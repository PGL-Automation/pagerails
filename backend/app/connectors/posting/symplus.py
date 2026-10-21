"""
Symplus journal posting connector.

Posts approved draft journals back to Symplus via:
  Mode A — REST API   (when Neulogic provides the posting endpoint)
  Mode B — CSV import  (interim: generates a Symplus import file for manual upload)

Required env / config (Mode A — same credentials as the GL pull):
  SYMPLUS_BASE_URL, SYMPLUS_USERNAME, SYMPLUS_PASSWORD, SYMPLUS_COMPANY_CODE
  SYMPLUS_POSTING_GL    the posting GL code used as the default contra account
  SYMPLUS_BATCH_REF     prefix for batch references (e.g. "PAGERAILS")

Important: This is intentionally provider-agnostic.  When you switch from Symplus
to another accounting system, implement a new LedgerPoster subclass and update
the registry.  The posting_queue table and the approval workflow do not change.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.connectors.base import (
    DraftJournal, LedgerPoster, PostResult, ValidationResult,
)


class SymplusAPIPoster(LedgerPoster):
    """Posts journals via the Symplus REST API (Mode A)."""

    name = "symplus_api"

    def __init__(self, base_url: str | None = None, username: str | None = None,
                 password: str | None = None, company_code: str | None = None,
                 batch_ref_prefix: str = "PAGERAILS"):
        self.base_url         = (base_url     or os.getenv("SYMPLUS_BASE_URL", "")).rstrip("/")
        self.username         = username      or os.getenv("SYMPLUS_USERNAME", "")
        self.password         = password      or os.getenv("SYMPLUS_PASSWORD", "")
        self.company_code     = company_code  or os.getenv("SYMPLUS_COMPANY_CODE", "")
        self.batch_ref_prefix = batch_ref_prefix
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
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def test_connection(self) -> bool:
        try:
            self._login()
            return True
        except Exception:
            return False

    def validate(self, journals: list[DraftJournal]) -> ValidationResult:
        errors, warnings = [], []
        for j in journals:
            if not j.dr_gl:
                errors.append(f"{j.narration[:40]}: missing DR GL code")
            if not j.cr_gl:
                errors.append(f"{j.narration[:40]}: missing CR GL code")
            if j.amount <= 0:
                errors.append(f"{j.narration[:40]}: amount must be > 0")
            if j.dr_gl == j.cr_gl:
                warnings.append(f"{j.narration[:40]}: DR and CR GL are the same")
        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def post(self, journals: list[DraftJournal], posted_by: str) -> PostResult:
        validation = self.validate(journals)
        if not validation.valid:
            return PostResult(ok=False, provider=self.name,
                              message="Validation failed: " + "; ".join(validation.errors))

        batch_ref = f"{self.batch_ref_prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        # Symplus API receives journal legs (each journal = one DR entry + one CR entry)
        entries = []
        for j in journals:
            ref = j.reference or batch_ref
            eff_date = datetime.strptime(j.date, "%Y-%m-%d").strftime("%d-%b-%Y").upper()
            base = {
                "book_of_account": j.book_of_account or "GL08",
                "batch_id": batch_ref,
                "batch_desc": j.narration[:60],
                "currency": j.currency or "NGN",
                "trans_code": j.trans_code or "000",
                "trans_description": j.narration[:60],
                "exch_rate": j.exch_rate,
                "amount": round(j.amount, 2),
                "cost_center": j.cost_center or "",
                "reference": ref,
                "effective_date": eff_date,
                "posted_by": posted_by,
            }
            entries.append({**base, "account": j.dr_gl, "dr_cr": "D"})
            entries.append({**base, "account": j.cr_gl, "dr_cr": "C"})


        try:
            resp = httpx.post(
                f"{self.base_url}/api/journals/batch",
                json={"batch_ref": batch_ref, "company": self.company_code,
                      "entries": entries},
                headers=self._headers(),
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return PostResult(
                ok=True, provider=self.name, post_ref=batch_ref,
                items_posted=len(journals),
                message=f"Posted {len(journals)} entries as batch {batch_ref}",
                raw_response=data,
            )
        except httpx.HTTPStatusError as e:
            return PostResult(ok=False, provider=self.name, message=str(e))
        except Exception as e:
            return PostResult(ok=False, provider=self.name, message=str(e))


class SymplusCSVPoster(LedgerPoster):
    """
    Generates the Symplus "Loaded Data" batch import file.

    Column order confirmed from the Symplus UI (Oct 2026):
      Book of Account | Batch ID | Batch Desc. | Account | Currency |
      Trans.Code | Trans. Description | Dr/Cr | Exch.Rate | Amount |
      Cost Center | Reference | Effective Date

    Each DraftJournal produces TWO rows — the DR leg and the CR leg —
    because Symplus imports each side of a journal separately.
    Effective Date format: DD-MON-YYYY (e.g. 07-OCT-2026).

    Finance loads the CSV via Symplus → General Ledger → Loaded Data → Import.
    Once loaded it appears in the "Loaded Data" grid for review before posting.
    """

    name = "symplus_csv"

    # Exact column headers visible in the Symplus Loaded Data screen
    HEADERS = [
        "Book of Account", "Batch ID", "Batch Desc.",
        "Account", "Currency", "Trans.Code", "Trans. Description",
        "Dr/Cr", "Exch.Rate", "Amount", "Cost Center", "Reference", "Effective Date",
    ]

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir or os.getenv("SYMPLUS_CSV_EXPORT_DIR", "./symplus_imports"))

    def test_connection(self) -> bool:
        return True

    def validate(self, journals: list[DraftJournal]) -> ValidationResult:
        errors, warnings = [], []
        for j in journals:
            if not j.dr_gl:
                errors.append(f"{j.narration[:40]}: DR GL code missing")
            if not j.cr_gl:
                errors.append(f"{j.narration[:40]}: CR GL code missing")
            if j.dr_gl == j.cr_gl:
                warnings.append(f"{j.narration[:40]}: DR and CR GL are identical")
            if j.amount <= 0:
                errors.append(f"{j.narration[:40]}: amount must be > 0")
            if not j.book_of_account:
                errors.append(f"{j.narration[:40]}: book_of_account not set")
        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

    @staticmethod
    def _symplus_date(iso_date: str) -> str:
        """Convert YYYY-MM-DD to DD-MON-YYYY (e.g. '22-SEP-2026') for Symplus."""
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d-%b-%Y").upper()

    def _make_rows(self, j: DraftJournal, batch_id: str) -> list[list]:
        """Return [DR_row, CR_row] for a single DraftJournal."""
        eff_date = self._symplus_date(j.date)
        narration = j.narration[:60]
        ref = j.reference or batch_id
        common = [
            j.book_of_account or "GL08",
            batch_id,
            narration,
            None,                  # Account — filled per leg
            j.currency or "NGN",
            j.trans_code or "000",
            narration,
            None,                  # Dr/Cr — filled per leg
            j.exch_rate,
            round(j.amount, 2),
            j.cost_center or "",
            ref,
            eff_date,
        ]
        dr_row = common.copy(); dr_row[3] = j.dr_gl; dr_row[7] = "D"
        cr_row = common.copy(); cr_row[3] = j.cr_gl; cr_row[7] = "C"
        return [dr_row, cr_row]

    def post(self, journals: list[DraftJournal], posted_by: str) -> PostResult:
        validation = self.validate(journals)
        if not validation.valid:
            return PostResult(ok=False, provider=self.name,
                              message="Validation failed:\n" + "\n".join(validation.errors))

        self.output_dir.mkdir(parents=True, exist_ok=True)
        batch_id  = f"PAGERAILS-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        filename  = self.output_dir / f"{batch_id}.csv"

        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(self.HEADERS)
        for j in journals:
            for row in self._make_rows(j, batch_id):
                writer.writerow(row)

        filename.write_text(buf.getvalue(), encoding="utf-8")

        return PostResult(
            ok=True, provider=self.name, post_ref=batch_id,
            items_posted=len(journals),
            message=f"Symplus import file ready: {filename.name}\n"
                    f"Load via: General Ledger → Loaded Data → Import → select this file.\n"
                    f"({len(journals)} journals = {len(journals) * 2} rows including DR+CR legs)",
        )


class DryRunPoster(LedgerPoster):
    """Validates and logs, never actually posts anything. Use for testing."""

    name = "dry_run"

    def test_connection(self) -> bool:
        return True

    def validate(self, journals: list[DraftJournal]) -> ValidationResult:
        errors = [f"{j.narration[:40]}: missing GL" for j in journals
                  if not j.dr_gl or not j.cr_gl]
        return ValidationResult(valid=not errors, errors=errors)

    def post(self, journals: list[DraftJournal], posted_by: str) -> PostResult:
        print(f"[DryRunPoster] Would post {len(journals)} journals as {posted_by}")
        for j in journals:
            print(f"  DR {j.dr_gl} | CR {j.cr_gl} | {j.amount:.2f} | {j.narration[:50]}")
        return PostResult(ok=True, provider=self.name, post_ref="DRY-RUN",
                          items_posted=len(journals),
                          message="Dry run — nothing posted")
