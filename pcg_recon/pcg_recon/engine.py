"""Orchestrates one reconciliation run for one account and period."""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from .ingest import load_feed
from .matcher import Matcher
from .model import Txn, fmt
from .reconcile import build, ReconResult
from .store import Store, now


def file_hash(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def run_account(account: dict, period: tuple[date, date], inputs: Path, store: Store,
                rules: dict, profiles: dict, rules_hash: str, maker: str) -> ReconResult:
    aid = account["id"]
    ctx = {"entity": account["entity"], "gl_account": account["gl_account"]}
    bank, bmeta = load_feed(account["bank_feed"], aid, "BANK", period, profiles, inputs, ctx)
    book, kmeta = load_feed(account["ledger_feed"], aid, "BOOK", period, profiles, inputs, ctx)

    prior = store.prior_run(aid, period[0].isoformat())
    carried_bank, carried_book = [], []
    pre_alerts = []
    if prior:
        for d in store.carried_items(prior["run_id"]):
            t = Txn.from_row({k: v for k, v in d.items() if k in Txn.__dataclass_fields__})
            (carried_bank if t.side == "BANK" else carried_book).append(t)
        if not prior["signed_at"]:
            pre_alerts.append(("MEDIUM", "PRIOR_NOT_SIGNED",
                               f"Prior run {prior['run_id']} not signed off — carried items are unreviewed"))
        if bmeta.opening_balance is not None and bmeta.opening_balance != prior["bank_close"]:
            pre_alerts.append(("HIGH", "BANK_OPENING_MISMATCH",
                               f"Statement opening {fmt(bmeta.opening_balance)} ≠ prior closing {fmt(prior['bank_close'])}"))
        if kmeta.opening_balance is not None and kmeta.opening_balance != prior["book_close"]:
            pre_alerts.append(("HIGH", "BOOK_OPENING_MISMATCH",
                               f"Ledger opening {fmt(kmeta.opening_balance)} ≠ prior closing {fmt(prior['book_close'])} "
                               "— back-dated postings into a closed period?"))

    # Book closing when the export has no running balance: opening from prior run / config
    if kmeta.closing_balance is None:
        opening = kmeta.opening_balance
        if opening is None:
            opening = prior["book_close"] if prior else int(round(float(account.get("opening_book_balance", 0)) * 100))
        kmeta.opening_balance = opening
        kmeta.closing_balance = opening + sum(t.amount for t in book)
    if bmeta.closing_balance is None:
        opening = bmeta.opening_balance if bmeta.opening_balance is not None else (prior["bank_close"] if prior else 0)
        bmeta.opening_balance = opening
        bmeta.closing_balance = opening + sum(t.amount for t in bank)
        pre_alerts.append(("MEDIUM", "NO_STATEMENT_BALANCE",
                           "Statement carries no balances — closing derived; confirm against bank confirmation"))

    for t in carried_bank + carried_book:
        t.origin_period = t.origin_period or (prior["period_end"] if prior else "")
    for t in bank + book:
        t.origin_period = period[1].isoformat()

    m = Matcher(carried_bank + bank, carried_book + book, rules, account.get("date_window_days", 5),
                client_money=bool(account.get("client_money")), current_period=period[1].isoformat())
    matches = m.run(store.decisions(aid))
    open_bank, open_book = m.open_items()
    res = build(account, period[1], bmeta, kmeta, matches, open_bank, open_book, rules,
                carried_bank + bank, carried_book + book)
    for sev, code, msg in pre_alerts:
        res.alerts.insert(0, {"account_id": aid, "severity": sev, "code": code, "message": msg, "uid": ""})
    res.stats["carried_in_bank"] = len(carried_bank)
    res.stats["carried_in_book"] = len(carried_book)
    res.__dict__["all_bank"] = carried_bank + bank
    res.__dict__["all_book"] = carried_book + book

    run_id = f"{aid}-{period[1].strftime('%Y%m%d')}-{now()[11:19].replace(':', '')}"
    res.__dict__["run_id"] = run_id
    feeds = [f for f in (account["bank_feed"], account["ledger_feed"]) if "path" in f]
    import glob
    paths = [Path(p) for f in feeds for p in glob.glob(str(inputs / f["path"]))]
    store.save_run({
        "run_id": run_id, "account_id": aid, "entity": account["entity"],
        "period_start": period[0].isoformat(), "period_end": period[1].isoformat(),
        "created_at": now(), "maker": maker, "rules_hash": rules_hash,
        "inputs_hash": file_hash(paths) if paths else "",
        "bank_open": bmeta.opening_balance, "bank_close": res.bank_close,
        "book_open": kmeta.opening_balance, "book_close": res.book_close,
        "adj_bank": res.adj_bank, "adj_book": res.adj_book, "difference": res.difference,
        "status": res.status, "checker": None, "signed_at": None, "signoff_note": None, "report_path": None,
    }, open_bank + open_book, matches=matches)
    store.audit(maker, "RUN", {"run_id": run_id, "status": res.status, "difference": res.difference,
                               "auto_match_rate": res.stats["auto_match_rate"], "rules_hash": rules_hash})
    return res
