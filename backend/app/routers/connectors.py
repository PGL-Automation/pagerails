"""
Connector routes:
  • Bank statement fetch (manual trigger + scheduler status)
  • GL fetch (manual trigger + scheduler status)
  • Journal review (list, approve)
  • Posting queue (populate, approve, execute, download CSV)
  • Scheduler management (list jobs, trigger manually)
"""
import csv
import io
import yaml
from datetime import date, datetime, timezone
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import db
from app.auth import (
    CanFetchStatement, CanFetchLedger, CanPostToLedger,
    CanApprovePost, AnyUser,
)
from app.config import settings
from app.connectors.base import DateRange, DraftJournal
from app.connectors.registry import (
    get_statement_provider, get_ledger_provider, get_ledger_poster,
)

router = APIRouter()


def _load_accounts() -> list[dict]:
    cfg = settings.config_dir()
    data = yaml.safe_load((cfg / "accounts.yaml").read_text())
    return [a for a in data.get("accounts", []) if a.get("enabled", True)]


def _find_account(account_id: str) -> dict:
    for a in _load_accounts():
        if a["id"] == account_id:
            return a
    raise HTTPException(404, f"Account {account_id} not found")


# ── Bank statement fetch ───────────────────────────────────────────────────────

class FetchRequest(BaseModel):
    account_id:   str
    period_start: str
    period_end:   str


@router.post("/statement/fetch", summary="Pull bank statement (API or email)")
def fetch_statement(body: FetchRequest, user: CanFetchStatement):
    account  = _find_account(body.account_id)
    provider = get_statement_provider(account)

    if not provider.can_auto_fetch():
        raise HTTPException(400,
            f"Account {body.account_id} uses '{provider.name}' which requires manual upload. "
            "Upload via the Files page or configure API credentials.")

    period = DateRange(
        start=date.fromisoformat(body.period_start),
        end=date.fromisoformat(body.period_end),
    )
    dest   = settings.inputs_dir() / body.account_id
    result = provider.fetch(body.account_id, period, dest)

    db.connector_log(provider.name, body.account_id, "FETCH_STATEMENT",
                     "OK" if result.ok else "FAILED", result.message, user.name)
    if not result.ok:
        raise HTTPException(502, f"Statement fetch failed: {result.message}")

    return {"ok": True, "provider": provider.name,
            "file": str(result.path), "message": result.message}


@router.get("/statement/status/{account_id}", summary="Statement provider status")
def statement_status(account_id: str, _: AnyUser):
    account  = _find_account(account_id)
    provider = get_statement_provider(account)
    af       = account.get("auto_fetch", {})
    return {
        "account_id":      account_id,
        "provider":        provider.name,
        "can_auto_fetch":  provider.can_auto_fetch(),
        "connection_ok":   provider.test_connection(),
        "schedule_enabled": af.get("enabled", False),
        "statement_time":  af.get("statement_time", "21:00"),
        "gl_time":         af.get("gl_time", "20:30"),
    }


# ── GL / Ledger fetch ─────────────────────────────────────────────────────────

@router.post("/ledger/fetch", summary="Pull GL from accounting system")
def fetch_ledger(body: FetchRequest, user: CanFetchLedger):
    account  = _find_account(body.account_id)
    provider = get_ledger_provider(account)

    period = DateRange(
        start=date.fromisoformat(body.period_start),
        end=date.fromisoformat(body.period_end),
    )
    dest   = settings.inputs_dir() / body.account_id
    result = provider.fetch(
        account_id=body.account_id,
        gl_account=account.get("gl_account", ""),
        period=period,
        dest_dir=dest,
    )

    db.connector_log(provider.name, body.account_id, "FETCH_LEDGER",
                     "OK" if result.ok else "FAILED", result.message, user.name)
    if not result.ok:
        raise HTTPException(502, f"Ledger fetch failed: {result.message}")

    return {"ok": True, "provider": provider.name,
            "file": str(result.path), "message": result.message}


@router.get("/ledger/status/{account_id}", summary="Ledger provider status")
def ledger_status(account_id: str, _: AnyUser):
    account  = _find_account(account_id)
    provider = get_ledger_provider(account)
    af       = account.get("auto_fetch", {})
    return {
        "account_id":      account_id,
        "provider":        provider.name,
        "can_auto_fetch":  provider.can_auto_fetch(),
        "connection_ok":   provider.test_connection(),
        "schedule_enabled": af.get("enabled", False),
        "gl_time":         af.get("gl_time", "20:30"),
    }


# ── Draft journals ─────────────────────────────────────────────────────────────

