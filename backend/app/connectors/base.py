"""
Abstract base classes for all external system connectors.

Design principle: every connector is swappable — the engine and the API layer
never depend on a specific implementation. Switch providers by changing config,
not code.

  StatementProvider  — pulls bank statements (Providus API, email, manual)
  LedgerProvider     — pulls GL exports from the accounting system (Symplus API, manual)
  LedgerPoster       — posts approved journals back to the accounting system
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class DateRange:
    start: date
    end:   date


@dataclass
class FetchResult:
    ok:          bool
    path:        Path | None        # local path to the downloaded file
    account_id:  str
    provider:    str
    message:     str = ""
    raw_response: dict = field(default_factory=dict)


@dataclass
class PostResult:
    ok:        bool
    provider:  str
    post_ref:  str = ""            # reference ID from the accounting system
    message:   str = ""
    items_posted: int = 0
    raw_response: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    valid:    bool
    errors:   list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DraftJournal:
    """
    A single double-entry journal ready to post to any accounting system.

    When posted to Symplus the engine generates TWO rows per entry:
      Row 1 — DR leg:  Account=dr_gl,  Dr/Cr="D"
      Row 2 — CR leg:  Account=cr_gl,  Dr/Cr="C"

    Symplus-specific fields (book_of_account, trans_code, etc.) are populated
    from the account config in accounts.yaml.
    """
    run_id:          str
    account_id:      str
    category:        str
    date:            str          # ISO date (YYYY-MM-DD)
    dr_gl:           str          # debit GL account code
    cr_gl:           str          # credit GL account code
    amount:          float        # in major units (NGN)
    narration:       str
    reference:       str = ""
    # Symplus-specific (populated from account config)
    book_of_account: str = "GL08"     # Symplus Book of Account code
    trans_code:      str = "000"      # Symplus transaction code
    currency:        str = "NGN"
    exch_rate:       float = 1.0
    cost_center:     str = ""
    metadata:        dict = field(default_factory=dict)


# ── Abstract bases ─────────────────────────────────────────────────────────────

class StatementProvider(abc.ABC):
    """Fetches a bank statement for a given account and period."""

    name: str = "base"

    @abc.abstractmethod
    def fetch(self, account_id: str, period: DateRange, dest_dir: Path) -> FetchResult:
        """Download / locate the statement file and return the path."""

    @abc.abstractmethod
    def can_auto_fetch(self) -> bool:
        """True if this provider supports unattended scheduled fetching."""

    @abc.abstractmethod
    def test_connection(self) -> bool:
        """Verify credentials / connectivity without fetching data."""


class LedgerProvider(abc.ABC):
    """Fetches a GL / ledger export from the accounting system."""

    name: str = "base"

    @abc.abstractmethod
    def fetch(self, account_id: str, gl_account: str,
              period: DateRange, dest_dir: Path) -> FetchResult:
        """Download GL postings and return the path to the exported file."""

    @abc.abstractmethod
    def can_auto_fetch(self) -> bool:
        """True if this provider supports unattended scheduled fetching."""

    @abc.abstractmethod
    def test_connection(self) -> bool:
        """Verify credentials / connectivity."""


class LedgerPoster(abc.ABC):
    """Posts approved journal entries into the accounting system."""

    name: str = "base"

    @abc.abstractmethod
    def validate(self, journals: list[DraftJournal]) -> ValidationResult:
        """Pre-flight check before committing anything."""

    @abc.abstractmethod
    def post(self, journals: list[DraftJournal], posted_by: str) -> PostResult:
        """Submit journals. Should be idempotent (use reference field)."""

    @abc.abstractmethod
    def test_connection(self) -> bool:
        """Verify credentials / connectivity."""
