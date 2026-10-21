"""
payout_scheduler.py — APScheduler jobs for the PageRails payout system.

Two jobs are registered here and wired into the main BackgroundScheduler:

  check_payout_timeouts()
      Polls overdue approval steps every minute.
      - At 1× step limit  → send reminder email, mark reminder_sent_at
      - At 2× step limit  → escalate to stand-in (or urgent repeat if none)

  check_recon_instruction_ids()
      Runs after every reconciliation sign-off (or on a periodic schedule).
      Scans open_items for instruction IDs embedded in narration/description
      and auto-confirms or flags mismatches.

Email sending: uses smtplib if PAGEOS_SMTP_* env vars are set; falls back
to console print so the code is safe in dev/CI with no mail server.
"""
from __future__ import annotations

import os
import re
import smtplib
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

from apscheduler.triggers.cron import CronTrigger

from app import db

TIMEZONE = "Africa/Lagos"

# ---------------------------------------------------------------------------
# Step time-limit lookup
# ---------------------------------------------------------------------------

# Minutes per (request_type, step_type) tuple.
# "payment" covers: client_payout | liquidation | transfer
_STEP_LIMITS: dict[tuple[str, str], int] = {
    # Payment types — 20 min per step
    ("payment", "head_concur"):      20,
    ("payment", "internal_control"): 20,
    ("payment", "compliance"):       20,
    ("payment", "finance"):          20,
    ("payment", "signatory_1"):      20,
    ("payment", "signatory_2"):      20,
    # Placement — 20 min per step
    ("placement", "head_concur"):      20,
    ("placement", "internal_control"): 20,
    ("placement", "finance"):          20,
    ("placement", "md"):               20,
    # Expense — mixed
    ("expense", "head_concur"):      240,  # 4 h
    ("expense", "internal_control"): 240,  # 4 h
    ("expense", "finance"):          480,  # 8 h
    ("expense", "md"):               480,  # 8 h
    ("expense", "ceo"):              480,  # 8 h
}

_PAYMENT_TYPES = {"client_payout", "liquidation", "transfer"}

INSTRUCTION_ID_RE = re.compile(r"[A-Z]{2,3}-APR-\d{4}-\d{6}")


def _step_limit_minutes(request_type: str, step_type: str) -> int:
    """Return the configured step-limit in minutes for a given request + step combination."""
    rtype = request_type.strip().lower()
    bucket = "payment" if rtype in _PAYMENT_TYPES else rtype
    return _STEP_LIMITS.get((bucket, step_type), 20)  # default 20 min


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------

_SMTP_HOST = os.getenv("PAGEOS_SMTP_HOST", "")
_SMTP_PORT = int(os.getenv("PAGEOS_SMTP_PORT", "587"))
_SMTP_USER = os.getenv("PAGEOS_SMTP_USER", "")
_SMTP_PASS = os.getenv("PAGEOS_SMTP_PASS", "")
_SMTP_FROM = os.getenv("PAGEOS_SMTP_FROM", "pagerecon@pageaml.com")


def _send_email(to: str | list[str], subject: str, body: str) -> None:
    """
    Send an email via SMTP if credentials are configured; otherwise print.
    `to` may be a single address string or a list of addresses.
    """
    recipients: list[str] = [to] if isinstance(to, str) else list(to)
    tag = f"[payout_scheduler] EMAIL → {recipients} | {subject}"

    if not (_SMTP_HOST and _SMTP_USER and _SMTP_PASS):
        print(f"{tag}\n{body}\n")
        return

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = _SMTP_FROM
    msg["To"] = ", ".join(recipients)

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(_SMTP_USER, _SMTP_PASS)
            smtp.sendmail(_SMTP_FROM, recipients, msg.as_string())
    except Exception as exc:  # noqa: BLE001
        print(f"[payout_scheduler] SMTP error: {exc}")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_str() -> str:
    return _now_utc().isoformat(timespec="seconds")


def _parse_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Finance / MD emails for alert escalation (loaded from approval_roles.yaml)
# ---------------------------------------------------------------------------

