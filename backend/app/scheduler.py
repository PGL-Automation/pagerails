"""
APScheduler — daily automated bank statement and GL pulls.

Each account in accounts.yaml can declare an `auto_fetch` block:

  auto_fetch:
    enabled: true
    statement_time: "21:00"   # COB time to pull the bank statement (Africa/Lagos)
    gl_time:        "20:30"   # pull GL shortly before statement to catch day's postings
    auto_run:       true      # also trigger a reconciliation run after fetching

If `auto_fetch` is absent the account is skipped.

The scheduler runs inside the FastAPI process (BackgroundScheduler).
It is production-grade: uses a persistent job store backed by the same SQLite
database, so jobs survive server restarts. When the Celery upgrade happens,
replace `BackgroundScheduler` with `CeleryScheduler` — no other changes needed.
"""
from __future__ import annotations

import sys
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from app.config import settings

_scheduler: BackgroundScheduler | None = None

TIMEZONE = "Africa/Lagos"


def _parse_time(t: str) -> tuple[int, int]:
    """Parse 'HH:MM' → (hour, minute)."""
    parts = t.split(":")
    return int(parts[0]), int(parts[1])


def _fetch_statement_job(account_id: str):
    from app.tasks import daily_fetch_task
    daily_fetch_task(account_id, "STATEMENT")


def _fetch_ledger_job(account_id: str):
    from app.tasks import daily_fetch_task
    daily_fetch_task(account_id, "LEDGER")


def _auto_run_job(account_id: str):
    """Trigger a daily reconciliation run after fetch completes."""
    from datetime import date
    from app.tasks import run_engine_task
    today = date.today().isoformat()
    run_engine_task([account_id], today, "scheduler")


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    db_url = f"sqlite:///{settings.db_path()}"
    jobstores = {
        "default": SQLAlchemyJobStore(url=db_url, tablename="apscheduler_jobs")
    }
    _scheduler = BackgroundScheduler(jobstores=jobstores, timezone=TIMEZONE)
    return _scheduler


def start_scheduler():
    """
    Load accounts.yaml and register cron jobs for every account
    that has `auto_fetch.enabled: true`.
    Idempotent — safe to call multiple times (existing jobs are replaced).
    """
    import yaml
    cfg = settings.config_dir()
    data = yaml.safe_load((cfg / "accounts.yaml").read_text())
    accounts = data.get("accounts", [])

    sched = get_scheduler()

    for acct in accounts:
        if not acct.get("enabled", True):
            continue
        af = acct.get("auto_fetch", {})
        if not af.get("enabled", False):
            continue

        aid = acct["id"]

        # Bank statement pull
        stmt_time = af.get("statement_time", "21:00")
        sh, sm = _parse_time(stmt_time)
        sched.add_job(
            _fetch_statement_job,
            trigger=CronTrigger(hour=sh, minute=sm, timezone=TIMEZONE),
            id=f"stmt_{aid}",
            replace_existing=True,
            args=[aid],
            name=f"Daily statement fetch — {aid}",
            misfire_grace_time=3600,   # if server was down, run within 1h window
        )

        # GL pull (slightly before statement so the latest entries are included)
        gl_time = af.get("gl_time", "20:30")
        gh, gm = _parse_time(gl_time)
        sched.add_job(
            _fetch_ledger_job,
            trigger=CronTrigger(hour=gh, minute=gm, timezone=TIMEZONE),
            id=f"gl_{aid}",
            replace_existing=True,
            args=[aid],
            name=f"Daily GL fetch — {aid}",
            misfire_grace_time=3600,
        )

        # Auto-run (after both fetches complete; add buffer of a few minutes)
        if af.get("auto_run", True):
            run_hour = sh
            run_min  = sm + 5
            if run_min >= 60:
                run_hour += 1
                run_min  -= 60
            sched.add_job(
                _auto_run_job,
                trigger=CronTrigger(hour=run_hour, minute=run_min, timezone=TIMEZONE),
                id=f"run_{aid}",
                replace_existing=True,
                args=[aid],
                name=f"Daily auto-run — {aid}",
                misfire_grace_time=3600,
            )

        print(f"[scheduler] {aid}: GL@{gl_time} → statement@{stmt_time} → run@{run_hour:02d}:{run_min:02d} ({TIMEZONE})")

    # Register payout timeout and recon-scan jobs
    try:
        from app.payout_scheduler import register_payout_jobs
        register_payout_jobs(sched)
    except Exception as _pe:
        print(f"[scheduler] Payout jobs warning: {_pe}")

    if not sched.running:
        sched.start()
        print(f"[scheduler] Started with {len(sched.get_jobs())} job(s)")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def list_jobs() -> list[dict]:
    sched = get_scheduler()
    jobs = []
    for job in sched.get_jobs():
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        jobs.append({
            "id":       job.id,
            "name":     job.name,
            "next_run": next_run,
            "trigger":  str(job.trigger),
        })
    return jobs


def trigger_now(job_id: str) -> bool:
    """Manually fire a scheduled job immediately (for testing / manual trigger)."""
    sched = get_scheduler()
    job   = sched.get_job(job_id)
    if not job:
        return False
    job.func(*job.args)
    return True
