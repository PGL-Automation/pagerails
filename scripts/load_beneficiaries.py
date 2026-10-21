#!/usr/bin/env python3
"""
load_beneficiaries.py — Load client beneficiary register into PageRails SQLite.

Reads the same Excel file used for PageOS:
    /Users/nonsookoroafor/Downloads/Client Account Register-PAML & PCL.xlsx

Run from the autopilot root:
    python3 scripts/load_beneficiaries.py
"""
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

_root = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_root))

try:
    import openpyxl
except ImportError:
    print("openpyxl not installed. Run: pip install openpyxl")
    sys.exit(1)

from app import db

EXCEL_PATH = Path("/Users/nonsookoroafor/Downloads/Client Account Register-PAML & PCL.xlsx")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def clean_acct(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\.0$", "", str(v).strip())

def main() -> None:
    if not EXCEL_PATH.exists():
        print(f"File not found: {EXCEL_PATH}")
        sys.exit(1)

    db.migrate()

    wb = openpyxl.load_workbook(str(EXCEL_PATH))
    ws = wb.active

    seen:  set[tuple[str, str]] = set()
    rows_to_insert = []

    for row in ws.iter_rows(values_only=True):
        client_id, client_name, bank, acct_no, company = (
            row[1], row[2], row[3], row[4], row[5]
        )
        if not client_name or str(client_name) == "CLIENT NAME":
            continue
        company_str = str(company).strip().upper() if company else ""
        if company_str not in ("PAML", "PCL"):
            continue

        entity = "PAM" if company_str == "PAML" else "PCL"
        acct_str = clean_acct(acct_no)
        if not acct_str or acct_str == "0":
            continue

        key = (entity, acct_str)
        if key in seen:
            continue
        seen.add(key)

        id_str   = re.sub(r"\.0$", "", str(client_id)).strip() if client_id else ""
        bank_str = str(bank).strip() if bank else ""
        name_str = str(client_name).strip()

        rows_to_insert.append((entity, name_str, id_str, bank_str, acct_str, _now()))

    print(f"Inserting {len(rows_to_insert)} unique client beneficiaries…")

    with db.get_db() as con:
        con.executemany(
            """
            INSERT OR IGNORE INTO client_beneficiaries
                (entity, client_name, client_id, bank_name, account_number, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )

    with db.get_db() as con:
        count = con.execute("SELECT COUNT(*) FROM client_beneficiaries").fetchone()[0]

    print(f"✅ client_beneficiaries table now has {count} rows.")


if __name__ == "__main__":
    main()