def _get_role_email(entity: str, role: str) -> str | None:
    """Thin wrapper around db.payout_get_approver for clarity."""
    return db.payout_get_approver(entity, role)


def _finance_email(entity: str) -> str | None:
    return _get_role_email(entity, "finance")


def _md_email(entity: str) -> str | None:
    return _get_role_email(entity, "md")


# ---------------------------------------------------------------------------
# Job 1: check_payout_timeouts
# ---------------------------------------------------------------------------

def check_payout_timeouts() -> None:
    """
    Scheduled task: reminder + escalation for overdue approval steps.

    Run frequency: every 1 minute (registered in scheduler.py / main.py).

    Logic per overdue step
    ----------------------
    Let L = step_limit_minutes(request_type, step_type) in minutes.

    Phase 1 — reminder (at 1× limit):
        If reminder_sent_at is None AND now > due_by:
            Send reminder email to assigned_to.
            Set reminder_sent_at = now.

    Phase 2 — escalation (at 2× limit, i.e. due_by + L minutes ago):
        If escalated_at is None AND now > due_by + L minutes:
            Look up stand-in for assigned_to.
            If stand-in found:
                Reassign step: assigned_to = stand_in, stand_in_for = original.
                Set escalated_at = now.
                Notify both original and stand-in.
            Else:
                Send urgent reminder to original (no stand-in configured).
    """
    try:
        overdue = db.payout_get_overdue_steps()
    except Exception as exc:
        print(f"[check_payout_timeouts] DB error fetching overdue steps: {exc}")
        return

    now = _now_utc()

    for step in overdue:
        try:
            _process_overdue_step(step, now)
        except Exception as exc:
            print(f"[check_payout_timeouts] Error processing step {step.get('step_id')}: {exc}")
            traceback.print_exc()


def _process_overdue_step(step: dict, now: datetime) -> None:
    step_id       = step["step_id"]
    request_id    = step["request_id"]
    step_type     = step["step_type"]
    assigned_to   = step["assigned_to"]
    instruction_id = step.get("instruction_id", request_id)
    request_type  = step.get("request_type", "")

    # Fetch request_type from payment_requests if not in the joined row
    if not request_type:
        req = db.payout_get(request_id)
        request_type = (req or {}).get("request_type", "client_payout")

    due_by_dt       = _parse_dt(step["due_by"])
    reminder_sent   = _parse_dt(step.get("reminder_sent_at"))
    escalated_at    = _parse_dt(step.get("escalated_at"))

    if due_by_dt is None:
        return  # malformed row — skip

    limit_minutes = _step_limit_minutes(request_type, step_type)
    escalation_threshold = due_by_dt + timedelta(minutes=limit_minutes)

    # ── Phase 1: Reminder ────────────────────────────────────────────────────
    if reminder_sent is None and now > due_by_dt:
        _send_reminder(
            to=assigned_to,
            instruction_id=instruction_id,
            step_type=step_type,
            due_by=step["due_by"],
        )
        db.payout_update_step(step_id, reminder_sent_at=_now_str())
        print(
            f"[check_payout_timeouts] Reminder sent → {assigned_to} "
            f"for step {step_type} on {instruction_id}"
        )

    # ── Phase 2: Escalation ──────────────────────────────────────────────────
    if escalated_at is None and now > escalation_threshold:
        original_assignee = assigned_to
        cover = db.payout_get_standin(original_assignee)

        if cover:
            # Reassign the step to the stand-in
            db.payout_update_step(
                step_id,
                assigned_to=cover,
                stand_in_for=original_assignee,
                escalated_at=_now_str(),
            )
            _send_escalation_original(
                to=original_assignee,
                cover=cover,
                instruction_id=instruction_id,
                step_type=step_type,
            )
            _send_escalation_standin(
                to=cover,
                original=original_assignee,
                instruction_id=instruction_id,
                step_type=step_type,
            )
            print(
                f"[check_payout_timeouts] Escalated {instruction_id}/{step_type} "
                f"from {original_assignee} → {cover}"
            )
        else:
            # No stand-in: send urgent reminder to original
            _send_urgent_reminder(
                to=original_assignee,
                instruction_id=instruction_id,
                step_type=step_type,
                overdue_by=int((now - due_by_dt).total_seconds() / 60),
            )
            print(
                f"[check_payout_timeouts] URGENT reminder sent → {original_assignee} "
                f"(no stand-in configured) for {instruction_id}/{step_type}"
            )


