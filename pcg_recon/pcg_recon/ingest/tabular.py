"""Generic tabular reader (CSV / XLS / XLSX) used for bank downloads, custodian
cash statements and GL / cashbook exports.

Nigerian bank portal exports usually carry 5-20 lines of letterhead / account
metadata above the real header row, sometimes split debit/credit columns,
sometimes a single signed amount with a DR/CR flag. A *profile* (profiles.yaml)
tells the reader which header names to look for; the reader locates the header
row itself, so letterhead changes do not break ingestion.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ..model import Txn, StatementMeta, to_minor
from ..refs import extract_refs

DATE_FORMATS = ["%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y",
                "%d %b %Y", "%d.%m.%Y", "%Y/%m/%d", "%d-%B-%Y"]


def parse_date(v, fmt: str | None = None) -> date:
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip().split(" ")[0] if fmt is None or " " not in fmt else str(v).strip()
    if fmt:
        return datetime.strptime(s, fmt).date()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    raise ValueError(f"Unparseable date {v!r}")


def _norm(h) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


def _read_raw(path: Path, sheet=None) -> pd.DataFrame:
    suf = path.suffix.lower()
    if suf in (".csv", ".txt"):
        # csv module, not pandas: letterhead lines have fewer fields than the table,
        # which makes pandas drop the real rows as "bad lines"
        import csv
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
            rows = list(csv.reader(fh))
        width = max((len(r) for r in rows), default=0)
        return pd.DataFrame([r + [""] * (width - len(r)) for r in rows], dtype=str)
    return pd.read_excel(path, header=None, dtype=object, sheet_name=sheet or 0)


def _locate_header(raw: pd.DataFrame, date_names: list[str], max_scan: int = 40) -> int:
    targets = {_norm(n) for n in date_names}
    for i in range(min(max_scan, len(raw))):
        cells = {_norm(c) for c in raw.iloc[i].tolist()}
        if cells & targets:
            return i
    raise ValueError(f"Header row not found (looked for any of {date_names})")


def _pick(cols: dict, names: list[str] | None):
    for n in names or []:
        if _norm(n) in cols:
            return cols[_norm(n)]
    return None


def read_tabular(path: str | Path, profile: dict, account_id: str, side: str,
                 period: tuple[date, date] | None = None) -> tuple[list[Txn], StatementMeta]:
    path = Path(path)
    raw = _read_raw(path, profile.get("sheet"))
    c = profile["columns"]
    hdr = _locate_header(raw, c["date"])
    df = raw.iloc[hdr + 1:].copy()
    df.columns = [str(x).strip() for x in raw.iloc[hdr].tolist()]
    cols = {_norm(x): x for x in df.columns}

    col_date = _pick(cols, c["date"])
    col_desc = _pick(cols, c.get("description"))
    col_ref = _pick(cols, c.get("reference"))
    col_in = _pick(cols, c.get("money_in"))
    col_out = _pick(cols, c.get("money_out"))
    col_amt = _pick(cols, c.get("amount"))
    col_drcr = _pick(cols, c.get("drcr"))
    col_bal = _pick(cols, c.get("balance"))
    col_ccy = _pick(cols, c.get("currency"))
    col_type = _pick(cols, c.get("doc_type"))
    col_acct = _pick(cols, c.get("account"))
    if not (col_in or col_out or col_amt):
        raise ValueError(f"{path.name}: no amount columns matched profile {profile.get('name')}")
    invert = bool(profile.get("invert_sign"))   # e.g. ledger exports where credit = money in
    acct_filter = profile.get("account_filter")

    txns: list[Txn] = []
    meta = StatementMeta(account_id=account_id, source=path.name)
    meta.__dict__["control"] = _control_totals(raw.iloc[:hdr], profile.get("control_labels") or {})
    for i, row in df.iterrows():
        dv = row.get(col_date)
        desc_l = str(row.get(col_desc, "")).upper() if col_desc else ""
        if any(k in desc_l for k in ("OPENING BALANCE", "BALANCE B/F", "BAL B/F", "BALANCE BROUGHT FORWARD")):
            if col_bal and meta.opening_balance is None:
                meta.opening_balance = to_minor(row.get(col_bal))
            continue
        if dv is None or str(dv).strip() in ("", "nan", "NaT", "None"):
            continue
        try:
            d = parse_date(dv, profile.get("date_format"))
        except ValueError:
            # opening/closing balance lines or footers
            if col_bal and "OPEN" in (str(dv) + desc_l).upper():
                meta.opening_balance = to_minor(row.get(col_bal))
            continue
        if col_acct and acct_filter and str(row.get(col_acct)).strip() != str(acct_filter):
            continue
        if col_amt:
            amt = to_minor(row.get(col_amt))
            if col_drcr:
                flag = str(row.get(col_drcr)).strip().upper()
                amt = -abs(amt) if flag.startswith("D") else abs(amt)
        else:
            amt = (to_minor(row.get(col_in)) if col_in else 0) - abs(to_minor(row.get(col_out)) if col_out else 0)
        if invert:
            amt = -amt
        if amt == 0:
            continue
        desc = str(row.get(col_desc, "") or "").strip() if col_desc else ""
        ref = str(row.get(col_ref, "") or "").strip() if col_ref else ""
        if ref in ("0", "0.0", "nan", "None"):
            ref = ""
        bal = to_minor(row.get(col_bal)) if col_bal and str(row.get(col_bal)).strip() not in ("", "nan") else None
        t = Txn(side=side, account_id=account_id, txn_date=d, amount=amt, description=desc,
                reference=ref if ref.lower() != "nan" else "", source=path.name, source_row=int(i) + 1,
                currency=str(row.get(col_ccy) or profile.get("currency", "NGN")) if col_ccy else profile.get("currency", "NGN"),
                running_balance=bal, doc_type=str(row.get(col_type, "") or "") if col_type else "")
        t.refs = extract_refs(t.description, t.reference)
        txns.append(t)

    if period:
        before = len(txns)
        kept = [t for t in txns if period[0] <= t.txn_date <= period[1]]
        if any(t.txn_date < period[0] for t in txns):
            meta.opening_balance = None      # re-derive from the first in-period running balance
        txns = kept
    if profile.get("newest_first") or (len(txns) > 1 and txns[0].txn_date > txns[-1].txn_date):
        txns.reverse()
    finalize_meta(meta, txns)
    _check_controls(meta, txns, full_file=not period or before == len(txns) if period else True)
    return txns, meta


def _check_controls(meta: StatementMeta, txns: list, full_file: bool):
    """Compare what we parsed with the totals the bank printed. Only meaningful when
    the whole file was read (no period filter trimmed it)."""
    ctl = meta.__dict__.get("control") or {}
    if not ctl or not full_file:
        return
    got = {"opening": meta.opening_balance, "closing": meta.closing_balance,
           "total_debit": -sum(t.amount for t in txns if t.amount < 0),
           "total_credit": sum(t.amount for t in txns if t.amount > 0),
           "count_debit": sum(1 for t in txns if t.amount < 0),
           "count_credit": sum(1 for t in txns if t.amount > 0)}
    res = {}
    for k, v in ctl.items():
        if k in got:
            res[k] = (v, got[k], v == got[k])
            if v != got[k]:
                meta.continuity_breaks.append({"row": f"control:{k}", "expected": v, "stated": got[k],
                                               "gap": (got[k] or 0) - v,
                                               "note": f"parsed {k} differs from bank-printed control figure"})
    meta.__dict__["control_check"] = res


def finalize_meta(meta: StatementMeta, txns: list[Txn]) -> None:
    """Derive opening/closing from running balances and check statement continuity:
    every row's balance must equal previous balance + amount. A break means a
    missing row, a duplicated row, or a mis-parsed amount — never silently ignore it."""
    if not txns:
        return
    meta.period_start = min(t.txn_date for t in txns)
    meta.period_end = max(t.txn_date for t in txns)
    with_bal = [t for t in txns if t.running_balance is not None]
    if not with_bal:
        return
    if meta.opening_balance is None:
        meta.opening_balance = with_bal[0].running_balance - with_bal[0].amount
    prev = meta.opening_balance
    for t in txns:
        if t.running_balance is None:
            prev += t.amount
            continue
        if prev + t.amount != t.running_balance:
            meta.continuity_breaks.append(
                {"row": t.source_row, "date": t.txn_date.isoformat(), "expected": prev + t.amount,
                 "stated": t.running_balance, "gap": t.running_balance - (prev + t.amount)})
        prev = t.running_balance
    meta.closing_balance = prev


def _control_totals(pre, labels: dict) -> dict:
    """Bank-printed control figures in the statement preamble (opening, closing,
    debit/credit totals and counts). Label -> value is read from the cell to the right."""
    out = {}
    if pre is None or not labels:
        return out
    for _, row in pre.iterrows():
        cells = [str(x).strip() for x in row.tolist()]
        for j, c in enumerate(cells[:-1]):
            for key, lab in labels.items():
                if _norm(c) == _norm(lab) and cells[j + 1] not in ("", "nan"):
                    try:
                        out[key] = to_minor(cells[j + 1]) if "count" not in key else int(float(cells[j + 1].replace(",", "")))
                    except ValueError:
                        pass
    return out
