"""
graphmail.py — Microsoft Graph API mail client (Python).

App-only authentication via client credentials flow — no user sign-in required.
The Azure AD application must have Mail.Read application permission, scoped to
the target mailboxes via an Exchange ApplicationAccessPolicy (already configured
by the IT team with Client ID 7f0c1881-c644-45eb-906c-438e96c8d6dc).

Required environment variables:
    PAGEOS_MSGRAPH_CLIENT_ID      = 7f0c1881-c644-45eb-906c-438e96c8d6dc
    PAGEOS_MSGRAPH_TENANT_ID      = c5367046-962e-4f7c-bea6-24fa415cd319
    PAGEOS_MSGRAPH_CLIENT_SECRET  = <secret>

Usage:
    client = GraphMailClient.from_env()
    if not client.configured:
        ...  # credentials absent — fall back to IMAP or skip
    messages = client.list_unread("approvals@pageaml.com")
    for msg in messages:
        process(msg)
        client.mark_read("approvals@pageaml.com", msg["id"])
"""
from __future__ import annotations

import base64
import logging
import os
import re
import threading
import time
from typing import Any

import httpx as requests  # httpx is already a project dependency

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL  = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


class GraphMailClient:
    """Minimal Microsoft Graph mail client using app-only authentication."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self.tenant_id     = tenant_id
        self.client_id     = client_id
        self.client_secret = client_secret
        self._token: str | None     = None
        self._token_expiry: float   = 0.0
        self._lock = threading.Lock()

    # ── Construction ──────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "GraphMailClient":
        return cls(
            tenant_id     = os.getenv("PAGEOS_MSGRAPH_TENANT_ID",     ""),
            client_id     = os.getenv("PAGEOS_MSGRAPH_CLIENT_ID",     ""),
            client_secret = os.getenv("PAGEOS_MSGRAPH_CLIENT_SECRET", ""),
        )

    @property
    def configured(self) -> bool:
        return bool(self.tenant_id and self.client_id and self.client_secret)

    # ── Token management ──────────────────────────────────────────────────────

    def _get_token(self) -> str:
        with self._lock:
            # Refresh 2 minutes before expiry.
            if self._token and time.time() < self._token_expiry - 120:
                return self._token

            url  = TOKEN_URL.format(tenant=self.tenant_id)
            data = {
                "grant_type":    "client_credentials",
                "client_id":     self.client_id,
                "client_secret": self.client_secret,
                "scope":         "https://graph.microsoft.com/.default",
            }
            resp = requests.post(url, data=data, timeout=15)
            resp.raise_for_status()
            body = resp.json()
            self._token        = body["access_token"]
            self._token_expiry = time.time() + int(body.get("expires_in", 3600))
            return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept":        "application/json",
        }

    # ── Mail operations ───────────────────────────────────────────────────────

    def list_unread(self, mailbox: str, top: int = 50) -> list[dict[str, Any]]:
        """
        Return up to `top` unread messages from the mailbox.

        Each item has:
            id           str   — Graph message ID (opaque, use for mark_read / get_attachments)
            subject      str
            from_address str   — lower-cased sender email
            body_text    str   — plain text (HTML stripped)
            has_attachments bool
        """
        url = (
            f"{GRAPH_BASE}/users/{mailbox}/messages"
            f"?$filter=isRead%20eq%20false"
            f"&$select=id,subject,from,body,hasAttachments"
            f"&$top={top}"
        )
        resp = requests.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()

        results = []
        for item in resp.json().get("value", []):
            body = item.get("body", {})
            content = body.get("content", "")
            if body.get("contentType", "").lower() == "html":
                content = _strip_html(content)
            results.append({
                "id":              item["id"],
                "subject":         item.get("subject", ""),
                "from_address":    item.get("from", {})
                                       .get("emailAddress", {})
                                       .get("address", "").lower().strip(),
                "body_text":       content,
                "has_attachments": item.get("hasAttachments", False),
            })
        return results

    def get_attachments(self, mailbox: str, message_id: str) -> list[dict[str, Any]]:
        """
        Return file attachments for a message.

        Each item has:
            id           str
            name         str   — filename
            content_type str
            data         bytes — decoded content
        """
        url = (
            f"{GRAPH_BASE}/users/{mailbox}/messages/{message_id}/attachments"
            f"?$select=id,name,contentType,contentBytes"
        )
        resp = requests.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()

        results = []
        for item in resp.json().get("value", []):
            if item.get("@odata.type") == "#microsoft.graph.referenceAttachment":
                continue
            raw = item.get("contentBytes", "")
            try:
                data = base64.b64decode(raw)
            except Exception:
                continue
            results.append({
                "id":           item["id"],
                "name":         item.get("name", ""),
                "content_type": item.get("contentType", ""),
                "data":         data,
            })
        return results

    def mark_read(self, mailbox: str, message_id: str) -> None:
        """Mark a message as read so it is not processed again."""
        url  = f"{GRAPH_BASE}/users/{mailbox}/messages/{message_id}"
        resp = requests.patch(
            url,
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"isRead": True},
            timeout=15,
        )
        resp.raise_for_status()

    def send_mail(
        self,
        from_mailbox: str,
        to_address: str,
        subject: str,
        body_text: str,
        save_to_sent: bool = True,
    ) -> None:
        """
        Send an email FROM a shared mailbox using Microsoft Graph.

        The Azure AD app must have Mail.Send application permission, scoped
        to from_mailbox via ApplicationAccessPolicy (already configured).

        body_text is sent as plain text; Graph wraps it in a minimal HTML
        shell so Outlook renders it correctly.
        """
        url  = f"{GRAPH_BASE}/users/{from_mailbox}/sendMail"
        # Escape HTML entities for the HTML wrapper
        escaped = (
            body_text.replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;")
                     .replace("\n", "<br>")
        )
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": (
                        "<html><body style='font-family:Arial,sans-serif;font-size:14px'>"
                        f"{escaped}"
                        "</body></html>"
                    ),
                },
                "toRecipients": [
                    {"emailAddress": {"address": to_address}}
                ],
            },
            "saveToSentItems": save_to_sent,
        }
        resp = requests.post(
            url,
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()


# ── Internal helpers ──────────────────────────────────────────────────────────

_HTML_TAG    = re.compile(r"<[^>]+>")
_HTML_ENTITY = {
    "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
    "&#39;": "'",
}


def _strip_html(html: str) -> str:
    text = _HTML_TAG.sub(" ", html)
    for entity, char in _HTML_ENTITY.items():
        text = text.replace(entity, char)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)