# ── Email templates ──────────────────────────────────────────────────────────

def _send_reminder(to: str, instruction_id: str, step_type: str, due_by: str) -> None:
    subject = f"[{instruction_id}] Reminder: your approval is overdue"
    body = (
        f"Dear Approver,\n\n"
        f"A payment instruction is awaiting your action:\n\n"
        f"  Instruction:  {instruction_id}\n"
        f"  Step:         {step_type}\n"
        f"  Due by:       {due_by}\n\n"
        f"Please log in to PageRails and approve or return the request.\n\n"
        f"This is an automated reminder. Do not reply to this email.\n"
    )
    _send_email(to, subject, body)


def _send_urgent_reminder(to: str, instruction_id: str, step_type: str, overdue_by: int) -> None:
    subject = f"[PageRails] URGENT — Overdue {instruction_id} ({step_type}, {overdue_by}m late)"
    body = (
        f"Dear Approver,\n\n"
        f"A payment instruction is CRITICALLY overdue and requires your IMMEDIATE attention:\n\n"
        f"  Instruction:  {instruction_id}\n"
        f"  Step:         {step_type}\n"
        f"  Overdue by:   {overdue_by} minutes\n\n"
        f"No stand-in has been configured for your role. "
        f"Please log in to PageRails immediately.\n\n"
        f"This is an automated urgent alert. Do not reply to this email.\n"
    )
    _send_email(to, subject, body)


def _send_escalation_original(to: str, cover: str, instruction_id: str, step_type: str) -> None:
    subject = f"[PageRails] Step Reassigned: {instruction_id} — {step_type}"
    body = (
        f"Dear Approver,\n\n"
        f"Because the following step was not actioned within the required timeframe, "
        f"it has been reassigned to your stand-in:\n\n"
        f"  Instruction:  {instruction_id}\n"
        f"  Step:         {step_type}\n"
        f"  Stand-in:     {cover}\n\n"
        f"Please coordinate with {cover} if you need to reclaim the step.\n\n"
        f"This is an automated notification. Do not reply to this email.\n"
    )
    _send_email(to, subject, body)


def _send_escalation_standin(to: str, original: str, instruction_id: str, step_type: str) -> None:
    subject = f"[PageRails] Stand-In Action Required: {instruction_id} — {step_type}"
    body = (
        f"Dear Stand-In,\n\n"
        f"You have been assigned as stand-in for the following overdue approval step:\n\n"
        f"  Instruction:  {instruction_id}\n"
        f"  Step:         {step_type}\n"
        f"  Original:     {original}\n\n"
        f"Please log in to PageRails and action this step as soon as possible.\n\n"
        f"This is an automated notification. Do not reply to this email.\n"
    )
    _send_email(to, subject, body)


# ---------------------------------------------------------------------------
# Job 2: check_recon_instruction_ids
# ---------------------------------------------------------------------------

def check_recon_instruction_ids() -> None:
    """
    Scheduled task: scan open_items for embedded payout instruction IDs.

    Run frequency: after every recon sign-off, or on a 15-minute schedule.

    For each instruction ID found in open_items:
      - If request exists AND status == 'sent_to_bank':
          Auto-confirm → reconciled.
      - If request exists AND amount mismatch:
          Alert finance approver.
          Log to connector_logs.
      - If no request found:
          Send URGENT alert to finance + MD.
          Log to connector_logs.
    """
    try:
        _scan_open_items_for_instruction_ids()
    except Exception as exc:
        print(f"[check_recon_instruction_ids] Fatal error: {exc}")
        traceback.print_exc()


