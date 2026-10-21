"""
Email bank statement fetcher.

Supports two transports (tried in order):
  1. Microsoft Graph API (preferred) — set PAGEOS_MSGRAPH_CLIENT_ID,
     PAGEOS_MSGRAPH_TENANT_ID and PAGEOS_MSGRAPH_CLIENT_SECRET.
  2. Raw IMAP/TLS fallback — set STATEMENT_IMAP_HOST, STATEMENT_IMAP_USER,
     STATEMENT_IMAP_PASSWORD.

Legacy env vars still accepted for IMAP fallback:
  STATEMENT_IMAP_HOST     e.g. imap.gmail.com
  STATEMENT_IMAP_PORT     993
  STATEMENT_IMAP_USER     bankstatements@pageaml.com
  STATEMENT_IMAP_PASSWORD
  STATEMENT_IMAP_FOLDER   INBOX

The connector:
  1. Connects via IMAP SSL
  2. Searches for unseen emails from the bank's sender address within the period
  3. Downloads the first matching attachment (.xls/.xlsx/.csv/.pdf)
  4. Marks the email as read and returns the file path
"""
from __future__ import annotations

import email
import imaplib
import os
from datetime import date
from pathlib import Path

from app.connectors.base import DateRange, FetchResult, StatementProvider


class EmailStatementProvider(StatementProvider):
    name = "email_imap"

    def __init__(self, sender_filter: str, attachment_prefix: str = "",
                 host: str | None = None, port: int | None = None,
                 user: str | None = None, password: str | None = None,
                 folder: str = "INBOX"):
        self.sender_filter     = sender_filter
        self.attachment_prefix = attachment_prefix
        self.host     = host     or os.getenv("STATEMENT_IMAP_HOST", "")
        self.port     = port     or int(os.getenv("STATEMENT_IMAP_PORT", "993"))
        self.user     = user     or os.getenv("STATEMENT_IMAP_USER", "")
        self.password = password or os.getenv("STATEMENT_IMAP_PASSWORD", "")
        self.folder   = folder

        # Graph client (preferred transport)
        from app.graphmail import GraphMailClient
        self._graph = GraphMailClient.from_env()

    def _use_graph(self) -> bool:
        return self._graph.configured and bool(self.user)

    def can_auto_fetch(self) -> bool:
        return self._use_graph() or bool(self.host and self.user and self.password)

    def test_connection(self) -> bool:
        if self._use_graph():
            try:
                self._graph.list_unread(self.user, top=1)
                return True
            except Exception:
                return False
        try:
            with imaplib.IMAP4_SSL(self.host, self.port) as m:
                m.login(self.user, self.password)
            return True
        except Exception:
            return False

    def fetch(self, account_id: str, period: DateRange, dest_dir: Path) -> FetchResult:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if self._use_graph():
            return self._fetch_via_graph(account_id, dest_dir)
        return self._fetch_via_imap(account_id, period, dest_dir)

    def _fetch_via_graph(self, account_id: str, dest_dir: Path) -> FetchResult:
        """Download the most recent unread bank statement via Microsoft Graph.

        Deduplication: before saving, the file's SHA-256 hash is checked against
        the uploaded_files table.  If an identical file was already imported for
        this account we mark the email as read and skip silently — Providus
        sometimes re-sends the same statement in a follow-up alert email.
        """
        try:
            messages = self._graph.list_unread(self.user, top=20)
            for msg in messages:
                if self.sender_filter.lower() not in msg["from_address"]:
                    continue
                if not msg["has_attachments"]:
                    continue
                atts = self._graph.get_attachments(self.user, msg["id"])
                for att in atts:
                    ext = Path(att["name"]).suffix.lower()
                    if ext not in (".xls", ".xlsx", ".csv", ".pdf"):
                        continue

                    # ── Deduplication check ──────────────────────────────────
                    import hashlib
                    file_hash = hashlib.sha256(att["data"]).hexdigest()
                    if self._already_imported(account_id, file_hash):
                        self._graph.mark_read(self.user, msg["id"])
                        return FetchResult(
                            ok=False, path=None, account_id=account_id,
                            provider=self.name,
                            message=f"Skipped duplicate: {att['name']} (hash {file_hash[:12]}…) already imported for {account_id}",
                        )

                    dest = dest_dir / att["name"]
                    dest.write_bytes(att["data"])
                    self._graph.mark_read(self.user, msg["id"])
                    return FetchResult(
                        ok=True, path=dest, account_id=account_id,
                        provider=self.name,
                        message=f"Downloaded {att['name']} via Microsoft Graph",
                    )
            return FetchResult(
                ok=False, path=None, account_id=account_id,
                provider=self.name,
                message=f"No unread emails from {self.sender_filter} with supported attachments",
            )
        except Exception as exc:
            return FetchResult(ok=False, path=None, account_id=account_id,
                               provider=self.name, message=str(exc))

    @staticmethod
    def _already_imported(account_id: str, file_hash: str) -> bool:
        """Return True if a file with this SHA-256 hash was already imported for account_id."""
        try:
            from app import db
            with db.get_db() as con:
                row = con.execute(
                    "SELECT 1 FROM uploaded_files WHERE account_id=? AND file_hash=? LIMIT 1",
                    (account_id, file_hash),
                ).fetchone()
            return row is not None
        except Exception:
            return False  # if check fails, allow import rather than blocking

    def _fetch_via_imap(self, account_id: str, period: DateRange, dest_dir: Path) -> FetchResult:
        """IMAP fallback — original implementation."""
        try:
            with imaplib.IMAP4_SSL(self.host, self.port) as m:
                m.login(self.user, self.password)
                m.select(self.folder)

                since = period.start.strftime("%d-%b-%Y")
                before = period.end.strftime("%d-%b-%Y")
                _, msg_nums = m.search(
                    None,
                    f'(FROM "{self.sender_filter}" SINCE "{since}" BEFORE "{before}")'
                )

                if not msg_nums[0]:
                    return FetchResult(ok=False, path=None, account_id=account_id,
                                       provider=self.name,
                                       message=f"No emails from {self.sender_filter} in period")

                # Take the most recent matching email
                latest = msg_nums[0].split()[-1]
                _, data = m.fetch(latest, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])

                for part in msg.walk():
                    if part.get_content_maintype() == "multipart":
                        continue
                    if part.get("Content-Disposition") is None:
                        continue
                    filename = part.get_filename()
                    if not filename:
                        continue
                    ext = Path(filename).suffix.lower()
                    if ext not in (".xls", ".xlsx", ".csv", ".pdf"):
                        continue

                    dest = dest_dir / filename
                    dest.write_bytes(part.get_payload(decode=True))

                    # Mark read
                    m.store(latest, "+FLAGS", "\\Seen")

                    return FetchResult(ok=True, path=dest, account_id=account_id,
                                       provider=self.name,
                                       message=f"Downloaded {filename} from email")

                return FetchResult(ok=False, path=None, account_id=account_id,
                                   provider=self.name,
                                   message="Email found but no supported attachment")
        except Exception as e:
            return FetchResult(ok=False, path=None, account_id=account_id,
                               provider=self.name, message=str(e))
