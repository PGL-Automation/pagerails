"""
payouts.py — PageRails payout approval router.

Handles the full lifecycle of a payment instruction:
  draft → submitted → (approval chain) → approved → sent_to_bank → confirmed

Routing, step generation, and instruction ID generation are delegated to
app.approval_chain.  PDF / HTML letter generation is delegated to app.pdf_letter.
"""

from __future__ import annotations

import logging
import os
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app import db
from app.approval_chain import build_steps, generate_instruction_id, get_entity_code
from app.auth import (
    AnyUser,
    TokenData,
    current_user,
    require_permission,
)
from app.config import settings
from app import pdf_letter

logger = logging.getLogger(__name__)

router = APIRouter()

# Typed permission dependencies
CanRaisePayout   = Annotated[TokenData, Depends(require_permission("raise_payout"))]
CanApprovePayout = Annotated[TokenData, Depends(require_permission("approve_payout"))]
CanPayPayout     = Annotated[TokenData, Depends(require_permission("pay_payout"))]
CanConfirmPayout = Annotated[TokenData, Depends(require_permission("confirm_payout"))]


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _frontend_url() -> str:
    return getattr(settings, "frontend_url", "https://recon.pagecapital.ng")


# ---------------------------------------------------------------------------
# Email notification
# ---------------------------------------------------------------------------

# Shared mailbox all approval emails are sent FROM.
# Replies to this address are picked up by the email poller.
_APPROVALS_MAILBOX = os.getenv("PAGEOS_APPROVALS_EMAIL_USER", "approvals@pageaml.com")

# Lazy-init Graph client (reused across requests)
_graph_client: "GraphMailClient | None" = None

def _graph() -> "GraphMailClient":
    global _graph_client
    if _graph_client is None:
        from app.graphmail import GraphMailClient
        _graph_client = GraphMailClient.from_env()
    return _graph_client


def _notify(to: str, subject: str, body: str) -> None:
    """
    Send an approval notification email.

    Transport priority:
      1. Microsoft Graph (send from approvals@pageaml.com) — preferred.
         Replies from the recipient go to approvals@pageaml.com and are
         picked up by the APPROVE/REJECT email poller.
      2. SMTP fallback if smtp_host is set in settings.
      3. Console log if neither is configured (local dev without credentials).
    """
    graph = _graph()
    if graph.configured:
        try:
            graph.send_mail(
                from_mailbox=_APPROVALS_MAILBOX,
                to_address=to,
                subject=subject,
                body_text=body,
            )
            logger.info("[email/graph] Sent to %s: %s", to, subject)
            return
        except Exception as exc:
            logger.warning("[email/graph] Failed for %s: %s — trying SMTP", to, exc)

    # SMTP fallback
    smtp_host = getattr(settings, "smtp_host", None)
    if smtp_host:
        smtp_port = getattr(settings, "smtp_port", 587)
        smtp_user = getattr(settings, "smtp_user", None)
        smtp_pass = getattr(settings, "smtp_pass", None)
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"]    = smtp_user or _APPROVALS_MAILBOX
            msg["To"]      = to
            msg.set_content(body)
            with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
                server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            logger.info("[email/smtp] Sent to %s: %s", to, subject)
            return
        except Exception as exc:
            logger.warning("[email/smtp] Failed for %s: %s", to, exc)

    # Console fallback (local dev)
    logger.info("[email/console] TO=%s\nSUBJECT=%s\n%s", to, subject, body)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class RaisePayoutBody(BaseModel):
    entity: str
    request_type: str
    payment_account_id: int
    amount_kobo: int
    beneficiary_name: str
    beneficiary_bank: str
    beneficiary_account: str
    purpose: str


class ApproveBody(BaseModel):
    notes: Optional[str] = ""


class ReturnBody(BaseModel):
    notes: str


class RejectBody(BaseModel):
    notes: str


class DispatchBody(BaseModel):
    bank_reference: str


class ConfirmBody(BaseModel):
    confirmation_doc_path: str


class BeneficiaryCheckBody(BaseModel):
    entity: str
    account_number: str


