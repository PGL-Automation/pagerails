"""
Providus Bank — Account Statement API connector.

API base: https://developer.providusbank.com
Auth: client_id + client_secret → Bearer token (OAuth2 client_credentials)

Required env / config keys (set in backend/.env):
  PROVIDUS_CLIENT_ID
  PROVIDUS_CLIENT_SECRET
  PROVIDUS_API_BASE       (default: https://api.providusbank.com/v1)

The API returns transactions in JSON.  This connector:
  1. Obtains / refreshes a Bearer token
  2. Calls GET /accounts/{account_number}/statements?from=...&to=...
  3. Writes the response to a local .json file (the engine's tabular ingest
     converts it on the next run)

Swap implementation: subclass StatementProvider with a different provider
and register it in connectors/registry.py.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import httpx

from app.connectors.base import DateRange, FetchResult, StatementProvider


class ProvidusAPIProvider(StatementProvider):
    name = "providus_api"

    def __init__(self, account_number: str, client_id: str | None = None,
                 client_secret: str | None = None, api_base: str | None = None):
        self.account_number = account_number
        self.client_id      = client_id     or os.getenv("PROVIDUS_CLIENT_ID", "")
        self.client_secret  = client_secret or os.getenv("PROVIDUS_CLIENT_SECRET", "")
        self.api_base       = (api_base or os.getenv("PROVIDUS_API_BASE",
                                "https://api.providusbank.com/v1")).rstrip("/")
        self._token: str | None = None

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        resp = httpx.post(
            f"{self.api_base}/oauth/token",
            data={"grant_type": "client_credentials",
                  "client_id": self.client_id,
                  "client_secret": self.client_secret},
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _headers(self) -> dict:
        if not self._token:
            self._get_token()
        return {"Authorization": f"Bearer {self._token}",
                "Accept": "application/json"}

    # ── StatementProvider interface ────────────────────────────────────────────

    def can_auto_fetch(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def test_connection(self) -> bool:
        try:
            self._get_token()
            return True
        except Exception:
            return False

    def fetch(self, account_id: str, period: DateRange, dest_dir: Path) -> FetchResult:
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            resp = httpx.get(
                f"{self.api_base}/accounts/{self.account_number}/statements",
                params={"from": period.start.isoformat(), "to": period.end.isoformat()},
                headers=self._headers(),
                timeout=60,
            )
            resp.raise_for_status()
            payload = resp.json()

            # Write raw JSON — the engine's tabular ingest will convert it
            filename = f"statement_{period.start}_{period.end}.json"
            dest = dest_dir / filename
            dest.write_text(json.dumps(payload, indent=2))

            return FetchResult(
                ok=True, path=dest, account_id=account_id,
                provider=self.name,
                message=f"{len(payload.get('transactions', []))} transactions fetched",
                raw_response=payload,
            )
        except httpx.HTTPStatusError as e:
            return FetchResult(ok=False, path=None, account_id=account_id,
                               provider=self.name, message=str(e))
        except Exception as e:
            return FetchResult(ok=False, path=None, account_id=account_id,
                               provider=self.name, message=str(e))
