import csv
import io
import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

import json
from app import db
from app.auth import AnyUser, CanTriggerRun
from app.schemas import (
    RunSummary, RunDetail, OpenItem, Match,
    TriggerRunRequest, TriggerRunResponse, DashboardStats,
)
from app.tasks import run_engine_task

router = APIRouter()


@router.get("/", response_model=list[RunSummary])
def list_runs(_: AnyUser):
    return db.run_list()


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(_: AnyUser):
    runs = db.run_list()
    latest: dict[str, dict] = {}
    for r in runs:
        if r["account_id"] not in latest:
            latest[r["account_id"]] = r

    current = list(latest.values())
    reconciled   = sum(1 for r in current if r["status"] == "RECONCILED")
    unreconciled = sum(1 for r in current if r["status"] == "UNRECONCILED")
    pending      = sum(1 for r in current if not r["signed_at"] and r["status"] == "RECONCILED")

    open_counts = {
        r["run_id"]: len(db.run_open_items(r["run_id"]))
        for r in current
    }
    total_open = sum(open_counts.values())

    return DashboardStats(
        total_accounts=len(latest),
        reconciled_count=reconciled,
        unreconciled_count=unreconciled,
        pending_signoff=pending,
        open_items_count=total_open,
        high_alerts=unreconciled,
        runs=[RunSummary(**r) for r in current],
    )


@router.post("/", response_model=TriggerRunResponse)
def trigger_run(body: TriggerRunRequest, bg: BackgroundTasks, user: CanTriggerRun):
    """Trigger a reconciliation run in the background."""
    if not body.account_ids:
        raise HTTPException(400, "account_ids is required")

    job_id = str(uuid.uuid4())[:8]
    bg.add_task(run_engine_task, body.account_ids, body.period, body.maker or user.name)

    return TriggerRunResponse(
        job_id=job_id,
        status="QUEUED",
        message=f"Run queued for {', '.join(body.account_ids)} · period {body.period}. "
                "Refresh /api/runs in a few seconds to see results.",
    )


@router.get("/{run_id}/proposed", summary="Proposed matches with transaction detail")
def get_proposed_matches(run_id: str, _: AnyUser):
    """Returns PROPOSED matches with full bank and book transaction payloads attached."""
    run = db.run_get(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    matches = [m for m in db.run_matches(run_id) if m["status"] == "PROPOSED"]
    if not matches:
        return []

    # Build a uid → txn payload lookup from open_items + all items stored
    all_items = db.run_open_items(run_id)
    by_uid = {item["uid"]: item for item in all_items}

    result = []
    for m in matches:
        bank_txns = [by_uid[u] for u in m["bank_uids"] if u in by_uid]
        book_txns = [by_uid[u] for u in m["book_uids"] if u in by_uid]
        result.append({**m, "bank_txns": bank_txns, "book_txns": book_txns})
    return result


@router.get("/{run_id}/journals", summary="Draft journals for a run")
def get_run_journals(run_id: str, _: AnyUser):
    run = db.run_get(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    return db.run_journals_list(run_id)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, _: AnyUser):
    run = db.run_get(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    open_bank = [OpenItem(**t) for t in db.run_open_items(run_id) if t["side"] == "BANK"]
    open_book = [OpenItem(**t) for t in db.run_open_items(run_id) if t["side"] == "BOOK"]
    matches   = [Match(**m) for m in db.run_matches(run_id)]

    stats = {
        "open_bank_count": len(open_bank),
        "open_book_count": len(open_book),
        "auto_matched":    sum(1 for m in matches if m.status == "AUTO"),
        "proposed":        sum(1 for m in matches if m.status == "PROPOSED"),
        "auto_match_rate": round(
            sum(1 for m in matches if m.status in ("AUTO", "APPROVED")) / max(len(matches), 1), 4
        ),
    }

    return RunDetail(**run, open_bank=open_bank, open_book=open_book, matches=matches, stats=stats)


@router.get("/{run_id}/export")
def export_run_csv(run_id: str, _: AnyUser):
    """Export all open (unmatched) items for a run as a CSV download."""
    run = db.run_get(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    open_items = db.run_open_items(run_id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Side", "Date", "Amount (NGN)", "Description", "Reference", "Source", "UID"
    ])
    for t in open_items:
        writer.writerow([
            t.get("side", ""),
            t.get("txn_date", ""),
            f"{t.get('amount', 0) / 100:.2f}",
            t.get("description", ""),
            t.get("reference", ""),
            t.get("source", ""),
            t.get("uid", ""),
        ])

    filename = f"open_items_{run_id[:8]}_{run.get('period_end', 'unknown')[:7]}.csv"
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
