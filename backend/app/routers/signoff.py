from fastapi import APIRouter, BackgroundTasks, HTTPException

from app import db
from app.auth import CanSignoffRun
from app.schemas import SignoffRequest

router = APIRouter()


@router.post("/{run_id}/signoff")
def sign_off(
    run_id: str,
    body: SignoffRequest,
    user: CanSignoffRun,
    background_tasks: BackgroundTasks,
):
    """
    Checker signs off a run.
    Enforces: checker ≠ maker, run must exist, not already signed.

    After sign-off, triggers the 3-way payout cross-check in the background:
    scans bank statement lines for payout instruction IDs and cross-checks
    them against the approval records for amount, beneficiary and status.
    """
    try:
        db.signoff_run(run_id, body.checker or user.name, body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))

    # ── 3-way payout cross-check (runs after the response is sent) ────────────
    # Imports inside function to avoid circular deps and allow the scheduler
    # module to not exist yet on first boot.
    def _cross_check():
        try:
            from app.payout_scheduler import check_recon_instruction_ids_for_run
            check_recon_instruction_ids_for_run(run_id)
        except ImportError:
            pass  # payout module not yet loaded (first-boot race)
        except Exception as exc:
            print(f"[signoff] payout cross-check error for run {run_id}: {exc}")

    background_tasks.add_task(_cross_check)

    return {
        "run_id": run_id,
        "signed_by": body.checker or user.name,
        "message": "Run signed off successfully.",
    }
