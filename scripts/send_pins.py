#!/usr/bin/env python3
"""
send_pins.py — Generate and distribute PINs to all PageRails payout users.

For each user this script:
  1. Generates a random 6-digit PIN.
  2. Hashes it with bcrypt (identical to password hashing).
  3. Writes the hash to the DB via pin_set() — also resets pin_attempts=0
     and clears pin_locked_until.
  4. Sends the user an email via Microsoft Graph with their PIN and setup
     instructions.

Usage:
  python3 scripts/send_pins.py              # generate, set in DB, send all
  python3 scripts/send_pins.py --dry-run    # print only, no DB or email changes
  python3 scripts/send_pins.py --email toyin.akinde@pageaml.com  # one user only

Required environment variables:
  PAGEOS_MSGRAPH_CLIENT_ID
  PAGEOS_MSGRAPH_TENANT_ID
  PAGEOS_MSGRAPH_CLIENT_SECRET
  PAGEOS_APPROVALS_EMAIL_USER   — the From mailbox, e.g. approvals@pageaml.com
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

# ── Make the backend package importable ──────────────────────────────────────
_root = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_root))

import bcrypt
from app import db
from app.graphmail import GraphMailClient

# ── User list ─────────────────────────────────────────────────────────────────
# (name, email)  — mirrors PAYOUT_USERS in add_payout_users.py
PAYOUT_USERS: list[tuple[str, str]] = [
    ("Toyin Akinde",        "toyin.akinde@pageaml.com"),
    ("Adenike Odesanya",    "adenike.odesanya@pageaml.com"),
    ("Deremi Ogunsipe",     "rogunsipe@pagefinancials.com"),
    ("Amos Olanrewaju",     "amos.olanrewaju@pageaml.com"),
    ("Damilola Osifala",    "damilola.osifala@pageaml.com"),
    ("Adewale Bamiro",      "Adewale.Bamiro@pagecapitalng.com"),
    ("Udochukwu Okigbo",    "udochukwu.okigbo@pageaml.com"),
    ("Olawunmi Oladigbo",   "olawunmi.oladigbo@pageaml.com"),
    ("Gabriel Adepoju",     "gabriel.adepoju@pageaml.com"),
    ("Samuel Fabunmi",      "Samuel.Fabunmi@pageaml.com"),
    ("Segun Akintemi",      "segun.akintemi@pageaml.com"),
]

# ── Email content ─────────────────────────────────────────────────────────────

EMAIL_SUBJECT = "Your PageRails PIN – action required before the dry run"

EMAIL_BODY_TEMPLATE = """\
Dear {name},

Your PIN for PageRails is: {pin}

Use this PIN — not your password — when approving payment requests
from your phone. Keep it private: every action is recorded in your
name with the time and cannot be changed afterwards.

To set up your PIN:
1. Open http://192.168.0.171:3000
2. Log in with your email and temporary password: PageOS2026!
3. Click your name in the top-right corner → "Set PIN"
4. Enter this PIN: {pin}
5. Confirm it and save.

Five wrong attempts locks you out for 15 minutes.

If you have any problems, contact Nonso immediately.

PageRails — Page Capital Group\
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_pin() -> str:
    """Return a zero-padded random 6-digit PIN string."""
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def _hash_pin(pin: str) -> str:
    """Bcrypt-hash a PIN the same way passwords are hashed."""
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def _print_table(rows: list[tuple[str, str, str]]) -> None:
    """Print a fixed-width table of (name, email, pin)."""
    col_name  = max(len(r[0]) for r in rows)
    col_email = max(len(r[1]) for r in rows)
    col_pin   = 6

    header = (
        f"{'Name':<{col_name}}  {'Email':<{col_email}}  {'PIN':<{col_pin}}"
    )
    divider = "-" * len(header)
    print()
    print(divider)
    print(header)
    print(divider)
    for name, email, pin in rows:
        print(f"{name:<{col_name}}  {email:<{col_email}}  {pin:<{col_pin}}")
    print(divider)
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and distribute PageRails PINs."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen — do not write to DB or send emails.",
    )
    parser.add_argument(
        "--email",
        metavar="ADDRESS",
        help="Process a single user by email address (for testing).",
    )
    args = parser.parse_args()

    # ── Select target users ───────────────────────────────────────────────────
    users = PAYOUT_USERS
    if args.email:
        users = [
            (name, email)
            for name, email in PAYOUT_USERS
            if email.lower() == args.email.lower()
        ]
        if not users:
            print(f"ERROR: '{args.email}' is not in PAYOUT_USERS.", file=sys.stderr)
            sys.exit(1)

    # ── Graph client (validate credentials early unless dry-run) ──────────────
    sender = os.getenv("PAGEOS_APPROVALS_EMAIL_USER", "").strip()
    graph: GraphMailClient | None = None

    if not args.dry_run:
        graph = GraphMailClient.from_env()
        if not graph.configured:
            print(
                "ERROR: Missing one or more Graph env vars:\n"
                "  PAGEOS_MSGRAPH_CLIENT_ID\n"
                "  PAGEOS_MSGRAPH_TENANT_ID\n"
                "  PAGEOS_MSGRAPH_CLIENT_SECRET",
                file=sys.stderr,
            )
            sys.exit(1)
        if not sender:
            print(
                "ERROR: PAGEOS_APPROVALS_EMAIL_USER is not set.",
                file=sys.stderr,
            )
            sys.exit(1)

    # ── Generate PINs ─────────────────────────────────────────────────────────
    table_rows: list[tuple[str, str, str]] = []
    for name, email in users:
        table_rows.append((name, email, _generate_pin()))

    # ── Print the admin record table ──────────────────────────────────────────
    mode_label = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{mode_label}PIN distribution — Page Capital Group")
    _print_table(table_rows)

    if args.dry_run:
        print("Dry run complete. No DB changes or emails sent.")
        return

    # ── Apply to DB and send emails ───────────────────────────────────────────
    errors: list[str] = []

    for name, email, pin in table_rows:
        # 1. Look up user id
        row = db.pin_get(email)
        if row is None:
            msg = f"SKIP   {email} — user not found in DB (run add_payout_users.py first)"
            print(msg)
            errors.append(msg)
            continue

        user_id: int = row["id"]

        # 2. Hash and store the PIN
        try:
            pin_hash = _hash_pin(pin)
            db.pin_set(user_id, pin_hash)
            print(f"  DB OK  {email}")
        except Exception as exc:
            msg = f"  DB ERR {email}: {exc}"
            print(msg, file=sys.stderr)
            errors.append(msg)
            continue

        # 3. Send the email
        body = EMAIL_BODY_TEMPLATE.format(name=name, pin=pin)
        try:
            assert graph is not None  # guaranteed above
            graph.send_mail(
                from_mailbox=sender,
                to_address=email,
                subject=EMAIL_SUBJECT,
                body_text=body,
            )
            print(f"  SENT   {email}")
        except Exception as exc:
            msg = f"  MAIL ERR {email}: {exc}"
            print(msg, file=sys.stderr)
            errors.append(msg)

    # ── Summary ───────────────────────────────────────────────────────────────
    total   = len(table_rows)
    n_err   = len(errors)
    n_ok    = total - n_err
    print(f"\nDone. {n_ok}/{total} users processed successfully.")
    if errors:
        print(f"\n{n_err} error(s):")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
