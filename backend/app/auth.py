"""JWT auth — DB-backed users with granular permissions."""
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings
from app import db as _db

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

ALL_PERMISSIONS = _db.ALL_PERMISSIONS


class TokenData(BaseModel):
    user_id: int
    email: str
    name: str
    is_admin: bool
    permissions: list[str]


def create_token(user: dict) -> str:
    payload = {
        "sub":         str(user["id"]),
        "email":       user["email"],
        "name":        user["name"],
        "is_admin":    bool(user["is_admin"]),
        "permissions": user.get("permissions", []),
        "exp":         datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> TokenData:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenData(
            user_id=int(data["sub"]),
            email=data["email"],
            name=data["name"],
            is_admin=data.get("is_admin", False),
            permissions=data.get("permissions", []),
        )
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


async def current_user(token: Annotated[str, Depends(oauth2)]) -> TokenData:
    return decode_token(token)


def require_permission(permission: str):
    """Dependency that requires a specific permission (or admin)."""
    async def _guard(user: Annotated[TokenData, Depends(current_user)]) -> TokenData:
        if user.is_admin:
            return user
        if permission not in user.permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Permission '{permission}' required",
            )
        return user
    return _guard


def require_admin():
    async def _guard(user: Annotated[TokenData, Depends(current_user)]) -> TokenData:
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        return user
    return _guard


# Shorthand deps
AnyUser      = Annotated[TokenData, Depends(current_user)]
AdminUser    = Annotated[TokenData, Depends(require_admin())]

# Permission-scoped deps
CanTriggerRun    = Annotated[TokenData, Depends(require_permission("trigger_run"))]
CanUploadFiles   = Annotated[TokenData, Depends(require_permission("upload_files"))]
CanApproveMatch  = Annotated[TokenData, Depends(require_permission("approve_match"))]
CanSignoffRun    = Annotated[TokenData, Depends(require_permission("signoff_run"))]
CanApprovePost   = Annotated[TokenData, Depends(require_permission("approve_posting"))]
CanPostToLedger  = Annotated[TokenData, Depends(require_permission("post_to_ledger"))]
CanFetchStatement = Annotated[TokenData, Depends(require_permission("fetch_statement"))]
CanFetchLedger   = Annotated[TokenData, Depends(require_permission("fetch_ledger"))]
CanManageUsers   = Annotated[TokenData, Depends(require_permission("manage_users"))]


# ── PIN auth ───────────────────────────────────────────────────────────────────

PIN_MAX_ATTEMPTS = 5
PIN_LOCK_MINUTES = 15

_PIN_RE = re.compile(r"^\d{4,6}$")


def set_pin(user_id: int, pin: str) -> None:
    """Validate, hash, and store a PIN for the given user."""
    if not _PIN_RE.match(pin):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PIN must be 4–6 digits",
        )
    import bcrypt
    pin_hash = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()
    _db.pin_set(user_id, pin_hash)


def authenticate_pin(email: str, pin: str) -> dict:
    """
    Verify a PIN for the given email.

    Returns the user dict on success.
    Raises 401 on any failure (no user enumeration).
    """
    import bcrypt
    from math import ceil

    row = _db.pin_get(email)

    # Unknown email or PIN not set — same opaque 401 to avoid enumeration
    if not row or not row.get("pin_hash"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="PIN not set",
        )

    # Check lockout
    locked_until_str = row.get("pin_locked_until")
    if locked_until_str:
        locked_until = datetime.fromisoformat(locked_until_str)
        now = datetime.now(timezone.utc)
        # Make locked_until timezone-aware if it isn't
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if now < locked_until:
            remaining = ceil((locked_until - now).total_seconds() / 60)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"PIN locked, try in {remaining} minute{'s' if remaining != 1 else ''}",
            )

    # Verify PIN
    if bcrypt.checkpw(pin.encode(), row["pin_hash"].encode()):
        _db.pin_reset_attempts(row["id"])
        user = _db.user_get_by_email(email)
        return user

    # Mismatch — increment attempts and maybe lock
    new_attempts = (row.get("pin_attempts") or 0) + 1
    lock_until: str | None = None
    if new_attempts >= PIN_MAX_ATTEMPTS:
        lock_until = (
            datetime.now(timezone.utc) + timedelta(minutes=PIN_LOCK_MINUTES)
        ).isoformat(timespec="seconds")
    _db.pin_increment_attempts(row["id"], lock_until)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid PIN",
    )
