"""
Symplus (Neulogic) — GL export connector.

Two modes depending on what Neulogic provides after M02 is resolved:

  Mode A — REST API  (preferred)
    POST /api/auth/login  → session token
    GET  /api/gl/export?account=...&from=...&to=...  → JSON payload

  Mode B — File import  (interim, while waiting for API access)
    Symplus admin exports a CSV/XLSX from the Symplus UI and places it in
    a watched directory (SFTP or shared folder).

Required env / config (Mode A):
  SYMPLUS_BASE_URL     e.g. https://symplus.neulogic.com.ng
  SYMPLUS_USERNAME
  SYMPLUS_PASSWORD
  SYMPLUS_COMPANY_CODE (the company code in Symplus)

Required config (Mode B):
  SYMPLUS_WATCH_DIR   path the Symplus admin drops exports into

The connector returns a path to a local file in the symplus_ledger profile
format (the engine already knows how to read it from the M09 run).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import httpx

from app.connectors.base import DateRange, FetchResult, LedgerProvider


class SymplusAPIProvider(LedgerProvider):
    """Calls the Symplus REST API (Mode A)."""

    name = "symplus_api"

    def __init__(self, base_url: str | None = None, username: str | None = None,
                 password: str | None = None, company_code: str | None = None):
        self.base_url     = (base_url     or os.getenv("SYMPLUS_BASE_URL", "")).rstrip("/")
        self.username     = username      or os.getenv("SYMPLUS_USERNAME", "")
        self.password     = password      or os.getenv("SYMPLUS_PASSWORD", "")
        self.company_code = company_code  or os.getenv("SYMPLUS_COMPANY_CODE", "")
        self._token: str | None = None

    def _login(self) -> str:
        resp = httpx.post(
            f"{self.base_url}/api/auth/login",
            json={"username": self.username, "password": self.password,
                  "company": self.company_code},
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["token"]
        return self._token

    def _headers(self) -> dict:
        if not self._token:
            self._login()
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    def can_auto_fetch(self) -> bool:
        return bool(self.base_url and self.username and self.password)

    def test_connection(self) -> bool:
        try:
            self._login()
            return True
        except Exception:
            return False

    def fetch(self, account_id: str, gl_account: str,
              period: DateRange, dest_dir: Path) -> FetchResult:
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            resp = httpx.get(
                f"{self.base_url}/api/gl/export",
                params={"account": gl_account, "company": self.company_code,
                        "from": period.start.isoformat(), "to": period.end.isoformat(),
                        "format": "json"},
                headers=self._headers(),
                timeout=120,
            )
            resp.raise_for_status()
            payload = resp.json()

            filename = f"symplus_gl_{gl_account}_{period.start}_{period.end}.json"
            dest = dest_dir / filename
            dest.write_text(json.dumps(payload, indent=2))

            return FetchResult(
                ok=True, path=dest, account_id=account_id,
                provider=self.name,
                message=f"{len(payload.get('entries', []))} GL entries fetched",
                raw_response=payload,
            )
        except httpx.HTTPStatusError as e:
            return FetchResult(ok=False, path=None, account_id=account_id,
                               provider=self.name, message=str(e))
        except Exception as e:
            return FetchResult(ok=False, path=None, account_id=account_id,
                               provider=self.name, message=str(e))


class SymplusWatchDirProvider(LedgerProvider):
    """
    Mode B — watches a directory for Symplus export files.
    The Symplus admin exports and drops the file here.
    This is the interim mode while the API is being provisioned.
    """

    name = "symplus_watch"

    def __init__(self, watch_dir: str | None = None):
        self.watch_dir = Path(watch_dir or os.getenv("SYMPLUS_WATCH_DIR", "./symplus_exports"))

    def can_auto_fetch(self) -> bool:
        return False   # requires a human to drop the file

    def test_connection(self) -> bool:
        return self.watch_dir.exists()

    def fetch(self, account_id: str, gl_account: str,
              period: DateRange, dest_dir: Path) -> FetchResult:
        # Look for the most recently modified file in the watch directory
        candidates = sorted(
            self.watch_dir.glob("*.xlsx") ,
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ) + sorted(
            self.watch_dir.glob("*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return FetchResult(ok=False, path=None, account_id=account_id,
                               provider=self.name,
                               message=f"No export files found in {self.watch_dir}. "
                                       "Ask the Symplus admin to export and drop the file here.")
        latest = candidates[0]
        return FetchResult(ok=True, path=latest, account_id=account_id,
                           provider=self.name,
                           message=f"Using {latest.name} from watch directory")
