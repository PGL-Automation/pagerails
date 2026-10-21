"""
Connector registry — maps account config to the right provider instance.

To swap a provider: change the connector_type in accounts.yaml.
No code change required.

accounts.yaml snippet:
  - id: PAM-PRV-CLIENTS
    bank_feed:
      connector: providus_api          # or: email_imap | manual
      account_number: "5401732286"
    ledger_feed:
      connector: symplus_watch         # or: symplus_api | manual
    posting:
      connector: symplus_csv           # or: symplus_api | dry_run
"""
from __future__ import annotations

import os
from pathlib import Path

from app.connectors.base import StatementProvider, LedgerProvider, LedgerPoster
from app.connectors.bank.manual     import ManualUploadProvider
from app.connectors.bank.providus   import ProvidusAPIProvider
from app.connectors.bank.email_fetch import EmailStatementProvider
from app.connectors.ledger.symplus  import SymplusAPIProvider, SymplusWatchDirProvider
from app.connectors.posting.symplus import SymplusAPIPoster, SymplusCSVPoster, DryRunPoster


def get_statement_provider(account: dict) -> StatementProvider:
    """Return the configured StatementProvider for an account."""
    feed = account.get("bank_feed", {})
    connector = feed.get("connector", "manual")

    if connector == "providus_api":
        return ProvidusAPIProvider(
            account_number=feed.get("account_number", account.get("account_number", "")),
        )
    if connector == "email_imap":
        return EmailStatementProvider(
            sender_filter=feed.get("sender_filter", ""),
        )
    # Default: manual
    return ManualUploadProvider()


def get_ledger_provider(account: dict) -> LedgerProvider:
    """Return the configured LedgerProvider for an account."""
    feed = account.get("ledger_feed", {})
    connector = feed.get("connector", "symplus_watch")

    if connector == "symplus_api":
        return SymplusAPIProvider()
    if connector == "symplus_watch":
        watch_dir = feed.get("watch_dir") or os.getenv("SYMPLUS_WATCH_DIR")
        return SymplusWatchDirProvider(watch_dir)
    # Default: treat any existing file as manual
    return SymplusWatchDirProvider()


def get_ledger_poster(account: dict) -> LedgerPoster:
    """Return the configured LedgerPoster for an account."""
    posting = account.get("posting", {})
    connector = posting.get("connector", "dry_run")

    if connector == "symplus_api":
        return SymplusAPIPoster()
    if connector == "symplus_csv":
        output_dir = posting.get("output_dir") or os.getenv("SYMPLUS_CSV_EXPORT_DIR")
        return SymplusCSVPoster(output_dir)
    if connector == "dry_run":
        return DryRunPoster()
    return DryRunPoster()
