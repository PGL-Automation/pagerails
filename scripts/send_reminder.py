#!/usr/bin/env python3
"""
send_reminder.py — Send Monday go-live reminder to all PageRails approvers.

Usage:
  python3 scripts/send_reminder.py            # send to all 11 approvers
  python3 scripts/send_reminder.py --dry-run  # print only, no emails sent
  python3 scripts/send_reminder.py --email toyin.akinde@pageaml.com  # one user

Required environment variables (inherited from backend/.env):
  PAGEOS_MSGRAPH_CLIENT_ID
  PAGEOS_MSGRAPH_TENANT_ID
  PAGEOS_MSGRAPH_CLIENT_SECRET
  PAGEOS_APPROVALS_EMAIL_USER
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_root))

from app.graphmail import GraphMailClient

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

EMAIL_SUBJECT = "PageRails goes live Monday 26 October — action required"

EMAIL_BODY_TEMPLATE = """\
Dear {name},

PageRails goes live on Monday 26 October 2026 at 08:00.

Before Monday, please complete ONE action:

  1. Open PageRails in your browser (from any computer in the office):
     http://192.168.0.171:3000

  2. Log in with:
     Email:    {email}
     Password: PageOS2026!

  3. You will be prompted to set your PIN. Choose a 6-digit PIN you can
     remember. You will enter this PIN every time you approve a payment.
     Keep it private — every approval is recorded in your name.

If you have already set your PIN, no further action is needed.

From Monday, payout approvals will come to your email. Click the link
in the email, log in, enter your PIN, and approve or reject. The whole
process takes under two minutes.

If you have any problems before Monday, contact Nonso immediately.

PageRails — Page Capital Group\
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Send PageRails go-live reminder emails.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be sent — no emails.")
    parser.add_argument("--email", metavar="ADDRESS",
                        help="Send to one user only.")
    args = parser.parse_args()

    users = PAYOUT_USERS
    if args.email:
        users = [(n, e) for n, e in PAYOUT_USERS if e.lower() == args.email.lower()]
        if not users:
            print(f"ERROR: '{args.email}' not in PAYOUT_USERS.", file=sys.stderr)
            sys.exit(1)

    sender = os.getenv("PAGEOS_APPROVALS_EMAIL_USER", "").strip()
    graph: GraphMailClient | None = None

    if not args.dry_run:
        graph = GraphMailClient.from_env()
        if not graph.configured:
            print(
                "ERROR: Missing Graph env vars:\n"
                "  PAGEOS_MSGRAPH_CLIENT_ID\n"
                "  PAGEOS_MSGRAPH_TENANT_ID\n"
                "  PAGEOS_MSGRAPH_CLIENT_SECRET",
                file=sys.stderr,
            )
            sys.exit(1)
        if not sender:
            print("ERROR: PAGEOS_APPROVALS_EMAIL_USER is not set.", file=sys.stderr)
            sys.exit(1)

    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{mode}Go-live reminder — {len(users)} recipient(s)\n")

    errors: list[str] = []
    for name, email in users:
        body = EMAIL_BODY_TEMPLATE.format(name=name, email=email)
        if args.dry_run:
            print(f"  WOULD SEND → {name} <{email}>")
            continue
        try:
            assert graph is not None
            graph.send_mail(
                from_mailbox=sender,
                to_address=email,
                subject=EMAIL_SUBJECT,
                body_text=body,
            )
            print(f"  SENT   {email}")
        except Exception as exc:
            msg = f"  ERR    {email}: {exc}"
            print(msg, file=sys.stderr)
            errors.append(msg)

    if args.dry_run:
        print("\nDry run complete. No emails sent.")
        return

    n_ok = len(users) - len(errors)
    print(f"\nDone. {n_ok}/{len(users)} sent successfully.")
    if errors:
        for e in errors:
            print(f"  {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
