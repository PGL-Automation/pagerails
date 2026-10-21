"""
Background task: run the reconciliation engine for one or more accounts.
FastAPI BackgroundTasks for now; drop-in Celery upgrade later.
"""
import hashlib
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

from app.config import settings
from app import db

# Make the pcg_recon package importable from the sibling directory
_engine_root = (Path(__file__).parent.parent.parent / "pcg_recon").resolve()
if str(_engine_root) not in sys.path:
    sys.path.insert(0, str(_engine_root))

import yaml
from pcg_recon.engine import run_account
from pcg_recon.report import write_pack
from pcg_recon.store import Store


def _load_config():
    cfg = settings.config_dir()
    accounts = yaml.safe_load((cfg / "accounts.yaml").read_text())
    profiles = yaml.safe_load((cfg / "profiles.yaml").read_text())
    rules_txt = (cfg / "rules.yaml").read_text()
    rules = yaml.safe_load(rules_txt)
    rules_hash = hashlib.sha256(rules_txt.encode()).hexdigest()[:12]
    return accounts, profiles, rules, rules_hash


def _parse_period(s: str) -> tuple[date, date]:
    import calendar
    if ":" in s:
        a, b = s.split(":")
        return date.fromisoformat(a), date.fromisoformat(b)
    parts = s.split("-")
    if len(parts) == 2:
        y, m = int(parts[0]), int(parts[1])
        return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    d = date.fromisoformat(s)
    return d, d


def run_engine_task(account_ids: list[str], period_str: str, maker: str):
    """
    Runs in a FastAPI BackgroundTask (or called directly by the scheduler).

    For each account:
      1. Run the reconciliation engine
      2. Save matches to DB
      3. Save draft journals to DB (so the UI and posting queue can use them)
      4. Write the Excel pack (Balance Rec + Symplus Import sheets)
      5. Store the report path in the runs table
    """
    try:
        accounts_cfg, profiles, rules, rules_hash = _load_config()
        period  = _parse_period(period_str)
        store   = Store(str(settings.db_path()))
        inputs  = settings.inputs_dir()
        outputs = settings.outputs_dir()
        outputs.mkdir(parents=True, exist_ok=True)

        db.migrate()

        results = []
        for acct in accounts_cfg["accounts"]:
            if acct["id"] not in account_ids:
                continue
            if acct.get("enabled") is False:
                continue
            try:
                res = run_account(acct, period, inputs, store, rules, profiles, rules_hash, maker)
                run_id = res.__dict__["run_id"]

                # 1. Save matches
                db.save_matches(run_id, [
                    {"match_id": m.match_id, "rule": m.rule, "confidence": m.confidence,
                     "bank_uids": m.bank_uids, "book_uids": m.book_uids,
                     "status": m.status, "difference": m.difference, "note": m.note}
                    for m in res.matches
                ])

                # 2. Save draft journals
                db.save_run_journals(run_id, acct["id"], res.journals)

                results.append(res)

            except Exception as e:
                print(f"[tasks] {acct['id']} FAILED: {e}")
                traceback.print_exc()
                store.audit(maker, "RUN_FAILED", {"account_id": acct["id"], "error": str(e)})

        if results:
            # 3. Write the Excel pack (all reconciled accounts together)
            label = period_str if len(period_str) != 10 else period[1].strftime("%d %b %Y")
            safe_label = period_str.replace(":", "_")
            pack_path = outputs / f"recon_pack_{safe_label}.xlsx"
            entities  = accounts_cfg.get("entities", {})
            write_pack(results, str(pack_path), label, maker, entities)

            # 4. Store report_path for each run in the DB
            for res in results:
                run_id = res.__dict__["run_id"]
                db.update_report_path(run_id, str(pack_path))

            print(f"[tasks] Pack written: {pack_path}")

    except Exception as e:
        print(f"[tasks] engine task crashed: {e}")
        traceback.print_exc()


# ── Automated daily fetch (called by the scheduler) ───────────────────────────

def daily_fetch_task(account_id: str, job_type: str):
    """
    Pulls the bank statement or GL for a single account for today's date.
    Called by the APScheduler at the configured COB time.
    """
    from app.connectors.base import DateRange
    from app.connectors.registry import get_statement_provider, get_ledger_provider

    today = date.today()
    period = DateRange(start=today, end=today)

    try:
        accounts_cfg, _, _, _ = _load_config()
        acct = next((a for a in accounts_cfg["accounts"] if a["id"] == account_id), None)
        if not acct:
            print(f"[scheduler] Account {account_id} not found")
            return

        dest = settings.inputs_dir() / account_id

        if job_type == "STATEMENT":
            provider = get_statement_provider(acct)
            if not provider.can_auto_fetch():
                print(f"[scheduler] {account_id}: statement provider '{provider.name}' cannot auto-fetch")
                return
            result = provider.fetch(account_id, period, dest)
            db.connector_log(provider.name, account_id, "AUTO_FETCH_STATEMENT",
                             "OK" if result.ok else "FAILED", result.message, "scheduler")
            if result.ok:
                print(f"[scheduler] {account_id}: statement fetched → {result.path}")

        elif job_type == "LEDGER":
            provider = get_ledger_provider(acct)
            if not provider.can_auto_fetch():
                print(f"[scheduler] {account_id}: ledger provider '{provider.name}' cannot auto-fetch")
                return
            result = provider.fetch(
                account_id=account_id,
                gl_account=acct.get("gl_account", ""),
                period=period,
                dest_dir=dest,
            )
            db.connector_log(provider.name, account_id, "AUTO_FETCH_LEDGER",
                             "OK" if result.ok else "FAILED", result.message, "scheduler")
            if result.ok:
                print(f"[scheduler] {account_id}: GL fetched → {result.path}")

    except Exception as e:
        print(f"[scheduler] {account_id} {job_type} fetch failed: {e}")
        traceback.print_exc()
        db.connector_log("scheduler", account_id, f"AUTO_FETCH_{job_type}",
                         "ERROR", str(e), "scheduler")
