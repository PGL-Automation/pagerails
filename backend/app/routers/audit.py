import hashlib
import json

from fastapi import APIRouter

from app import db
from app.auth import AnyUser
from app.schemas import AuditEntry

router = APIRouter()


def _verify_chain(entries: list[dict]) -> tuple[bool, int]:
    """Re-derive hashes; return (ok, first_broken_seq)."""
    sorted_entries = sorted(entries, key=lambda e: e["seq"])
    prev = "GENESIS"
    for e in sorted_entries:
        payload_str = json.dumps(e.get("payload", {}), sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(f"{e['ts']}|{e['actor']}|{e['action']}|{payload_str}|{prev}".encode()).hexdigest()
        if e["hash"] != expected:
            return False, e["seq"]
        prev = e["hash"]
    return True, len(sorted_entries)


@router.get("/", response_model=list[AuditEntry])
def list_audit(_: AnyUser, limit: int = 200):
    entries = db.audit_list(limit)
    return [
        AuditEntry(
            seq=e["seq"], ts=e["ts"], actor=e["actor"], action=e["action"],
            payload=e.get("payload", {}),
            prev_hash=e.get("prev_hash", ""),
            hash=e.get("hash", ""),
        )
        for e in entries
    ]


@router.post("/verify")
def verify_chain(_: AnyUser):
    entries = db.audit_list(10_000)
    intact, n = _verify_chain(entries)
    return {
        "intact": intact,
        "entries_checked": n,
        "message": "Audit chain intact." if intact else f"Chain broken at seq {n}.",
    }
