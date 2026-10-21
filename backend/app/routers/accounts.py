import yaml
from fastapi import APIRouter

from app.auth import AnyUser
from app.config import settings

router = APIRouter()


@router.get("/")
def list_accounts(_: AnyUser):
    """Return the account registry from accounts.yaml (read-only)."""
    cfg = settings.config_dir()
    data = yaml.safe_load((cfg / "accounts.yaml").read_text())
    accounts = [
        a for a in data.get("accounts", [])
        if a.get("enabled", True)
    ]
    entities = data.get("entities", {})
    return {"accounts": accounts, "entities": entities}
