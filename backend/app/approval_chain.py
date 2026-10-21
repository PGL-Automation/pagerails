"""
approval_chain.py — PageRails payout approval chain engine.

Responsibilities
----------------
1. Load approval_roles.yaml (config-based, not org-chart-based).
2. build_steps(request, now) → ordered list of step dicts ready for
   payout_create_step().
3. generate_instruction_id(entity, year, sequence) → "PAM-APR-2026-000001"
4. get_entity_code(entity) → "PAM" | "PCL"

Routing rules (all timeouts in minutes unless noted)
-----------------------------------------------------
  client_payout | liquidation | transfer:
      head_concur(20) → internal_control(20)
      → compliance(20) [only when beneficiary NOT registered]
      → finance(20) → signatory_1(20) → signatory_2(20)

  expense ≤ 1_000_000 NGN (stored as kobo: ≤ 100_000_000):
      head_concur(4h) → internal_control(4h) → finance(8h) → md(8h)

  expense > 1_000_000 NGN:
      head_concur(4h) → internal_control(4h) → finance(8h) → md(8h) → ceo(8h)

  placement:
      head_concur(20) → internal_control(20) → finance(20) → md(20)

Guards (enforced at action time, not here):
  - raised_by != actor
  - no double-acting on same request
  - actor must be assigned to current step

Stand-ins:  at 2× step timeout → reassign to stand_in, notify both
Reminders:  at 1× step timeout → send email reminder
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml


def end_of_business_day(now: datetime) -> datetime:
    """
    Return today's 17:00 WAT (UTC+1) as a UTC datetime.
    If `now` is already at or past 17:00 WAT, return next business day 17:00 WAT.
    Skips Saturday (5) and Sunday (6).
    """
    WAT = timezone(timedelta(hours=1))
    now_wat = now.astimezone(WAT)
    eob = now_wat.replace(hour=17, minute=0, second=0, microsecond=0)
    if now_wat >= eob:
        # After COB — deadline is next business day 17:00
        days_ahead = 1
        next_day = now_wat + timedelta(days=days_ahead)
        while next_day.weekday() in (5, 6):
            days_ahead += 1
            next_day = now_wat + timedelta(days=days_ahead)
        eob = next_day.replace(hour=17, minute=0, second=0, microsecond=0)
    return eob.astimezone(timezone.utc)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "pcg_recon" / "config" / "approval_roles.yaml"

_config: dict | None = None


def _load_config() -> dict:
    global _config
    if _config is None:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            _config = yaml.safe_load(fh)
    return _config


def _role_email(entity: str, role: str) -> str | None:
    """Return the email for a given entity + role, or None if not configured."""
    cfg = _load_config()
    return cfg.get("entities", {}).get(entity, {}).get(role) or None


def get_stand_in(email: str) -> str | None:
    """Return the stand-in email for a given person, or None."""
    cfg = _load_config()
    return cfg.get("stand_ins", {}).get(email)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_entity_code(entity: str) -> str:
    """
    Normalise an entity name or code to 'PAM' or 'PCL'.

    Accepts:
        'PAM', 'PAML', 'Page Asset Management Limited',
        'PCL', 'Page Capital Limited', etc.
    """
    upper = entity.strip().upper()
    if upper in ("PAM", "PAML", "PAGE ASSET MANAGEMENT LIMITED", "PAGE ASSET MANAGEMENT"):
        return "PAM"
    if upper in ("PCL", "PAGE CAPITAL LIMITED", "PAGE CAPITAL"):
        return "PCL"
    # Fallback: assume it's already the code
    return upper


def generate_instruction_id(entity: str, year: int, sequence: int) -> str:
    """
    Build a human-readable instruction reference.

    Examples
    --------
    >>> generate_instruction_id("PAM", 2026, 1)
    'PAM-APR-2026-000001'
    >>> generate_instruction_id("PCL", 2026, 999)
    'PCL-APR-2026-000999'
    """
    code = get_entity_code(entity)
    return f"{code}-APR-{year}-{sequence:06d}"


# ---------------------------------------------------------------------------
# Step builder
# ---------------------------------------------------------------------------

def _minutes(m: int) -> timedelta:
    return timedelta(minutes=m)


def _hours(h: int) -> timedelta:
    return timedelta(hours=h)


def _make_step(
    *,
    request_id: str,
    step_order: int,
    step_type: str,
    assigned_to: str | None,
    due_by: datetime,
    now: datetime,
    status: str = "pending",
) -> dict[str, Any]:
    """Build a single step dict."""
    if not assigned_to:
        # Role not configured — skip automatically
        status = "skipped"
        due_by = now

    return {
        "id":          str(uuid.uuid4()),
        "request_id":  request_id,
        "step_order":  step_order,
        "step_type":   step_type,
        "assigned_to": assigned_to or "",
        "status":      status,
        "due_by":      due_by.isoformat(timespec="seconds"),
        "created_at":  now.isoformat(timespec="seconds"),
    }


def build_steps(request: dict, now: datetime | None = None) -> list[dict[str, Any]]:
    """
    Build the ordered approval chain for a payout request.

    Parameters
    ----------
    request : dict
        Must contain:
            request_id        : str   — unique ID of the payout request
            request_type      : str   — client_payout | liquidation | transfer | expense | placement
            entity            : str   — PAM | PCL (or long form)
            amount_kobo       : int   — amount in kobo (100 kobo = 1 NGN)
        Optional:
            beneficiary_registered : bool  — defaults to True
                If False, a compliance step is inserted for payment-type requests.

    now : datetime
        Reference time.  Defaults to UTC now.

    Returns
    -------
    list[dict]  ordered step dicts (step_order is 1-based).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    request_id   = request["request_id"]
    req_type     = request["request_type"].strip().lower()
    entity       = get_entity_code(request.get("entity", "PAM"))
    amount_kobo  = int(request.get("amount_kobo", 0))
    ben_reg      = bool(request.get("beneficiary_registered", True))

    def email(role: str) -> str | None:
        return _role_email(entity, role)

    steps: list[dict] = []
    order = 1

    # -----------------------------------------------------------------------
    # Route: client_payout | liquidation | transfer
    # -----------------------------------------------------------------------
    if req_type in ("client_payout", "liquidation", "transfer"):
        _SL = _minutes(20)  # step limit

        chain: list[tuple[str, timedelta]] = [
            ("head_concur",      _SL),
            ("internal_control", _SL),
        ]
        if not ben_reg:
            chain.append(("compliance", _SL))
        chain += [
            ("finance",     _SL),
            ("signatory_1", _SL),
            ("signatory_2", _SL),
        ]

        t = now
        for role, limit in chain:
            t = t + limit
            steps.append(_make_step(
                request_id=request_id,
                step_order=order,
                step_type=role,
                assigned_to=email(role),
                due_by=t,
                now=now,
            ))
            order += 1

    # -----------------------------------------------------------------------
    # Route: expense
    # -----------------------------------------------------------------------
    elif req_type == "expense":
        # ≤ 1,000,000 NGN = ≤ 100,000,000 kobo
        _4H = _hours(4)
        _8H = _hours(8)

        # head_concur and internal_control are checks — fixed 4h window.
        # finance, md, ceo are approval steps — end-of-business-day deadline.
        _EOB_ROLES = {"finance", "md", "ceo"}

        chain: list[tuple[str, timedelta]] = [
            ("head_concur",      _4H),
            ("internal_control", _4H),
            ("finance",          _8H),
            ("md",               _8H),
        ]
        if amount_kobo > 100_000_000:
            chain.append(("ceo", _8H))

        t = now
        for role, limit in chain:
            t = t + limit
            if role in _EOB_ROLES:
                due_by = end_of_business_day(now)
            else:
                due_by = t
            steps.append(_make_step(
                request_id=request_id,
                step_order=order,
                step_type=role,
                assigned_to=email(role),
                due_by=due_by,
                now=now,
            ))
            order += 1

    # -----------------------------------------------------------------------
    # Route: placement
    # -----------------------------------------------------------------------
    elif req_type == "placement":
        _SL = _minutes(20)

        chain: list[tuple[str, timedelta]] = [
            ("head_concur",      _SL),
            ("internal_control", _SL),
            ("finance",          _SL),
            ("md",               _SL),
        ]

        t = now
        for role, limit in chain:
            t = t + limit
            steps.append(_make_step(
                request_id=request_id,
                step_order=order,
                step_type=role,
                assigned_to=email(role),
                due_by=t,
                now=now,
            ))
            order += 1

    else:
        raise ValueError(
            f"Unknown request_type '{req_type}'. "
            "Expected: client_payout | liquidation | transfer | expense | placement"
        )

    return steps


# ---------------------------------------------------------------------------
# Stand-in resolution helper (for scheduler / escalation tasks)
# ---------------------------------------------------------------------------

def resolve_stand_in(email: str) -> str | None:
    """
    Return the configured stand-in for *email*, or None if none is defined.

    At 2× the step time-limit, the caller should:
        1. Reassign the step to the returned email.
        2. Notify both the original assignee and the stand-in.
    """
    return get_stand_in(email)