# ---------------------------------------------------------------------------
# Route ordering note:
#   FastAPI matches routes in registration order.
#   Static path segments (/pending, /accounts, /beneficiaries) must be
#   registered BEFORE the /{request_id} catch-all to avoid shadowing.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# POST /  — raise (create draft)
# ---------------------------------------------------------------------------

@router.post("")
def raise_payout(body: RaisePayoutBody, user: CanRaisePayout):
    """Create a draft payment request."""
    now = _now()
    request_id = str(uuid.uuid4())

    data = {
        "id":                    request_id,
        "instruction_id":        None,
        "entity":                get_entity_code(body.entity),
        "request_type":          body.request_type,
        "payment_account_id":    body.payment_account_id,
        "amount_kobo":           body.amount_kobo,
        "beneficiary_name":      body.beneficiary_name,
        "beneficiary_bank":      body.beneficiary_bank,
        "beneficiary_account":   body.beneficiary_account,
        "purpose":               body.purpose,
        "supporting_doc_path":   "",
        "status":                "draft",
        "compliance_flagged":    0,
        "raised_by":             user.email,
        "submitted_at":          None,
        "approved_at":           None,
        "bank_reference":        "",
        "confirmation_doc_path": "",
        "created_at":            now,
        "updated_at":            now,
    }

    request = db.payout_create(data)

    db.payout_log_action({
        "id":          str(uuid.uuid4()),
        "request_id":  request_id,
        "step_id":     None,
        "actor_email": user.email,
        "action":      "created",
        "notes":       "",
        "source":      "web",
        "created_at":  now,
    })

    return request


# ---------------------------------------------------------------------------
# GET /  — list requests
# ---------------------------------------------------------------------------

@router.get("")
def list_payouts(
    user: AnyUser,
    entity: Optional[str] = None,
    status: Optional[str] = None,
    mine: bool = False,
):
    """List payment requests with optional filters."""
    raised_by = user.email if mine else None
    return db.payout_list(entity=entity, status=status, raised_by=raised_by)


# ---------------------------------------------------------------------------
# GET /pending  — steps awaiting current user
#   Must be registered before /{request_id}
# ---------------------------------------------------------------------------

@router.get("/pending")
def pending_for_me(user: AnyUser):
    """Return all approval steps currently assigned to the authenticated user."""
    return db.payout_pending_for_user(user.email)


# ---------------------------------------------------------------------------
# GET /accounts
#   Must be registered before /{request_id}
# ---------------------------------------------------------------------------

@router.get("/accounts")
def list_accounts(
    user: AnyUser,
    entity: Optional[str] = None,
):
    """Return payment accounts, optionally filtered by entity."""
    return db.payout_list_accounts(entity=entity)


# ---------------------------------------------------------------------------
# GET /beneficiaries
#   Must be registered before /{request_id}
# ---------------------------------------------------------------------------

