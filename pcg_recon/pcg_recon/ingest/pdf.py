"""PDF bank / custodian statement parser.

Layout-agnostic: most Nigerian bank PDFs print one line per transaction as
    <date> [<value date>] <narration ...> <debit|credit> <balance>
The column the amount sits in is unreliable after text extraction, so the sign is
derived from the RUNNING BALANCE movement (balance_now - balance_prev), and then
cross-checked against the printed amount. Any disagreement is recorded as a
continuity break and surfaces in the exceptions report.

Scanned (image-only) PDFs have no text layer: run OCR first (ocrmypdf) — the
reader raises a clear error in that case rather than returning nothing.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from ..model import Txn, StatementMeta, to_minor
from ..refs import extract_refs
from .tabular import parse_date

_DATE = r"(\d{1,2}[-/ ](?:[A-Za-z]{3}|\d{1,2})[-/ ]\d{2,4})"
_LINE = re.compile(rf"^{_DATE}\s+(?:{_DATE}\s+)?(.*)$")
_MONEY = re.compile(r"\(?-?\d{1,3}(?:,\d{3})*\.\d{2}\)?(?:\s?(?:CR|DR))?")
_OPEN = re.compile(r"(OPENING BALANCE|BALANCE B/F|BAL B/F|BALANCE BROUGHT FORWARD|OPENING BAL)", re.I)
_CLOSE = re.compile(r"(CLOSING BALANCE|BALANCE C/F|BAL C/F|CLOSING BAL)", re.I)


def read_pdf(path: str | Path, account_id: str, profile: dict | None = None, period=None):
    path = Path(path)
    profile = profile or {}
    lines: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            lines.extend(l.strip() for l in txt.split("\n") if l.strip())
    if not lines:
        raise ValueError(f"{path.name}: no text layer — scanned PDF, run OCR (ocrmypdf) first")

    meta = StatementMeta(account_id=account_id, source=path.name, currency=profile.get("currency", "NGN"))
    txns: list[Txn] = []
    stated_close = None
    prev_bal = None
    for ln in lines:
        nums = _MONEY.findall(ln)
        if _OPEN.search(ln) and nums and meta.opening_balance is None:
            meta.opening_balance = _signed_bal(nums[-1])
            prev_bal = meta.opening_balance
            continue
        if _CLOSE.search(ln) and nums:
            stated_close = _signed_bal(nums[-1])
            continue
        m = _LINE.match(ln)
        if not m or len(nums) < 2:
            # continuation of the previous narration (wrapped line)
            if txns and not nums and not _LINE.match(ln):
                if len(txns[-1].description) < 400:
                    txns[-1].description += " " + ln
            continue
        try:
            d = parse_date(m.group(1).replace(" ", "-"), profile.get("date_format"))
        except ValueError:
            continue
        rest = m.group(3)
        bal = _signed_bal(nums[-1])
        printed = abs(to_minor(nums[-2].replace("CR", "").replace("DR", "")))
        spans = list(_MONEY.finditer(rest))
        desc = rest[:spans[-2].start()] if len(spans) >= 2 else rest   # cut at the amount column
        if prev_bal is None:
            # no opening line: sign unknown for the first row — use keyword heuristic, flag it
            sign = -1 if re.search(r"\b(DR|DEBIT|WITHDRAW|CHARGE|FEE|TRF TO|TRANSFER TO)\b", desc, re.I) else 1
            amt = sign * printed
            meta.opening_balance = bal - amt
            meta.continuity_breaks.append({"row": len(txns) + 1, "date": d.isoformat(),
                                           "note": "no opening balance line; first-row sign inferred"})
        else:
            amt = bal - prev_bal
            if abs(amt) != printed:
                meta.continuity_breaks.append({"row": len(txns) + 1, "date": d.isoformat(),
                                               "expected": prev_bal + (printed if amt > 0 else -printed),
                                               "stated": bal, "gap": abs(amt) - printed,
                                               "note": "balance movement != printed amount"})
        prev_bal = bal
        t = Txn(side="BANK", account_id=account_id, txn_date=d, amount=amt,
                description=re.sub(r"\s+", " ", desc).strip(), source=path.name,
                source_row=len(txns) + 1, running_balance=bal, currency=meta.currency)
        txns.append(t)
    for t in txns:
        t.refs = extract_refs(t.description)
        t.uid = ""
        t.__post_init__()
    meta.closing_balance = prev_bal
    if stated_close is not None and stated_close != prev_bal:
        meta.continuity_breaks.append({"row": "CLOSING", "expected": prev_bal, "stated": stated_close,
                                       "gap": stated_close - (prev_bal or 0)})
    if period:
        txns = [t for t in txns if period[0] <= t.txn_date <= period[1]]
    if txns:
        meta.period_start = min(t.txn_date for t in txns)
        meta.period_end = max(t.txn_date for t in txns)
    return txns, meta


def _signed_bal(s: str) -> int:
    v = to_minor(s.replace("CR", "").replace("DR", ""))
    return -abs(v) if "DR" in s.upper() else v
