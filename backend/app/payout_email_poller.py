"""
payout_email_poller.py — Approval email poller for PageRails payout system.

Transport priority:
  1. Microsoft Graph API (app-only, preferred) — when PAGEOS_MSGRAPH_CLIENT_ID,
     PAGEOS_MSGRAPH_TENANT_ID and PAGEOS_MSGRAPH_CLIENT_SECRET are all set.
  2. Raw IMAP/TLS fallback — when PAGEOS_APPROVALS_IMAP_HOST is set.

Monitors approvals@pageaml.com for emails from approval-step assignees
and applies APPROVE / REJECT / RETURN actions directly via DB calls.

Required env vars (set in .env or environment):
  PAGEOS_APPROVALS_IMAP_HOST   e.g. imap.gmail.com or mail.pageaml.com
  PAGEOS_APPROVALS_EMAIL_USER  approvals@pageaml.com
  PAGEOS_APPROVALS_EMAIL_PASS  the mailbox password / app-password

If any of the three are absent, the poller logs a warning and returns
without starting a thread — safe in dev/CI.

Email protocol (what approvers send):
  Subject:  [any prefix] PAM-APR-2026-000001 [any suffix]
            The instruction ID anywhere in the subject is sufficient.

  Body (first non-blank, non-quoted line):
    APPROVE         — approve the current step
    REJECT          — reject the entire request
    RETURN          — return to the previous step / raiser

  The From address must match the step's assigned_to (case-insensitive).
  All other emails are marked SEEN and silently skipped.

Thread model:
  PayoutEmailPoller.start() spawns a daemon thread that calls poll()
  every POLL_INTERVAL_SECONDS (default 120) in a tight try/except loop.
  Errors in a single poll cycle are logged and the thread continues.
"""
from __future__ import annotations

import email as _email_mod
import imaplib
import os
import re
import ssl
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from email.header import decode_header as _decode_header

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

IMAP_HOST = os.getenv("PAGEOS_APPROVALS_IMAP_HOST", "")
IMAP_PORT = int(os.getenv("PAGEOS_APPROVALS_IMAP_PORT", "993"))
EMAIL_USER = os.getenv("PAGEOS_APPROVALS_EMAIL_USER", "")
EMAIL_PASS = os.getenv("PAGEOS_APPROVALS_EMAIL_PASS", "")

POLL_INTERVAL_SECONDS = int(os.getenv("PAGEOS_APPROVALS_POLL_INTERVAL", "120"))  # 2 minutes

INSTRUCTION_ID_RE = re.compile(r"([A-Z]{2,3}-APR-\d{4}-\d{6})")

