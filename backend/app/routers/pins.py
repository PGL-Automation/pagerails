"""PIN authentication endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.auth import AnyUser, TokenData, authenticate_pin, create_token, set_pin
from app.schemas import TokenResponse

router = APIRouter()


class SetPinRequest(BaseModel):
    pin: str


class PinLoginRequest(BaseModel):
    email: str
    pin: str


@router.post("/set", summary="Set own PIN (authenticated)")
def set_my_pin(body: SetPinRequest, current_user: AnyUser) -> dict:
    """Set or replace the caller's PIN. Requires a valid JWT."""
    set_pin(current_user.user_id, body.pin)
    return {"ok": True}


@router.post("/login", response_model=TokenResponse, summary="PIN login (public)")
def pin_login(body: PinLoginRequest) -> TokenResponse:
    """Exchange email + PIN for a JWT token (no prior auth required)."""
    user = authenticate_pin(body.email, body.pin)
    return TokenResponse(
        access_token=create_token(user),
        name=user["name"],
        role="admin" if user["is_admin"] else "user",
        permissions=user.get("permissions", []),
    )
