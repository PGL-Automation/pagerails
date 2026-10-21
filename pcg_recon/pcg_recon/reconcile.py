"""Reconciliation statement, classification of open items, ageing and alerts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .model import Txn, Match, StatementMeta, fmt


@dataclass
class ReconResult:
    account: dict
    period_end: date
    bank_meta: StatementMeta
    book_meta: StatementMeta
    matches: list
    open_bank: list
    open_book: list
    journals: list = field(default_factory=list)
    alerts: list = field(default_factory=list)
    bank_close: int = 0
    book_close: int = 0
    adj_bank: int = 0
    adj_book: int = 0
    difference: int = 0
    lines: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)

    @property
    def status(self) -> str:
        if self.difference != 0:
            return "UNRECONCILED"
        if any(a["severity"] == "HIGH" for a in self.alerts):
            return "RECONCILED-WITH-EXCEPTIONS"
        return "RECONCILED"


def classify(t: Txn, rules: dict) -> tuple[str, str]:
    for r in rules["classification"]:
        if r["sign"] == "in" and t.amount < 0:
            continue
        if r["sign"] == "out" and t.amount > 0:
            continue
        if re.search(r["pattern"], (t.description.strip() + " " + t.reference).upper()):
            return r["category"], r["gl"]
    return "UNCLASSIFIED", "REVIEW"


def age_bucket(days: int, buckets: list[int]) -> str:
    lo = 0
    for b in buckets:
        if days <= b:
            return f"{lo}-{b}"
        lo = b + 1
    return f">{buckets[-1]}"


def build(account: dict, period_end: date, bank_meta: StatementMeta, book_meta: StatementMeta,
          matches: list[Match], open_bank: list[Txn], open_book: list[Txn], rules: dict,
          all_bank: list[Txn], all_book: list[Txn]) -> ReconResult:
    esc = rules["escalation"]
    buckets = rules["ageing_buckets_days"]
    r = ReconResult(account, period_end, bank_meta, book_meta, matches, open_bank, open_book)
    r.bank_close = bank_meta.closing_balance or 0
    r.book_close = book_meta.closing_balance or 0

    # --- classify bank-only items and draft journals (book needs to catch up)
    in_proposed = {u for m in matches if m.status == "PROPOSED" for u in m.bank_uids}
    agg_cats = {x["category"] for x in rules["classification"] if x.get("aggregate")}
    jbuckets: dict = {}
    for t in open_bank:
        t.category, gl = classify(t, rules)
        if gl in ("REVIEW",) or t.uid in in_proposed:
            continue
        dr, cr = (account["gl_account"], gl) if t.amount > 0 else (gl, account["gl_account"])
        if t.category in agg_cats:
            # one journal per charge type per month, not one per bank line
            key = (t.category, t.txn_date.strftime("%Y-%m"), dr, cr)
            b = jbuckets.setdefault(key, {"amount": 0, "n": 0, "last": t.txn_date, "uids": []})
            b["amount"] += abs(t.amount); b["n"] += 1; b["last"] = max(b["last"], t.txn_date); b["uids"].append(t.uid)
            continue
        hold = t.category.startswith("UNIDENTIFIED") and account.get("client_money")
        r.journals.append({"account_id": account["id"], "entity": account["entity"], "uid": t.uid,
                           "date": t.txn_date.isoformat(), "category": t.category,
                           "dr_gl": dr, "cr_gl": cr, "amount": abs(t.amount) / 100, "lines": 1,
                           "narration": f"[{t.category}] {t.description[:80]}",
                           "status": "HOLD - identify before posting (client money)" if hold
                           else "DRAFT - requires approval"})
    for (cat, month, dr, cr), b in sorted(jbuckets.items()):
        r.journals.append({"account_id": account["id"], "entity": account["entity"],
                           "uid": f"{len(b['uids'])} lines", "date": b["last"].isoformat(), "category": cat,
                           "dr_gl": dr, "cr_gl": cr, "amount": b["amount"] / 100, "lines": b["n"],
                           "narration": f"{cat.replace('_', ' ').title()} {month} ({b['n']} bank lines)",
                           "status": "DRAFT - requires approval"})
    r.journals.sort(key=lambda j: (j["date"], j["category"]))
    for t in open_book:
        if t.amount > 0:
            t.category = "DEPOSIT_IN_TRANSIT"
        elif any(x.startswith("CHQ:") for x in t.refs) or t.doc_type.upper() in ("CHQ", "CHEQUE"):
            t.category = "UNPRESENTED_CHEQUE"
        else:
            t.category = "OUTSTANDING_PAYMENT"

    # --- reconciling items (open items by quadrant)
    credits_bank_not_gl = sum(t.amount for t in open_bank if t.amount > 0)   # received by bank, not yet in GL
    debits_bank_not_gl  = sum(t.amount for t in open_bank if t.amount < 0)   # paid by bank, not yet in GL
    credits_gl_not_bank = sum(t.amount for t in open_book if t.amount > 0)   # posted to GL, not yet in bank
    debits_gl_not_bank  = sum(t.amount for t in open_book if t.amount < 0)   # posted to GL, not yet in bank

    L = {
        # standard names (kept for backward-compat with SUMIFS formulas in the report)
        "deposits_in_transit":     credits_gl_not_bank,
        "unpresented_cheques":     sum(t.amount for t in open_book if t.category == "UNPRESENTED_CHEQUE"),
        "outstanding_payments":    debits_gl_not_bank - sum(t.amount for t in open_book if t.category == "UNPRESENTED_CHEQUE"),
        "bank_credits_not_in_book": credits_bank_not_gl,
        "bank_debits_not_in_book":  debits_bank_not_gl,
        # four-quadrant labels matching the manual reconciliation format
        "credits_bank_not_gl":  credits_bank_not_gl,
        "debits_bank_not_gl":   debits_bank_not_gl,
        "credits_gl_not_bank":  credits_gl_not_bank,
        "debits_gl_not_bank":   debits_gl_not_bank,
    }
    r.lines = L

    # --- adjusted balances and difference
    # Credit-balance convention (Symplus client-money accounts):
    #   The GL balance is negative (liability to clients).
    #   Formula:  bank_close - credits_in_bank_not_gl + |debits_in_bank_not_gl|
    #           = abs(GL_close)  when fully reconciled.
    # Standard debit-balance convention:
    #   adj_bank = bank_close + GL-only items
    #   adj_book = book_close + bank-only items
    if account.get("gl_balance_convention") == "credit":
        r.adj_bank = r.bank_close - credits_bank_not_gl - debits_bank_not_gl   # subtract because debits_bank_not_gl < 0
        r.adj_book = abs(r.book_close) + credits_gl_not_bank + debits_gl_not_bank
        r.difference = r.adj_bank - r.adj_book
    else:
        r.adj_bank = r.bank_close + credits_gl_not_bank + debits_gl_not_bank
        r.adj_book = r.book_close + credits_bank_not_gl + debits_bank_not_gl
        r.difference = r.adj_bank - r.adj_book

    # --- stats
    n_bank, n_book = len(all_bank), len(all_book)
    auto_bank = sum(len(m.bank_uids) for m in matches if m.status in ("AUTO", "APPROVED"))
    r.stats = {
        "bank_lines": n_bank, "book_lines": n_book,
        "auto_matched_bank_lines": auto_bank,
        "auto_match_rate": round(auto_bank / n_bank, 4) if n_bank else 1.0,
        "proposed_matches": sum(1 for m in matches if m.status == "PROPOSED"),
        "open_bank": len(open_bank), "open_book": len(open_book),
    }

    # --- alerts
    def alert(sev, code, msg, uid=""):
        r.alerts.append({"account_id": account["id"], "severity": sev, "code": code, "message": msg, "uid": uid})

    for b in bank_meta.continuity_breaks:
        alert("HIGH", "STATEMENT_CONTINUITY",
              f"Statement balance chain broken at {b.get('row')}: {b.get('note', '')} "
              f"gap {fmt(b['gap']) if isinstance(b.get('gap'), int) else ''} — missing/duplicated line or parse error")
    for b in book_meta.continuity_breaks:
        alert("HIGH", "LEDGER_CONTINUITY", f"Cashbook running balance broken at row {b.get('row')}")
    if r.difference != 0:
        alert("HIGH", "UNRECONCILED_DIFFERENCE",
              f"Adjusted bank {fmt(r.adj_bank)} vs adjusted book {fmt(r.adj_book)}: difference {fmt(r.difference)}. "
              "Check opening balances agree with last signed-off recon and for missing statement/ledger lines.")
    seen = {}
    for t in all_bank:
        k = (t.txn_date, t.amount, t.reference, t.description)
        if k in seen and t.reference:
            alert("MEDIUM", "POSSIBLE_DUPLICATE", f"Bank lines {seen[k]} and {t.source_row} identical", t.uid)
        seen[k] = t.source_row
    cm = account.get("client_money")
    for t in open_bank + open_book:
        age = (period_end - t.txn_date).days
        t_bucket = age_bucket(max(age, 0), buckets)
        t.__dict__["age_days"] = age
        t.__dict__["age_bucket"] = t_bucket
        if abs(t.amount) >= esc["large_item_minor"]:
            alert("HIGH", "LARGE_OPEN_ITEM", f"{t.side} item {fmt(t.amount)} open ({t.description[:50]})", t.uid)
        if t.category == "UNPRESENTED_CHEQUE" and age > esc["stale_cheque_days"]:
            alert("MEDIUM", "STALE_CHEQUE", f"Cheque {fmt(t.amount)} unpresented {age}d — write-back review", t.uid)
        elif cm and age > esc["client_money_escalate_days"]:
            alert("HIGH", "CLIENT_MONEY_AGED",
                  f"Client/fund money item {fmt(t.amount)} open {age}d — escalate to Compliance", t.uid)
        elif age > esc["unmatched_escalate_days"]:
            alert("MEDIUM", "AGED_OPEN_ITEM", f"{t.side} item {fmt(t.amount)} open {age}d", t.uid)
        if cm and t.side == "BANK" and t.category == "UNIDENTIFIED_RECEIPT" and t.uid not in in_proposed \
                and esc.get("aml_review_unidentified_receipts"):
            alert("HIGH", "AML_UNIDENTIFIED_RECEIPT",
                  f"Unidentified credit {fmt(t.amount)} into client/fund account — route to AML review", t.uid)
    return r