def _scan_open_items_for_instruction_ids() -> None:
    """Inner implementation — separated for testability."""
    from app import db as _db

    # Fetch all open items across all runs
    with db.get_db() as con:
        rows = con.execute(
            """SELECT oi.uid, oi.run_id, oi.account_id, oi.payload
               FROM open_items oi
               ORDER BY oi.uid"""
        ).fetchall()

    if not rows:
        return

    processed: set[str] = set()

    for row in rows:
        try:
            import json as _json
            payload = _json.loads(row["payload"]) if row["payload"] else {}
        except Exception:
            payload = {}

        narration   = str(payload.get("narration", "") or "")
        description = str(payload.get("description", "") or "")
        reference   = str(payload.get("reference", "") or "")
        combined    = f"{narration} {description} {reference}"

        matches = INSTRUCTION_ID_RE.findall(combined)
        for instruction_id in matches:
            if instruction_id in processed:
                continue
            processed.add(instruction_id)
            _handle_instruction_match(instruction_id, payload, row["account_id"])


def _open_item_amount_ngn(payload: dict) -> float | None:
    """Extract the transaction amount from an open_item payload as NGN float."""
    for key in ("amount", "credit", "debit", "value"):
        val = payload.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def _handle_instruction_match(instruction_id: str, payload: dict, account_id: str) -> None:
    """Process a single instruction ID found in an open item."""
    # Look up the payment request
    with db.get_db() as con:
        row = con.execute(
            "SELECT * FROM payment_requests WHERE instruction_id=?",
            (instruction_id,),
        ).fetchone()

    if row is None:
        # No approval record found — flag URGENT
        _flag_no_approval(instruction_id, account_id, payload)
        return

    request = dict(row)
    status      = request["status"]
    amount_kobo = request["amount_kobo"]
    entity      = request["entity"]
    request_id  = request["id"]

    # Amount from open item (NGN) vs request (kobo)
    oi_amount_ngn = _open_item_amount_ngn(payload)
    req_amount_ngn = amount_kobo / 100 if amount_kobo else None

    amount_mismatch = (
        oi_amount_ngn is not None
        and req_amount_ngn is not None
        and abs(oi_amount_ngn - req_amount_ngn) > 0.01
    )

    if status == "sent_to_bank":
        if amount_mismatch:
            # Amount mismatch — flag before confirming
            _flag_amount_mismatch(
                instruction_id, request_id, entity,
                req_amount_ngn, oi_amount_ngn, account_id,
            )
            return

        # Auto-confirm → reconciled
        now = _now_str()

        # Update to confirmed
        db.payout_update(
            request_id,
            status="confirmed",
            confirmation_doc_path="auto:reconciliation",
        )
        db.payout_log_action({
            "id":          str(uuid.uuid4()),
            "request_id":  request_id,
            "step_id":     None,
            "actor_email": "scheduler:recon",
            "action":      "confirmed",
            "notes":       f"Auto-confirmed via reconciliation open item match ({account_id})",
            "source":      "scheduler",
            "created_at":  now,
        })

        # Update to reconciled
        db.payout_update(request_id, status="reconciled")
        db.payout_log_action({
            "id":          str(uuid.uuid4()),
            "request_id":  request_id,
            "step_id":     None,
            "actor_email": "scheduler:recon",
            "action":      "reconciled",
            "notes":       f"Auto-reconciled after bank statement match ({account_id})",
            "source":      "scheduler",
            "created_at":  now,
        })

        print(
            f"[check_recon_instruction_ids] Auto-reconciled {instruction_id} "
            f"(request {request_id}) — matched in {account_id}"
        )

    else:
        # Request exists but is not in sent_to_bank state — nothing to do
        print(
            f"[check_recon_instruction_ids] {instruction_id} found in open items "
            f"but request status is '{status}' — skipping auto-confirm"
        )


