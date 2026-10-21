#!/usr/bin/env python3
"""
add_payout_users.py — Add all payout approval system users to PageRails.

Run on the PageRails server (or locally with the correct RECON_DB_PATH set):
    python3 scripts/add_payout_users.py

The script is idempotent — already-existing users are skipped (matched by email).
Permissions are granted / updated on every run so they're always in sync.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Make backend importable ───────────────────────────────────────────────────
_root = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_root))

import bcrypt
from app import db

# ── Users to add ──────────────────────────────────────────────────────────────
# Format: (name, email, password, is_admin, permissions)
INITIAL_PASSWORD = "PageOS2026!"

PAYOUT_USERS = [
    # Approval chain — signatories / MD
    (
        "Toyin Akinde",
        "toyin.akinde@pageaml.com",
        INITIAL_PASSWORD,
        False,
        [
            "approve_payout",   # approves steps assigned to her
            "view_audit",
            "view_reports",
            "signoff_run",
        ],
    ),
    (
        "Adenike Odesanya",
        "adenike.odesanya@pageaml.com",
        INITIAL_PASSWORD,
        False,
        [
            "approve_payout",
            "view_audit",
            "view_reports",
        ],
    ),
    (
        "Deremi Ogunsipe",
        "rogunsipe@pagefinancials.com",
        INITIAL_PASSWORD,
        False,
        [
            "approve_payout",
            "view_audit",
            "view_reports",
            "signoff_run",
        ],
    ),
    # Operations — raises and pays client payouts
    (
        "Amos Olanrewaju",
        "amos.olanrewaju@pageaml.com",
        INITIAL_PASSWORD,
        False,
        [
            "raise_payout",
            "pay_payout",
            "approve_payout",   # checker 1 for customer payouts
            "upload_files",
            "trigger_run",
            "view_reports",
        ],
    ),
    # Finance — FinOps checker (already exists, but ensure payout permissions added)
    (
        "Damilola Osifala",
        "damilola.osifala@pageaml.com",
        INITIAL_PASSWORD,
        False,
        [
            "approve_payout",
            "raise_payout",
            "pay_payout",
            "signoff_run",
            "upload_files",
            "view_reports",
            "view_audit",
            "approve_posting",
        ],
    ),
    # Page Capital operations
    (
        "Adewale Bamiro",
        "Adewale.Bamiro@pagecapitalng.com",
        INITIAL_PASSWORD,
        False,
        [
            "raise_payout",
            "approve_payout",
            "view_reports",
        ],
    ),
    # Internal Control
    (
        "Udochukwu Okigbo",
        "udochukwu.okigbo@pageaml.com",
        INITIAL_PASSWORD,
        False,
        [
            "approve_payout",
            "view_audit",
            "view_reports",
        ],
    ),
    # Internal Control officer (Wunmi)
    (
        "Olawunmi Oladigbo",
        "olawunmi.oladigbo@pageaml.com",
        INITIAL_PASSWORD,
        False,
        [
            "approve_payout",
            "view_audit",
            "view_reports",
        ],
    ),
    # Operations — raises client payouts
    (
        "Gabriel Adepoju",
        "gabriel.adepoju@pageaml.com",
        INITIAL_PASSWORD,
        False,
        [
            "raise_payout",
            "upload_files",
            "view_reports",
        ],
    ),
    # Confirms payments after bank processes them
    (
        "Samuel Fabunmi",
        "Samuel.Fabunmi@pageaml.com",
        INITIAL_PASSWORD,
        False,
        [
            "confirm_payout",
            "view_reports",
            "view_audit",
        ],
    ),
    # PCL bank signatory_2 — signs bank mandate sheets for Page Capital
    (
        "Segun Akintemi",
        "segun.akintemi@pageaml.com",
        "PageOS2026!",
        False,
        ["approve_payout", "view_reports"],
    ),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    db.migrate()  # ensure all tables (including payout tables) exist

    with db.get_db() as con:
        for name, email, password, is_admin, permissions in PAYOUT_USERS:
            # Check if user already exists
            existing = con.execute(
                "SELECT id FROM users WHERE lower(email) = lower(?)", (email,)
            ).fetchone()

            if existing:
                user_id = existing["id"]
                print(f"  EXISTING  {email} (id={user_id}) — updating permissions")
            else:
                pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                now = _now()
                cur = con.execute(
                    "INSERT INTO users (name, email, password_hash, is_admin, is_active, "
                    "created_at, updated_at) VALUES (?,?,?,?,1,?,?)",
                    (name, email, pw_hash, int(is_admin), now, now),
                )
                user_id = cur.lastrowid
                print(f"  CREATED   {email} (id={user_id})")

            # Grant / ensure permissions (idempotent)
            for perm in permissions:
                con.execute(
                    "INSERT OR IGNORE INTO permissions (user_id, permission) VALUES (?,?)",
                    (user_id, perm),
                )

    print(f"\n✅ Done. {len(PAYOUT_USERS)} users processed.")
    print(f"   Initial password: {INITIAL_PASSWORD}")
    print("   Each user should log in and set their PIN via /pin-setup")


if __name__ == "__main__":
    main()
