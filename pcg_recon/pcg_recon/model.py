"""Canonical data model.

Every source (bank CSV/Excel, PDF, MT940, custodian, GL export, Postgres ledger)
is normalised into `Txn`. Sign convention, identical on both sides:

    + = money INTO the bank account   (bank: credit on statement | book: debit to bank GL)
    - = money OUT of the bank account (bank: debit on statement  | book: credit to bank GL)

Amounts are held as integer minor units (kobo / cents) to make matching and
subset-sum exact. Never use float for money in this package.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

BANK = "BANK"
BOOK = "BOOK"


def to_minor(value) -> int:
    """Parse '1,234.50', '(1,234.50)', '1.234,50' (MT940 comma decimal), 1234.5 -> 123450."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value * 100
    s = str(value).strip()
    if s in ("", "-", "nan", "None"):
        return 0
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    if s.endswith("-"):
        neg, s = True, s[:-1]
    if s.startswith("-"):
        neg, s = not neg, s[1:]
    s = s.replace("NGN", "").replace("₦", "").replace(" ", "")
    s = s.replace("CR", "").replace("DR", "")
    if "," in s and "." not in s and s.count(",") == 1 and len(s.split(",")[1]) <= 2:
        s = s.replace(",", ".")          # MT940 style 1234,50
    else:
        s = s.replace(",", "")
    try:
        d = Decimal(s)
    except InvalidOperation as e:
        raise ValueError(f"Unparseable amount: {value!r}") from e
    q = int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return -q if neg else q


def fmt(minor: int) -> str:
    sign = "-" if minor < 0 else ""
    m = abs(minor)
    return f"{sign}{m // 100:,}.{m % 100:02d}"


@dataclass
class Txn:
    side: str                 # BANK | BOOK
    account_id: str           # registry key, e.g. PAM-ZEN-OPS-01
    txn_date: date            # value date for bank; posting date for book
    amount: int               # signed minor units
    description: str = ""
    reference: str = ""
    source: str = ""          # file name / connector
    source_row: int = 0
    currency: str = "NGN"
    running_balance: int | None = None
    doc_type: str = ""        # e.g. CHQ, NIP, JV, RCPT
    refs: set = field(default_factory=set)   # extracted reference tokens
    category: str = ""        # set by classifier for unmatched bank-only items
    origin_period: str = ""   # period the item first appeared (carry-forward)
    uid: str = ""

    def __post_init__(self):
        if not self.uid:
            h = hashlib.sha1(
                f"{self.side}|{self.account_id}|{self.txn_date}|{self.amount}|"
                f"{self.reference}|{self.description}|{self.source}|{self.source_row}".encode()
            ).hexdigest()[:16]
            self.uid = f"{self.side[0]}-{h}"

    def to_row(self) -> dict:
        d = asdict(self)
        d["refs"] = " ".join(sorted(self.refs))
        d["txn_date"] = self.txn_date.isoformat()
        d["amount_major"] = self.amount / 100
        return d

    @classmethod
    def from_row(cls, d: dict) -> "Txn":
        d = dict(d)
        d.pop("amount_major", None)
        d["txn_date"] = date.fromisoformat(d["txn_date"])
        d["refs"] = set(filter(None, (d.get("refs") or "").split(" ")))
        return cls(**d)


@dataclass
class Match:
    match_id: str
    rule: str                 # P0_REVERSAL, P1_REF, P2_AMT_DATE, P3_AGGREGATE, P4_FUZZY, MANUAL
    confidence: float
    bank_uids: list
    book_uids: list
    status: str = "AUTO"      # AUTO | PROPOSED | APPROVED | REJECTED
    difference: int = 0       # bank total - book total (non-zero only for tolerance matches)
    note: str = ""


@dataclass
class StatementMeta:
    account_id: str
    source: str
    opening_balance: int | None = None
    closing_balance: int | None = None
    period_start: date | None = None
    period_end: date | None = None
    currency: str = "NGN"
    continuity_breaks: list = field(default_factory=list)