def _flag_no_approval(instruction_id: str, account_id: str, payload: dict) -> None:
    """Alert finance + MD when an instruction ID appears in bank statement but has no approval record."""
    detail = (
        f"Instruction ID '{instruction_id}' found in open_items (account: {account_id}) "
        f"but no matching payment_request exists in PageRails. "
        f"This may indicate an unauthorised payment.\n"
        f"Payload snapshot: {str(payload)[:300]}"
    )

    db.connector_log(
        connector="payout_recon_scanner",
        account_id=account_id,
        action="no_approval_flag",
        status="ERROR",
        detail=detail,
        triggered_by="scheduler:recon",
    )

    # Alert finance + MD for every entity (we don't know entity from the open item)
    for entity in ("PAM", "PCL"):
        recipients = [
            e for e in (_finance_email(entity), _md_email(entity)) if e
        ]
        if recipients:
            subject = f"[PageRails] URGENT: Unmatched Payment — {instruction_id}"
            body = (
                f"URGENT ALERT\n\n"
                f"A payment with instruction ID '{instruction_id}' was found in the bank statement "
                f"for account '{account_id}' but there is NO corresponding approval record in PageRails.\n\n"
                f"This may indicate an UNAUTHORISED PAYMENT.\n\n"
                f"Please investigate immediately.\n\n"
                f"Detected by: PageRails Reconciliation Scanner\n"
            )
            _send_email(recipients, subject, body)

    print(f"[check_recon_instruction_ids] NO-APPROVAL ALERT: {instruction_id} in {account_id}")


def _flag_amount_mismatch(
    instruction_id: str,
    request_id: str,
    entity: str,
    expected_ngn: float,
    actual_ngn: float,
    account_id: str,
) -> None:
    """Alert finance when the bank statement amount differs from the approved amount."""
    detail = (
        f"Amount mismatch for {instruction_id}: "
        f"approved ₦{expected_ngn:,.2f}, bank statement ₦{actual_ngn:,.2f} "
        f"(account: {account_id})"
    )

    db.connector_log(
        connector="payout_recon_scanner",
        account_id=account_id,
        action="amount_mismatch_flag",
        status="WARNING",
        detail=detail,
        triggered_by="scheduler:recon",
    )

    finance = _finance_email(entity)
    if finance:
        subject = f"[PageRails] Amount Mismatch: {instruction_id}"
        body = (
            f"AMOUNT MISMATCH ALERT\n\n"
            f"Instruction ID: {instruction_id}\n"
            f"Request ID:     {request_id}\n"
            f"Entity:         {entity}\n"
            f"Approved amount: ₦{expected_ngn:,.2f}\n"
            f"Bank statement:  ₦{actual_ngn:,.2f}\n"
            f"Account:         {account_id}\n\n"
            f"Please review and reconcile this discrepancy in PageRails.\n\n"
            f"Detected by: PageRails Reconciliation Scanner\n"
        )
        _send_email(finance, subject, body)

    print(
        f"[check_recon_instruction_ids] AMOUNT MISMATCH: {instruction_id} "
        f"expected ₦{expected_ngn:,.2f} got ₦{actual_ngn:,.2f}"
    )


# ---------------------------------------------------------------------------
# Scheduler registration
# ---------------------------------------------------------------------------

def register_payout_jobs(scheduler) -> None:
    """
    Register payout scheduler jobs into an existing APScheduler BackgroundScheduler.

    Call this from scheduler.start_scheduler() after loading accounts.

    Jobs registered:
      payout_timeout_check  — every 2 minutes (IntervalTrigger)
      payout_recon_scan     — daily at 08:30 Africa/Lagos (CronTrigger), runs after
                              the reconciliation auto-fetch to scan new open items
    """
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        check_payout_timeouts,
        trigger=IntervalTrigger(minutes=2),
        id="payout_timeout_check",
        replace_existing=True,
        name="Payout step timeout / escalation check",
        misfire_grace_time=120,
    )

    scheduler.add_job(
        check_recon_instruction_ids,
        trigger=CronTrigger(hour=8, minute=30, timezone=TIMEZONE),
        id="payout_recon_scan",
        replace_existing=True,
        name="Recon open-items → instruction ID scanner (08:30 Lagos)",
        misfire_grace_time=3600,
    )

    print("[scheduler] Registered payout jobs: payout_timeout_check (2m), payout_recon_scan (08:30 Africa/Lagos)")