@router.get("/beneficiaries")
def list_beneficiaries(
    user: AnyUser,
    entity: Optional[str] = None,
):
    """Return registered client beneficiaries."""
    with db.get_db() as con:
        if entity:
            rows = con.execute(
                "SELECT * FROM client_beneficiaries WHERE entity=? AND is_active=1 ORDER BY client_name",
                (entity,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM client_beneficiaries WHERE is_active=1 ORDER BY entity, client_name"
            ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# POST /beneficiaries/check
#   Must be registered before /{request_id}
# ---------------------------------------------------------------------------

@router.post("/beneficiaries/check")
def check_beneficiary(body: BeneficiaryCheckBody, user: AnyUser):
    """Check whether an account number is on the registered beneficiary list."""
    on_register = db.payout_check_beneficiary(
        get_entity_code(body.entity), body.account_number
    )
    return {"on_register": on_register}


# ---------------------------------------------------------------------------
# GET /{request_id}/verify-chain  — SHA-256 chain integrity check
#   Must be registered before /{request_id} to avoid route shadowing.
#   FastAPI resolves this correctly because the path has a static suffix.
# ---------------------------------------------------------------------------

@router.get("/{request_id}/verify-chain")
def verify_chain(request_id: str, user: AnyUser):
    """Verify the SHA-256 tamper-evident chain for a payout request's action log."""
    entries = db.payout_get_action_log(request_id)
    intact  = db.payout_verify_chain(request_id)
    return {"intact": intact, "entries": len(entries)}


# ---------------------------------------------------------------------------
# GET /{request_id}  — full detail
# ---------------------------------------------------------------------------

@router.get("/{request_id}")
def get_payout(request_id: str, user: AnyUser):
    """Return full payout request detail: request, steps, and action log."""
    request = db.payout_get(request_id)
    if not request:
        raise HTTPException(404, "Payment request not found")
    steps = db.payout_get_steps(request_id)
    log   = db.payout_get_action_log(request_id)
    return {"request": request, "steps": steps, "log": log}


# ---------------------------------------------------------------------------
# POST /{request_id}/submit
# ---------------------------------------------------------------------------

@router.post("/{request_id}/submit")
def submit_payout(request_id: str, user: CanRaisePayout):
    """Submit a draft request into the approval workflow."""
    request = db.payout_get(request_id)
    if not request:
        raise HTTPException(404, "Payment request not found")
    if request["status"] != "draft":
        raise HTTPException(400, f"Request is not in draft status (current: {request['status']})")
    if request["raised_by"] != user.email:
        raise HTTPException(403, "You can only submit your own requests")

    now_dt = datetime.now(timezone.utc)
    now    = now_dt.isoformat(timespec="seconds")
    entity = get_entity_code(request["entity"])
    year   = now_dt.year

    # Check beneficiary register
    on_register = db.payout_check_beneficiary(entity, request["beneficiary_account"])
    compliance_flagged = 0 if on_register else 1

    # Generate instruction_id
    seq = db.payout_count_for_year(entity, year) + 1
    instruction_id = generate_instruction_id(entity, year, seq)

    # Build step chain
    chain_input = {
        "request_id":             request_id,
        "request_type":           request["request_type"],
        "entity":                 entity,
        "amount_kobo":            request["amount_kobo"],
        "beneficiary_registered": on_register,
    }
    steps = build_steps(chain_input, now=now_dt)

    # Insert steps
    for step in steps:
        step.setdefault("stand_in_for", None)
        step.setdefault("reminder_sent_at", None)
        step.setdefault("escalated_at", None)
        step.setdefault("decided_at", None)
        step.setdefault("notes", "")
        db.payout_create_step(step)

    # Determine initial status from first active (non-skipped) step
    first_active = next((s for s in steps if s["status"] == "pending"), None)
    new_status = first_active["step_type"] if first_active else "approved"

    db.payout_update(
        request_id,
        instruction_id=instruction_id,
        compliance_flagged=compliance_flagged,
        status=new_status,
        submitted_at=now,
    )

    db.payout_log_action({
        "id":          str(uuid.uuid4()),
        "request_id":  request_id,
        "step_id":     None,
        "actor_email": user.email,
        "action":      "submitted",
        "notes":       f"instruction_id={instruction_id}",
        "source":      "web",
        "created_at":  now,
    })

    # Notify first assignee
    if first_active and first_active.get("assigned_to"):
        link = f"{_frontend_url()}/payouts/{request_id}"
        amount_ngn = f"₦{request['amount_kobo'] / 100:,.2f}"
        _notify(
            to=first_active["assigned_to"],
            subject=f"[{instruction_id}] Approve: {amount_ngn} to {request['beneficiary_name']}",
            body=(
                f"A payment instruction requires your action.\n\n"
                f"Reference:   {instruction_id}\n"
                f"Type:        {request['request_type'].replace('_', ' ').title()}\n"
                f"Amount:      {amount_ngn}\n"
                f"Beneficiary: {request['beneficiary_name']} – {request['beneficiary_bank']} {request['beneficiary_account']}\n"
                f"Purpose:     {request['purpose']}\n"
                f"Your step:   {first_active['step_type'].replace('_', ' ').title()}\n"
                f"Due by:      {first_active['due_by']}\n\n"
                f"Open in PageRails:\n{link}\n\n"
                f"── Reply by email ───────────────────────────────────────────\n"
                f"Reply to this email with ONE of the following:\n\n"
                f"  APPROVE\n"
                f"  REJECT  followed by your reason\n"
                f"  RETURN  followed by what needs to change\n\n"
                f"Your reply is recorded with your name and timestamp.\n"
                f"You cannot act on your own request.\n"
            ),
        )

    return db.payout_get(request_id)


# ---------------------------------------------------------------------------
# POST /{request_id}/approve
# ---------------------------------------------------------------------------

@router.post("/{request_id}/approve")
def approve_payout(
    request_id: str,
    user: CanApprovePayout,
    body: ApproveBody = ApproveBody(),
):
    """Approve the current active step."""
    request = db.payout_get(request_id)
    if not request:
        raise HTTPException(404, "Payment request not found")

    step = db.payout_get_active_step(request_id)
    if not step:
        raise HTTPException(400, "No pending approval step for this request")

    if step["assigned_to"] != user.email:
        raise HTTPException(403, "This step is not assigned to you")
    if request["raised_by"] == user.email:
        raise HTTPException(403, "You cannot approve your own request")

    now = _now()

    db.payout_update_step(
        step["id"],
        status="approved",
        decided_at=now,
        notes=body.notes or "",
    )

    db.payout_log_action({
        "id":          str(uuid.uuid4()),
        "request_id":  request_id,
        "step_id":     step["id"],
        "actor_email": user.email,
        "action":      "approved",
        "notes":       body.notes or "",
        "source":      "web",
        "created_at":  now,
    })

    # Advance to next pending step
    next_step = db.payout_get_active_step(request_id)
    inst_id    = request.get("instruction_id", request_id)
    amount_ngn = f"₦{request['amount_kobo'] / 100:,.2f}"
    link       = f"{_frontend_url()}/payouts/{request_id}"

    if next_step:
        db.payout_update(request_id, status=next_step["step_type"])
        _notify(
            to=next_step["assigned_to"],
            subject=f"[{inst_id}] Approve: {amount_ngn} to {request['beneficiary_name']}",
            body=(
                f"A payment instruction requires your action.\n\n"
                f"Reference:   {inst_id}\n"
                f"Type:        {request['request_type'].replace('_', ' ').title()}\n"
                f"Amount:      {amount_ngn}\n"
                f"Beneficiary: {request['beneficiary_name']} – {request['beneficiary_bank']} {request['beneficiary_account']}\n"
                f"Purpose:     {request['purpose']}\n"
                f"Your step:   {next_step['step_type'].replace('_', ' ').title()}\n"
                f"Due by:      {next_step['due_by']}\n\n"
                f"Open in PageRails:\n{link}\n\n"
                f"── Reply by email ───────────────────────────────────────────\n"
                f"Reply to this email with ONE of the following:\n\n"
                f"  APPROVE\n"
                f"  REJECT  followed by your reason\n"
                f"  RETURN  followed by what needs to change\n\n"
                f"Your reply is recorded with your name and timestamp.\n"
            ),
        )
    else:
        # All steps done — fully approved
        db.payout_update(request_id, status="approved", approved_at=now)
        _notify(
            to=request["raised_by"],
            subject=f"[{inst_id}] APPROVED – {amount_ngn} to {request['beneficiary_name']}",
            body=(
                f"Your payment instruction has been fully approved.\n\n"
                f"Reference:   {inst_id}\n"
                f"Type:        {request['request_type'].replace('_', ' ').title()}\n"
                f"Amount:      {amount_ngn}\n"
                f"Beneficiary: {request['beneficiary_name']} – {request['beneficiary_bank']} {request['beneficiary_account']}\n\n"
                f"Next step: Send to bank with the narration:\n"
                f"  {inst_id}\n\n"
                f"Open bank instruction letter:\n{link}/letter\n\n"
                f"View in PageRails:\n{link}\n"
            ),
        )

    return db.payout_get(request_id)


# ---------------------------------------------------------------------------
# POST /{request_id}/return
# ---------------------------------------------------------------------------

@router.post("/{request_id}/return")
def return_payout(
    request_id: str,
    body: ReturnBody,
    user: CanApprovePayout,
):
    """Return (send back) the current step to the raiser."""
    request = db.payout_get(request_id)
    if not request:
        raise HTTPException(404, "Payment request not found")

    step = db.payout_get_active_step(request_id)
    if not step:
        raise HTTPException(400, "No pending approval step for this request")

    if step["assigned_to"] != user.email:
        raise HTTPException(403, "This step is not assigned to you")
    if request["raised_by"] == user.email:
        raise HTTPException(403, "You cannot act on your own request")

    now = _now()

    db.payout_update_step(step["id"], status="returned", decided_at=now, notes=body.notes)
    db.payout_update(request_id, status="returned")

    db.payout_log_action({
        "id":          str(uuid.uuid4()),
        "request_id":  request_id,
        "step_id":     step["id"],
        "actor_email": user.email,
        "action":      "returned",
        "notes":       body.notes,
        "source":      "web",
        "created_at":  now,
    })

    _inst_id   = request.get("instruction_id", request_id)
    _amount_ngn = f"₦{request['amount_kobo'] / 100:,.2f}"
    _notify(
        to=request["raised_by"],
        subject=f"[{_inst_id}] RETURNED – {_amount_ngn} to {request['beneficiary_name']}",
        body=(
            f"Your payment instruction has been returned.\n\n"
            f"Reference: {_inst_id}\n"
            f"Returned by: {user.email}\n"
            f"Notes: {body.notes}\n\n"
            f"View at: {_frontend_url()}/payouts/{request_id}\n"
        ),
    )

    return db.payout_get(request_id)


# ---------------------------------------------------------------------------
# POST /{request_id}/reject
# ---------------------------------------------------------------------------

@router.post("/{request_id}/reject")
def reject_payout(
    request_id: str,
    body: RejectBody,
    user: CanApprovePayout,
):
    """Reject the payment request outright."""
    request = db.payout_get(request_id)
    if not request:
        raise HTTPException(404, "Payment request not found")

    step = db.payout_get_active_step(request_id)
    now = _now()

    if step:
        db.payout_update_step(step["id"], status="rejected", decided_at=now, notes=body.notes)

    db.payout_update(request_id, status="rejected")

    db.payout_log_action({
        "id":          str(uuid.uuid4()),
        "request_id":  request_id,
        "step_id":     step["id"] if step else None,
        "actor_email": user.email,
        "action":      "rejected",
        "notes":       body.notes,
        "source":      "web",
        "created_at":  now,
    })

    _rej_inst_id   = request.get("instruction_id", request_id)
    _rej_amount_ngn = f"₦{request['amount_kobo'] / 100:,.2f}"
    _notify(
        to=request["raised_by"],
        subject=f"[{_rej_inst_id}] REJECTED – {_rej_amount_ngn} to {request['beneficiary_name']}",
        body=(
            f"Your payment instruction has been rejected.\n\n"
            f"Reference: {_rej_inst_id}\n"
            f"Rejected by: {user.email}\n"
            f"Reason: {body.notes}\n\n"
            f"View at: {_frontend_url()}/payouts/{request_id}\n"
        ),
    )

    return db.payout_get(request_id)


# ---------------------------------------------------------------------------
# POST /{request_id}/dispatch
# ---------------------------------------------------------------------------

@router.post("/{request_id}/dispatch")
def dispatch_payout(
    request_id: str,
    body: DispatchBody,
    user: CanPayPayout,
):
    """Mark an approved request as sent to bank."""
    request = db.payout_get(request_id)
    if not request:
        raise HTTPException(404, "Payment request not found")
    if request["status"] != "approved":
        raise HTTPException(
            400,
            f"Request must be approved before dispatch (current: {request['status']})",
        )

    now = _now()

    db.payout_update(request_id, bank_reference=body.bank_reference, status="sent_to_bank")

    db.payout_log_action({
        "id":          str(uuid.uuid4()),
        "request_id":  request_id,
        "step_id":     None,
        "actor_email": user.email,
        "action":      "dispatched",
        "notes":       f"bank_reference={body.bank_reference}",
        "source":      "web",
        "created_at":  now,
    })

    return db.payout_get(request_id)


# ---------------------------------------------------------------------------
# POST /{request_id}/confirm
# ---------------------------------------------------------------------------

@router.post("/{request_id}/confirm")
def confirm_payout(
    request_id: str,
    body: ConfirmBody,
    user: CanConfirmPayout,
):
    """Attach bank confirmation and mark request as confirmed."""
    request = db.payout_get(request_id)
    if not request:
        raise HTTPException(404, "Payment request not found")
    if request["status"] != "sent_to_bank":
        raise HTTPException(
            400,
            f"Request must be in sent_to_bank status (current: {request['status']})",
        )

    now = _now()

    db.payout_update(
        request_id,
        confirmation_doc_path=body.confirmation_doc_path,
        status="confirmed",
    )

    db.payout_log_action({
        "id":          str(uuid.uuid4()),
        "request_id":  request_id,
        "step_id":     None,
        "actor_email": user.email,
        "action":      "confirmed",
        "notes":       f"doc={body.confirmation_doc_path}",
        "source":      "web",
        "created_at":  now,
    })

    return db.payout_get(request_id)


# ---------------------------------------------------------------------------
# GET /{request_id}/letter
# ---------------------------------------------------------------------------

@router.get("/{request_id}/letter", response_class=HTMLResponse)
def get_payout_letter(request_id: str, user: AnyUser):
    """Generate and return a printable A4 bank instruction letter as HTML."""
    request = db.payout_get(request_id)
    if not request:
        raise HTTPException(404, "Payment request not found")

    account: dict = {}
    if request.get("payment_account_id"):
        fetched = db.payout_get_account(int(request["payment_account_id"]))
        if fetched:
            account = fetched

    html = pdf_letter.generate_letter(request, account)
    return HTMLResponse(content=html, media_type="text/html")


# ---------------------------------------------------------------------------
# POST /{request_id}/document  — attach supporting document
# ---------------------------------------------------------------------------

_DOC_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".xlsx", ".xls", ".csv", ".docx"}
_DOC_MAX_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/{request_id}/document")
async def upload_payout_document(
    request_id: str,
    file: UploadFile = File(...),
    user: CanRaisePayout = None,  # type: ignore[assignment]
):
    """
    Attach a supporting document to a payment request.

    The request must exist and be in draft or returned status,
    and must belong to the authenticated user.
    Accepted types: .pdf .jpg .jpeg .png .xlsx .xls .csv .docx
    Max size: 10 MB.
    """
    request = db.payout_get(request_id)
    if not request:
        raise HTTPException(404, "Payment request not found")
    if request["raised_by"] != user.email:
        raise HTTPException(403, "You can only attach documents to your own requests")
    _TERMINAL_STATUSES = {"rejected", "confirmed"}
    if request["status"] in _TERMINAL_STATUSES:
        raise HTTPException(
            400,
            f"Cannot attach documents to a {request['status']} request",
        )

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in _DOC_ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' is not allowed. Allowed: {', '.join(sorted(_DOC_ALLOWED_EXTENSIONS))}")

    data = await file.read()
    if len(data) > _DOC_MAX_SIZE:
        raise HTTPException(400, f"{file.filename} exceeds the 10 MB limit")

    # Save to uploads/payouts/{request_id}/{original_filename}
    dest_dir = settings.uploads_dir() / "payouts" / request_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / file.filename
    dest.write_bytes(data)

    # Store a relative path (relative to uploads_dir root)
    relative_path = f"payouts/{request_id}/{file.filename}"

    db.payout_update(request_id, supporting_doc_path=relative_path)

    now = _now()
    db.payout_log_action({
        "id":          str(uuid.uuid4()),
        "request_id":  request_id,
        "step_id":     None,
        "actor_email": user.email,
        "action":      "document_uploaded",
        "notes":       f"filename={file.filename} size={len(data)}",
        "source":      "web",
        "created_at":  now,
    })

    logger.info(
        "[payout/document] request=%s file=%s size=%d uploaded_by=%s",
        request_id, file.filename, len(data), user.email,
    )

    return {"path": relative_path, "filename": file.filename}
