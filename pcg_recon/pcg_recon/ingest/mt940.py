"""SWIFT MT940 customer statement parser (bank feeds / host-to-host / SFTP drops).

Handles multiple statements per file, :60F:/:60M: opening, :61: lines with optional
entry date, reversal marks (RC/RD), :86: multi-line narrative, :62F:/:62M: closing.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ..model import Txn, StatementMeta, to_minor
from ..refs import extract_refs

_TAG = re.compile(r"^:(\d{2}[A-Z]?):", re.M)
_61 = re.compile(
    r"^(?P<vd>\d{6})(?P<ed>\d{4})?(?P<mark>R?[DC])(?P<fc>[A-Z])?(?P<amt>\d+,\d{0,2})"
    r"(?P<ttype>[NFS][A-Z0-9]{3})(?P<cref>[^/\n]*)(?://(?P<bref>[^\n]*))?(?:\n(?P<supp>.*))?",
    re.S)
_BAL = re.compile(r"^(?P<dc>[DC])(?P<d>\d{6})(?P<ccy>[A-Z]{3})(?P<amt>\d+,\d{0,2})")


def _yymmdd(s: str) -> date:
    return date(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]))


def _blocks(text: str):
    parts = _TAG.split(text)
    # parts: [pre, tag, body, tag, body, ...]
    for i in range(1, len(parts) - 1, 2):
        yield parts[i], parts[i + 1].strip("\r\n ")


def read_mt940(path: str | Path, account_id: str, period=None) -> tuple[list[Txn], StatementMeta]:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    text = re.sub(r"^-\}$|^\{4:|^\{1:.*?\}\{2:.*?\}", "", text, flags=re.M)
    meta = StatementMeta(account_id=account_id, source=path.name)
    txns: list[Txn] = []
    cur: Txn | None = None
    n = 0
    for tag, body in _blocks(text):
        if tag in ("60F", "60M"):
            m = _BAL.match(body)
            if m and meta.opening_balance is None:
                v = to_minor(m["amt"])
                meta.opening_balance = v if m["dc"] == "C" else -v
                meta.currency = m["ccy"]
        elif tag == "61":
            m = _61.match(body)
            if not m:
                raise ValueError(f"{path.name}: bad :61: line {body[:60]!r}")
            n += 1
            v = to_minor(m["amt"])
            mark = m["mark"]
            # D = debit (out), C = credit (in); RD = reversal of debit (in), RC = reversal of credit (out)
            signed = {"C": v, "D": -v, "RD": v, "RC": -v}[mark]
            cref = (m["cref"] or "").strip()
            bref = (m["bref"] or "").strip()
            cur = Txn(side="BANK", account_id=account_id, txn_date=_yymmdd(m["vd"]), amount=signed,
                      description="", reference=cref if cref != "NONREF" else bref,
                      source=path.name, source_row=n, currency=meta.currency,
                      doc_type=m["ttype"][1:])
            if m["supp"]:
                cur.description = m["supp"].strip()
            txns.append(cur)
        elif tag == "86" and cur is not None:
            narrative = " ".join(line.strip() for line in body.split("\n"))
            narrative = re.sub(r"\?\d{2}", " ", narrative)   # structured subfields ?20 ?21 ...
            cur.description = (cur.description + " " + narrative).strip()
        elif tag in ("62F", "62M"):
            m = _BAL.match(body)
            if m:
                v = to_minor(m["amt"])
                meta.closing_balance = v if m["dc"] == "C" else -v
    for t in txns:
        t.refs = extract_refs(t.description, t.reference)
        t.uid = ""
        t.__post_init__()
    if period:
        txns = [t for t in txns if period[0] <= t.txn_date <= period[1]]
    if txns:
        meta.period_start = min(t.txn_date for t in txns)
        meta.period_end = max(t.txn_date for t in txns)
    if meta.opening_balance is not None and meta.closing_balance is not None:
        calc = meta.opening_balance + sum(t.amount for t in txns)
        if calc != meta.closing_balance:
            meta.continuity_breaks.append({"row": "62F", "expected": calc, "stated": meta.closing_balance,
                                           "gap": meta.closing_balance - calc})
    return txns, meta
