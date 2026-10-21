import hashlib
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import db
from app.auth import CanUploadFiles, AnyUser
from app.config import settings
from app.schemas import UploadedFile

router = APIRouter()


@router.get("/pack", summary="Download a reconciliation Excel pack by path")
def download_pack(path: str, _: AnyUser):
    """Serves the reconciliation Excel pack produced by a run."""
    p = Path(path)
    if not p.exists() or p.suffix not in (".xlsx", ".xls"):
        raise HTTPException(404, "Pack file not found")
    return FileResponse(str(p), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        filename=p.name)

ALLOWED_EXTENSIONS = {".csv", ".xls", ".xlsx", ".pdf", ".sta", ".txt"}


def _file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


@router.post("/upload", response_model=list[UploadedFile])
async def upload_files(
    account_id: str = Form(...),
    period: str = Form(...),
    files: list[UploadFile] = File(...),
    user: CanUploadFiles = None,   # type: ignore[assignment]
):
    """
    Upload one or more input files for an account/period.
    Files are stored at uploads/{account_id}/ and symlinked into the engine's inputs directory.
    """
    if not account_id or not period:
        raise HTTPException(400, "account_id and period are required")

    results = []
    upload_root = settings.uploads_dir() / account_id
    upload_root.mkdir(parents=True, exist_ok=True)

    engine_inputs = settings.inputs_dir() / account_id
    engine_inputs.mkdir(parents=True, exist_ok=True)

    for f in files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"File type {ext} not allowed")

        data = await f.read()
        if len(data) > 100 * 1024 * 1024:  # 100MB guard
            raise HTTPException(400, f"{f.filename} exceeds 100MB")

        h = _file_hash(data)

        # Duplicate detection — skip if this exact file was already imported
        with db.get_db() as con:
            existing = con.execute(
                "SELECT filename, uploaded_at FROM uploaded_files "
                "WHERE account_id=? AND file_hash=? LIMIT 1",
                (account_id, h),
            ).fetchone()
        if existing:
            raise HTTPException(
                409,
                f"'{f.filename}' is identical to '{existing['filename']}' already uploaded "
                f"on {existing['uploaded_at'][:10]}. If this is a corrected file, "
                f"rename it before uploading (e.g. add '_v2' to the filename)."
            )

        dest = upload_root / f.filename
        dest.write_bytes(data)

        # Hard-link into engine inputs so the engine can read it directly
        engine_dest = engine_inputs / f.filename
        if engine_dest.exists():
            engine_dest.unlink()
        shutil.copy2(str(dest), str(engine_dest))

        row_id = db.save_uploaded_file(
            account_id=account_id, period=period, filename=f.filename,
            stored_path=str(dest), size=len(data), file_hash=h,
            uploaded_by=user.name,
        )
        results.append(UploadedFile(
            id=row_id, account_id=account_id, period=period,
            filename=f.filename, size=len(data), file_hash=h,
            uploaded_by=user.name, uploaded_at="",
        ))

    return results


@router.get("/", response_model=list[UploadedFile])
def list_files(account_id: str | None = None, _: AnyUser = None):   # type: ignore[assignment]
    rows = db.uploaded_files(account_id)
    return [
        UploadedFile(
            id=r["id"], account_id=r["account_id"], period=r["period"],
            filename=r["filename"], size=r["size"], file_hash=r["file_hash"],
            uploaded_by=r["uploaded_by"], uploaded_at=r["uploaded_at"],
        )
        for r in rows
    ]
