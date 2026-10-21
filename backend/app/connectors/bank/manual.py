"""Manual upload provider — passes through a file already in the inputs directory."""
from pathlib import Path
from app.connectors.base import DateRange, FetchResult, StatementProvider


class ManualUploadProvider(StatementProvider):
    name = "manual"

    def __init__(self, file_path: Path | None = None):
        self._file_path = file_path

    def can_auto_fetch(self) -> bool:
        return False

    def test_connection(self) -> bool:
        return True

    def fetch(self, account_id: str, period: DateRange, dest_dir: Path) -> FetchResult:
        if self._file_path and self._file_path.exists():
            return FetchResult(ok=True, path=self._file_path, account_id=account_id,
                               provider=self.name, message="Using manually uploaded file")
        return FetchResult(ok=False, path=None, account_id=account_id,
                           provider=self.name,
                           message="No file provided — upload via the Files page")
