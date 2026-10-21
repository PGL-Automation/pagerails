"""Bank charge audit.

Nigerian banks charge each electronic transfer as separate statement lines —
commission, VAT on the commission, and a stamp duty / EMTL levy — and several
(Providus among them) print the NIBSS session ID of the parent transfer on every
leg. That lets each charge be tied to the transfer that caused it, and checked:

  VAT_RATE          VAT leg != vat_rate x commission (to the kobo)
  DUPLICATE_CHARGE  the same charge type levied twice on one transfer
  CHARGES_KEPT      transfer reversed (failed) but some charge legs not refunded
  OVER_REVERSAL     more reversed than was debited on the session (bank owes itself)
  ORPHAN_CHARGE     charge legs with no principal transfer on the statement
"""
from __future__ import annotations

from collections import defaultdict

from .model import Txn
from .reconcile import classify


def session_of(t: Txn) -> str | None:
    nips = sorted(r for r in t.refs if r.startswith("NIP:"))
    return nips[-1] if nips else None


def audit(bank: list[Txn], rules: dict) -> tuple[list[dict], dict]:
    cfg = rules.get("charge_audit", {})
    rate = cfg.get("vat_rate", 0.075)
    charge_cats = set(cfg.get("categories", ["BANK_CHARGES", "VAT_ON_CHARGES", "EMTL_STAMP_DUTY"]))
    sessions: dict[str, list] = defaultdict(list)
    for t in bank:
        s = session_of(t)
        if s:
            sessions[s].append((t, classify(t, rules)[0]))

    rows, tariff = [], defaultdict(int)
    stats = defaultdict(int)
    for s, legs in sessions.items():
        deb = [(t, c) for t, c in legs if t.amount < 0]
        rev = [(t, c) for t, c in legs if t.amount > 0 and c == "REVERSAL"]
        principal = [(t, c) for t, c in legs if c not in charge_cats and c != "REVERSAL"]   # either direction
        principal_out = [(t, c) for t, c in principal if t.amount < 0]
        charges = [(t, c) for t, c in deb if c in charge_cats]
        if not charges:
            continue
        stats["sessions_with_charges"] += 1
        by_cat = defaultdict(list)
        for t, c in charges:
            by_cat[c].append(t)
        comm = sum(-t.amount for t in by_cat.get("BANK_CHARGES", []))
        vat = sum(-t.amount for t in by_cat.get("VAT_ON_CHARGES", []))
        tariff[(comm, vat, sum(-t.amount for t in by_cat.get("EMTL_STAMP_DUTY", [])))] += 1
        first = min(t.txn_date for t, _ in legs)
        base = {"session": s[4:], "date": first.isoformat(),
                "direction": "OUT" if principal_out else ("IN" if principal else "-"),
                "principal": sum(abs(t.amount) for t, _ in principal) / 100,
                "commission": comm / 100, "vat": vat / 100,
                "stamp_duty": sum(-t.amount for t in by_cat.get("EMTL_STAMP_DUTY", [])) / 100,
                "reversed": sum(t.amount for t, _ in rev) / 100,
                "narration": (principal[0][0] if principal else charges[0][0]).description[:110]}

        def flag(code, detail, amount=0):
            rows.append({**base, "check": code, "detail": detail, "amount_at_issue": amount / 100})
            stats[code] += 1

        if comm and vat != round(comm * rate):
            flag("VAT_RATE", f"VAT {vat / 100:,.2f} vs {rate:.1%} of commission {comm / 100:,.2f}", vat - round(comm * rate))
        for c, ts in by_cat.items():
            if len(ts) > 1 and len(principal) <= 1:
                flag("DUPLICATE_CHARGE", f"{len(ts)} x {c} on one transfer", sum(-t.amount for t in ts[1:]))
        if not principal:
            flag("ORPHAN_CHARGE", "charge legs with no principal transfer on this statement",
                 sum(-t.amount for t, _ in charges))
        debited = sum(-t.amount for t, _ in deb)
        reversed_ = sum(t.amount for t, _ in rev)
        if reversed_:
            stats["reversed_sessions"] += 1
            if reversed_ > debited:
                flag("OVER_REVERSAL", f"reversed {reversed_ / 100:,.2f} but only {debited / 100:,.2f} debited",
                     reversed_ - debited)
            elif principal_out and reversed_ >= sum(-t.amount for t, _ in principal_out) and reversed_ < debited:
                flag("CHARGES_KEPT", "transfer reversed but charges not fully refunded", debited - reversed_)
    summary = {"sessions": len(sessions), **stats,
               "tariff": sorted(((k[0] / 100, k[1] / 100, k[2] / 100, n) for k, n in tariff.items()),
                                key=lambda x: -x[3])}
    return rows, summary