# Recognised action keywords (first non-blank, non-quoted body line)
_APPROVE_WORDS = {"approve", "approved", "yes", "accept"}
_REJECT_WORDS  = {"reject", "rejected", "decline", "declined"}
_RETURN_WORDS  = {"return", "returned", "send back", "sendback"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decode_mime_header(raw: str) -> str:
    """Decode RFC 2047 encoded header value to plain text."""
    parts = _decode_header(raw or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_body_text(msg) -> str:
    """Walk a parsed email.Message and extract the first plain-text part."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def _first_action_line(body: str) -> str | None:
    """
    Return the first non-blank, non-quoted line of the body, lowercased.
    Quoted lines start with '>' (typical email reply convention).
    """
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            continue
        return stripped.lower()
    return None


def _classify_action(line: str | None) -> str | None:
    """Map a body line to 'approve' | 'reject' | 'return' | None."""
    if line is None:
        return None
    # strip punctuation for a clean keyword match
    clean = re.sub(r"[^\w\s]", "", line).strip()
    if clean in _APPROVE_WORDS:
        return "approve"
    if clean in _REJECT_WORDS:
        return "reject"
    if clean.replace(" ", "") in {w.replace(" ", "") for w in _RETURN_WORDS}:
        return "return"
    return None


# ---------------------------------------------------------------------------
# Core action logic (mirrors the payout router — shared DB calls)
# ---------------------------------------------------------------------------

def _apply_action(request_id: str, step: dict, actor_email: str, action: str) -> None:
    """
    Apply approve / reject / return to an approval step via direct DB writes.

    Guards enforced:
      - actor != raised_by
      - actor must be assigned_to (case-insensitive)  [already checked by caller]
      - action must be one of approve | reject | return
    """
    from app import db

    request = db.payout_get(request_id)
    if not request:
        print(f"[payout_email_poller] Request {request_id} not found")
        return

    if request["raised_by"].lower() == actor_email.lower():
        print(
            f"[payout_email_poller] {actor_email} cannot act on their own request "
            f"{request_id} — skipping"
        )
        return

    step_id = step["id"]
    now = _now_str()

    if action == "approve":
        # Mark this step approved
        db.payout_update_step(step_id, status="approved", decided_at=now)
        db.payout_log_action({
            "id":          str(uuid.uuid4()),
            "request_id":  request_id,
            "step_id":     step_id,
            "actor_email": actor_email,
            "action":      "approved",
            "notes":       "Approved via email reply",
            "source":      "email",
            "created_at":  now,
        })

        # Check if there's a next pending step
        all_steps = db.payout_get_steps(request_id)
        pending_after = [
            s for s in all_steps
            if s["status"] == "pending" and s["step_order"] > step["step_order"]
        ]

        if not pending_after:
            # All steps done — mark request as approved
            db.payout_update(request_id, status="approved", approved_at=now)
            db.payout_log_action({
                "id":          str(uuid.uuid4()),
                "request_id":  request_id,
                "step_id":     None,
                "actor_email": actor_email,
                "action":      "full_approval",
                "notes":       "All steps approved — request fully approved",
                "source":      "email",
                "created_at":  now,
            })
            print(
                f"[payout_email_poller] {request_id} FULLY APPROVED "
                f"after email from {actor_email}"
            )
        else:
            print(
                f"[payout_email_poller] Step {step['step_type']} approved by {actor_email} "
                f"on {request_id} — {len(pending_after)} step(s) remain"
            )

    elif action == "reject":
        # Mark step and request rejected
        db.payout_update_step(step_id, status="rejected", decided_at=now)
        db.payout_update(request_id, status="rejected")
        db.payout_log_action({
            "id":          str(uuid.uuid4()),
            "request_id":  request_id,
            "step_id":     step_id,
            "actor_email": actor_email,
            "action":      "rejected",
            "notes":       "Rejected via email reply",
            "source":      "email",
            "created_at":  now,
        })
        print(
            f"[payout_email_poller] {request_id} REJECTED by {actor_email} via email"
        )

    elif action == "return":
        # Mark step returned; reset request to pending_submission so raiser can edit
        db.payout_update_step(step_id, status="returned", decided_at=now)
        db.payout_update(request_id, status="pending_revision")
        db.payout_log_action({
            "id":          str(uuid.uuid4()),
            "request_id":  request_id,
            "step_id":     step_id,
            "actor_email": actor_email,
            "action":      "returned",
            "notes":       "Returned via email reply",
            "source":      "email",
            "created_at":  now,
        })
        print(
            f"[payout_email_poller] {request_id} RETURNED by {actor_email} via email"
        )


# ---------------------------------------------------------------------------
# PayoutEmailPoller class
# ---------------------------------------------------------------------------

class PayoutEmailPoller:
    """
    Approval email poller — Microsoft Graph primary, IMAP fallback.

    Usage
    -----
    poller = PayoutEmailPoller()
    poller.start()   # spawns a background daemon thread
    """

    def __init__(
        self,
        imap_host: str | None = None,
        imap_port: int | None = None,
        email_user: str | None = None,
        email_pass: str | None = None,
        poll_interval: int | None = None,
    ):
        self.imap_host     = imap_host    or IMAP_HOST
        self.imap_port     = imap_port    or IMAP_PORT
        self.email_user    = email_user   or EMAIL_USER
        self.email_pass    = email_pass   or EMAIL_PASS
        self.poll_interval = poll_interval or POLL_INTERVAL_SECONDS

        # Graph client — preferred transport
        from app.graphmail import GraphMailClient
        self._graph = GraphMailClient.from_env()

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ── Transport selection ───────────────────────────────────────────────────

    def _use_graph(self) -> bool:
        return self._graph.configured

    def _use_imap(self) -> bool:
        return bool(self.imap_host and self.email_user and self.email_pass)

    def _configured(self) -> bool:
        return self._use_graph() or self._use_imap()

    # ── Single poll cycle ────────────────────────────────────────────────────

    def poll(self) -> None:
        """
        Fetch UNSEEN/unread messages, process each, mark as read.
        Uses Microsoft Graph when credentials are present; falls back to IMAP.
        """
        if self._use_graph():
            self._poll_via_graph()
        elif self._use_imap():
            self._poll_via_imap()
        else:
            print(
                "[payout_email_poller] No mail transport configured — "
                "set PAGEOS_MSGRAPH_CLIENT_ID/TENANT_ID/CLIENT_SECRET (preferred) "
                "or PAGEOS_APPROVALS_IMAP_HOST (fallback)"
            )

    # ── Graph path ────────────────────────────────────────────────────────────

    def _poll_via_graph(self) -> None:
        mailbox = self.email_user or "approvals@pageaml.com"
        try:
            messages = self._graph.list_unread(mailbox)
        except Exception as exc:
            print(f"[payout_email_poller] Graph list_unread error: {exc}")
            return

        if not messages:
            return

        print(f"[payout_email_poller] Graph: {len(messages)} unread message(s)")

        for msg in messages:
            try:
                self._process_graph_message(msg)
            except Exception as exc:
                print(f"[payout_email_poller] Graph process error msg {msg['id']}: {exc}")
                traceback.print_exc()
            finally:
                try:
                    self._graph.mark_read(mailbox, msg["id"])
                except Exception:
                    pass

    def _process_graph_message(self, msg: dict) -> None:
        from_addr  = msg["from_address"]
        subject    = msg["subject"]
        body       = msg["body_text"]

        id_match = INSTRUCTION_ID_RE.search(subject) or INSTRUCTION_ID_RE.search(body)
        if not id_match:
            return

        instruction_id = id_match.group(1)
        action_line    = _first_action_line(body)
        action         = _classify_action(action_line)

        if action is None:
            return

        print(f"[payout_email_poller] Graph: {from_addr} → {instruction_id}: {action}")
        self._apply_by_instruction_id(from_addr, instruction_id, action)

    # ── IMAP fallback path ────────────────────────────────────────────────────

    def _poll_via_imap(self) -> None:
        try:
            ctx = ssl.create_default_context()
            with imaplib.IMAP4_SSL(self.imap_host, self.imap_port, ssl_context=ctx) as imap:
                imap.login(self.email_user, self.email_pass)
                self._process_inbox(imap)
        except imaplib.IMAP4.error as exc:
            print(f"[payout_email_poller] IMAP error: {exc}")
        except OSError as exc:
            print(f"[payout_email_poller] Network error: {exc}")
        except Exception as exc:
            print(f"[payout_email_poller] Unexpected IMAP error: {exc}")
            traceback.print_exc()

    def _apply_by_instruction_id(
        self, from_addr: str, instruction_id: str, action: str
    ) -> None:
        """Shared action-dispatch used by both Graph and IMAP paths."""
        from app import db
        with db.get_db() as con:
            row = con.execute(
                "SELECT * FROM payment_requests WHERE instruction_id=?",
                (instruction_id,),
            ).fetchone()

        if not row:
            print(f"[payout_email_poller] {instruction_id} not found")
            return

        request    = dict(row)
        request_id = request["id"]
        step       = db.payout_get_active_step(request_id)

        if not step:
            print(f"[payout_email_poller] No pending step for {instruction_id}")
            return

        if step["assigned_to"].lower() != from_addr.lower():
            print(
                f"[payout_email_poller] {from_addr} not assigned to "
                f"{step['step_type']} of {instruction_id}"
            )
            return

        _apply_action(request_id, step, from_addr, action)

    def _process_inbox(self, imap: imaplib.IMAP4_SSL) -> None:
        imap.select("INBOX")
        _, data = imap.search(None, "UNSEEN")
        msg_nums = data[0].split() if data[0] else []

        if not msg_nums:
            return  # nothing to do

        print(f"[payout_email_poller] {len(msg_nums)} unseen message(s) to process")

        for num in msg_nums:
            try:
                self._process_one(imap, num)
            except Exception as exc:
                print(f"[payout_email_poller] Error processing msg {num}: {exc}")
                traceback.print_exc()
            finally:
                # Always mark as SEEN regardless of outcome
                try:
                    imap.store(num, "+FLAGS", "\\Seen")
                except Exception:
                    pass

    def _process_one(self, imap: imaplib.IMAP4_SSL, num: bytes) -> None:
        _, raw = imap.fetch(num, "(RFC822)")
        if not raw or not raw[0]:
            return

        raw_bytes = raw[0][1] if isinstance(raw[0], tuple) else raw[0]
        if not isinstance(raw_bytes, bytes):
            return

        msg = _email_mod.message_from_bytes(raw_bytes)

        # Extract From address
        from_raw = msg.get("From", "")
        from_match = re.search(r"[\w.+\-]+@[\w.\-]+", from_raw)
        if not from_match:
            print(f"[payout_email_poller] Could not parse From address: {from_raw!r} — skipping")
            return
        from_addr = from_match.group(0).lower()

        # Extract Subject
        subject = _decode_mime_header(msg.get("Subject", ""))

        # Find instruction ID in subject
        id_match = INSTRUCTION_ID_RE.search(subject)
        if not id_match:
            # Try the message body as a fallback
            body_for_id = _extract_body_text(msg)
            id_match = INSTRUCTION_ID_RE.search(body_for_id)

        if not id_match:
            print(f"[payout_email_poller] No instruction ID in msg from {from_addr} — skipping")
            return

        instruction_id = id_match.group(1)

        # Extract action from body
        body = _extract_body_text(msg)
        action_line = _first_action_line(body)
        action = _classify_action(action_line)

        if action is None:
            print(
                f"[payout_email_poller] Could not classify action "
                f"(first line: {action_line!r}) in msg from {from_addr} re {instruction_id} — skipping"
            )
            return

        print(
            f"[payout_email_poller] {from_addr} → {instruction_id}: action={action}"
        )

        print(f"[payout_email_poller] IMAP: {from_addr} → {instruction_id}: {action}")
        self._apply_by_instruction_id(from_addr, instruction_id, action)

    # ── Background thread ────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Start the poller in a background daemon thread.
        Polls every self.poll_interval seconds until stop() is called.

        If credentials are not configured, logs a warning and returns immediately
        without spawning a thread.
        """
        if not self._configured():
            print(
                "[payout_email_poller] Skipping start — "
                "PAGEOS_APPROVALS_IMAP_HOST / EMAIL_USER / EMAIL_PASS not set"
            )
            return

        if self._thread and self._thread.is_alive():
            print("[payout_email_poller] Already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="payout-email-poller",
            daemon=True,
        )
        self._thread.start()
        print(
            f"[payout_email_poller] Started — polling {self.email_user} "
            f"every {self.poll_interval}s"
        )

    def stop(self) -> None:
        """Signal the background thread to stop after the current poll completes."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=30)
        print("[payout_email_poller] Stopped")

    def _run_loop(self) -> None:
        """Internal: poll on a fixed interval until stop_event is set."""
        while not self._stop_event.is_set():
            try:
                self.poll()
            except Exception as exc:
                print(f"[payout_email_poller] Unhandled error in run loop: {exc}")
                traceback.print_exc()
            # Wait for interval or until stopped
            self._stop_event.wait(timeout=self.poll_interval)


# ---------------------------------------------------------------------------
# Module-level singleton — used by main.py lifespan
# ---------------------------------------------------------------------------

_poller: PayoutEmailPoller | None = None


def get_poller() -> PayoutEmailPoller:
    global _poller
    if _poller is None:
        _poller = PayoutEmailPoller()
    return _poller


def start_poller() -> None:
    """Start the module-level singleton poller. Call from lifespan startup."""
    get_poller().start()


def stop_poller() -> None:
    """Stop the module-level singleton poller. Call from lifespan shutdown."""
    if _poller:
        _poller.stop()