@router.get("/journals/{run_id}", summary="Draft journals for a run")
def list_journals(run_id: str, _: AnyUser):
    run = db.run_get(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    return db.run_journals_list(run_id)


@router.post("/journals/{journal_id}/approve", summary="Approve a draft journal")
def approve_journal(journal_id: int, user: CanApprovePost):
    db.run_journal_approve(journal_id, user.name)
    return {"approved": True, "journal_id": journal_id, "approved_by": user.name}


# ── Posting queue ─────────────────────────────────────────────────────────────

@router.get("/posting/queue", summary="Posting queue items")
def list_posting_queue(run_id: str | None = None, status: str | None = None, _: AnyUser = None):
    return db.posting_queue_list(run_id=run_id, status=status)


@router.post("/posting/queue/{run_id}", summary="Move approved journals into posting queue")
def populate_posting_queue(run_id: str, user: CanApprovePost):
    """
    Takes all APPROVED draft journals for a run and queues them for posting.
    Only journals the reviewer has approved (status=APPROVED) are included.
    HOLD journals (unidentified credits on client-money accounts) are excluded.
    """
    run = db.run_get(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    journals = [j for j in db.run_journals_list(run_id) if j["status"] == "APPROVED"]
    if not journals:
        raise HTTPException(400, "No approved journals for this run. Approve them first.")

    ids = db.posting_queue_add(run_id, run["account_id"], journals)
    return {"queued": len(ids), "run_id": run_id, "queued_by": user.name}


@router.post("/posting/approve/{item_id}", summary="Approve a posting queue item")
def approve_posting(item_id: int, user: CanApprovePost):
    db.posting_queue_approve(item_id, user.name)
    return {"approved": True, "item_id": item_id, "approved_by": user.name}


@router.post("/posting/execute/{run_id}", summary="Post approved journals to the ledger")
def execute_posting(run_id: str, user: CanPostToLedger, bg: BackgroundTasks):
    items = db.posting_queue_list(run_id=run_id, status="APPROVED")
    if not items:
        raise HTTPException(400, "No approved items in the posting queue for this run")

    run = db.run_get(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    account = _find_account(run["account_id"])
    poster  = get_ledger_poster(account)

    def _do_post():
        journals = [
            DraftJournal(
                run_id=item["run_id"],
                account_id=item["account_id"],
                category=item["category"],
                date=item["journal"].get("date", ""),
                dr_gl=item["journal"].get("dr_gl", ""),
                cr_gl=item["journal"].get("cr_gl", ""),
                amount=item["journal"].get("amount", 0),
                narration=item["journal"].get("narration", ""),
                book_of_account=account.get("book_of_account", "GL08"),
                trans_code=account.get("trans_code", "000"),
                currency=account.get("currency", "NGN"),
            )
            for item in items
        ]
        result = poster.post(journals, posted_by=user.name)
        if result.ok:
            for item in items:
                db.posting_queue_mark_posted(item["id"], user.name, result.post_ref)
            db.connector_log(poster.name, run["account_id"], "POST_JOURNALS",
                             "OK", result.message, user.name)
        else:
            for item in items:
                db.posting_queue_mark_failed(item["id"], result.message)
            db.connector_log(poster.name, run["account_id"], "POST_JOURNALS",
                             "FAILED", result.message, user.name)

    bg.add_task(_do_post)
    return {"message": f"Posting {len(items)} journals via {poster.name}",
            "provider": poster.name, "items": len(items)}


@router.get("/posting/download/{run_id}", summary="Download Symplus import CSV for a run")
def download_symplus_csv(run_id: str, _: AnyUser):
    """
    Generates and streams the Symplus Loaded Data import CSV directly from
    the database — no need to re-run the engine.
    Finance downloads this, then loads it in Symplus → GL → Loaded Data → Import.
    """
    run = db.run_get(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    account  = _find_account(run["account_id"])
    journals = db.run_journals_list(run_id)

    # Only include non-HOLD journals
    postable = [j for j in journals if j["status"] != "HOLD"]
    if not postable:
        raise HTTPException(404, "No postable journals for this run")

    from app.connectors.posting.symplus import SymplusCSVPoster
    poster = SymplusCSVPoster()

    book  = account.get("book_of_account", "GL08")
    tcode = account.get("trans_code", "000")
    batch_prefix = account.get("posting", {}).get("batch_prefix", "PAGERAILS")
    batch_id = f"{batch_prefix}-{run_id[-14:]}"

    buf    = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(SymplusCSVPoster.HEADERS)

    for j in postable:
        draft = DraftJournal(
            run_id=run_id,
            account_id=run["account_id"],
            category=j["category"],
            date=j["date"],
            dr_gl=j["dr_gl"],
            cr_gl=j["cr_gl"],
            amount=j["amount"],
            narration=j["narration"],
            book_of_account=book,
            trans_code=tcode,
            currency=account.get("currency", "NGN"),
        )
        for row in poster._make_rows(draft, batch_id):
            writer.writerow(row)

    csv_bytes = buf.getvalue().encode("utf-8")
    filename  = f"{batch_id}.csv"

    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/posting/status/{account_id}", summary="Posting provider status")
def posting_status(account_id: str, _: AnyUser):
    account = _find_account(account_id)
    poster  = get_ledger_poster(account)
    return {
        "account_id":   account_id,
        "provider":     poster.name,
        "connection_ok": poster.test_connection(),
    }


# ── Scheduler management ──────────────────────────────────────────────────────

@router.get("/scheduler/jobs", summary="List scheduled jobs")
def list_scheduled_jobs(_: AnyUser):
    from app.scheduler import list_jobs
    return list_jobs()


@router.post("/scheduler/trigger/{job_id}", summary="Manually fire a scheduled job now")
def trigger_job(job_id: str, user: CanFetchStatement):
    from app.scheduler import trigger_now
    ok = trigger_now(job_id)
    if not ok:
        raise HTTPException(404, f"Job '{job_id}' not found in scheduler")
    return {"triggered": True, "job_id": job_id, "triggered_by": user.name}


# ── Connector audit log ────────────────────────────────────────────────────────

@router.get("/logs", summary="Connector activity log")
def connector_logs(account_id: str | None = None, _: AnyUser = None):
    with db.get_db() as con:
        if account_id:
            rows = con.execute(
                "SELECT * FROM connector_logs WHERE account_id=? ORDER BY created_at DESC LIMIT 200",
                (account_id,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM connector_logs ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
    return [dict(r) for r in rows]
