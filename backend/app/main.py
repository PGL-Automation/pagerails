"""PageRails — FastAPI backend."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from pydantic import BaseModel

from app import db
from app.auth import create_token, authenticate_pin
from app.config import settings
from app.schemas import TokenResponse
from app.routers import runs, files, decisions, signoff, audit, accounts, users, connectors, pins, payouts
from app.scheduler import start_scheduler, stop_scheduler
from app.payout_email_poller import start_poller, stop_poller


class PinLoginRequest(BaseModel):
    email: str
    pin: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Run DB migrations and start the scheduler on startup."""
    try:
        db.migrate()
        print("[startup] DB migrations applied.")
    except FileNotFoundError as e:
        print(f"[startup] WARNING: {e}")
    try:
        start_scheduler()
    except Exception as e:
        print(f"[startup] Scheduler warning: {e}")
    try:
        start_poller()
    except Exception as e:
        print(f"[startup] Payout email poller warning: {e}")
    yield
    stop_scheduler()
    stop_poller()
    yield


app = FastAPI(
    title="PageRails API",
    description="PageRails — Financial Operations Platform by Page Capital Group",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth ──────────────────────────────────────────────────────────────────────
@app.post("/api/auth/token", response_model=TokenResponse, tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends()):
    from fastapi import HTTPException, status
    user = db.user_verify_password(form.username, form.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_token(user),
        name=user["name"],
        role="admin" if user["is_admin"] else "user",
        permissions=user.get("permissions", []),
    )


@app.post("/api/auth/pin-login", response_model=TokenResponse, tags=["auth"])
def pin_login_direct(body: PinLoginRequest):
    """PIN login — exchange email + PIN for a JWT token (no prior auth required)."""
    from fastapi import HTTPException, status
    try:
        user = authenticate_pin(body.email, body.pin)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return TokenResponse(
        access_token=create_token(user),
        name=user["name"],
        role="admin" if user["is_admin"] else "user",
        permissions=user.get("permissions", []),
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(runs.router,      prefix="/api/runs",      tags=["runs"])
app.include_router(files.router,     prefix="/api/files",     tags=["files"])
app.include_router(decisions.router, prefix="/api/decisions", tags=["decisions"])
app.include_router(signoff.router,   prefix="/api/runs",      tags=["signoff"])
app.include_router(audit.router,     prefix="/api/audit",     tags=["audit"])
app.include_router(accounts.router,  prefix="/api/accounts",  tags=["accounts"])
app.include_router(users.router,       prefix="/api/users",       tags=["users"])
app.include_router(connectors.router,  prefix="/api/connectors",  tags=["connectors"])
app.include_router(pins.router,        prefix="/api/auth/pin",    tags=["auth"])
app.include_router(payouts.router,     prefix="/api/payouts",     tags=["payouts"])


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "version": "0.1.0"}
