from fastapi import APIRouter, HTTPException

from app import db
from app.auth import CanApproveMatch
from app.schemas import DecisionsRequest

router = APIRouter()

VALID_ACTIONS = {"APPROVE", "REJECT", "MANUAL"}


@router.post("/")
def submit_decisions(body: DecisionsRequest, user: CanApproveMatch):
    """
    Submit batch approve/reject decisions from the Review Queue.
    Re-run the account after submitting to apply decisions.
    """
    if not body.decisions:
        raise HTTPException(400, "decisions list is empty")

    saved = 0
    for d in body.decisions:
        if d.action.upper() not in VALID_ACTIONS:
            raise HTTPException(400, f"Invalid action: {d.action}")
        db.save_decision(
            account_id=d.account_id,
            action=d.action.upper(),
            bank_uids=d.bank_uids,
            book_uids=d.book_uids,
            reviewer=body.reviewer or user.name,
            note=d.note,
        )
        saved += 1

    return {
        "saved": saved,
        "message": f"Recorded {saved} decision(s) by {body.reviewer or user.name}. "
                   "Re-run the period to apply them.",
    }
