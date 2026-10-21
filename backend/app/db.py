"""
Thin SQLite wrapper — extends the engine's recon.db with the API layer tables.

Extra tables managed here:
  users                — user accounts with bcrypt-hashed passwords
  permissions          — per-user permission flags
  matches              — match results per run
  uploaded_files       — file upload log
  connector_logs       — automated fetch / post audit trail
  posting_queue        — journal entries approved for posting to the ledger
  payment_accounts     — disbursement bank accounts per entity
  client_beneficiaries — registered client beneficiaries per entity
  stand_ins            — escalation cover mappings
  payment_requests     — payout / liquidation / transfer / expense / placement requests
  approval_steps       — ordered approval workflow steps per request
  payout_action_log    — immutable audit trail for every payout action
"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings


def _connect() -> sqlite3.Connection:
    path = settings.db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"recon.db not found at {path}. "
            "Run the engine first: pagerails run --inputs ... --period ... --maker ..."
        )
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def get_db():
    con = _connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── Schema migrations (idempotent) ────────────────────────────────────────────

MIGRATIONS = [
    # Matches
    """CREATE TABLE IF NOT EXISTS matches (
        match_id   TEXT PRIMARY KEY,
        run_id     TEXT NOT NULL,
        rule       TEXT NOT NULL,
        confidence REAL NOT NULL,
        bank_uids  TEXT NOT NULL,
        book_uids  TEXT NOT NULL,
        status     TEXT NOT NULL,
        difference INTEGER NOT NULL DEFAULT 0,
        note       TEXT NOT NULL DEFAULT ''
    )""",

    # File upload log
    """CREATE TABLE IF NOT EXISTS uploaded_files (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   TEXT NOT NULL,
        period       TEXT NOT NULL,
        filename     TEXT NOT NULL,
        stored_path  TEXT NOT NULL,
        size         INTEGER NOT NULL,
        file_hash    TEXT NOT NULL,
        uploaded_by  TEXT NOT NULL,
        uploaded_at  TEXT NOT NULL
    )""",

    # Users
    """CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        email         TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        is_admin      INTEGER NOT NULL DEFAULT 0,
        is_active     INTEGER NOT NULL DEFAULT 1,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL
    )""",

    # Granular permissions  (one row per user per permission)
    """CREATE TABLE IF NOT EXISTS permissions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        permission TEXT NOT NULL,
        UNIQUE(user_id, permission)
    )""",

    # Connector fetch/post audit
    """CREATE TABLE IF NOT EXISTS connector_logs (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        connector    TEXT NOT NULL,
        account_id   TEXT NOT NULL,
        action       TEXT NOT NULL,
        status       TEXT NOT NULL,
        detail       TEXT,
        triggered_by TEXT,
        created_at   TEXT NOT NULL
    )""",

    # Posting queue — journals approved to send to the ledger
    """CREATE TABLE IF NOT EXISTS posting_queue (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id       TEXT NOT NULL,
        account_id   TEXT NOT NULL,
        category     TEXT NOT NULL,
        payload      TEXT NOT NULL,   -- JSON: the DraftJournal object
        status       TEXT NOT NULL DEFAULT 'PENDING',
        approved_by  TEXT,
        approved_at  TEXT,
        posted_by    TEXT,
        posted_at    TEXT,
        post_ref     TEXT,            -- reference from the ledger (e.g. Symplus journal ID)
        error        TEXT,
        created_at   TEXT NOT NULL
    )""",

    # Draft journals produced by each run (persisted so the UI and posting queue can use them)
    """CREATE TABLE IF NOT EXISTS run_journals (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id       TEXT NOT NULL,
        account_id   TEXT NOT NULL,
        date         TEXT NOT NULL,
        category     TEXT NOT NULL,
        dr_gl        TEXT NOT NULL,
        cr_gl        TEXT NOT NULL,
        amount       REAL NOT NULL,
        narration    TEXT NOT NULL,
        lines        INTEGER NOT NULL DEFAULT 1,
        uid          TEXT NOT NULL,
        status       TEXT NOT NULL DEFAULT 'DRAFT'
    )""",

    # Scheduler state — when each account's auto-fetch last ran
    """CREATE TABLE IF NOT EXISTS scheduler_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   TEXT NOT NULL,
        job_type     TEXT NOT NULL,   -- STATEMENT | LEDGER | RUN
        scheduled_at TEXT NOT NULL,
        ran_at       TEXT,
        status       TEXT NOT NULL DEFAULT 'PENDING',
        message      TEXT
    )""",

    # Indexes
    "CREATE INDEX IF NOT EXISTS idx_runs_period     ON runs(period_end)",
    "CREATE INDEX IF NOT EXISTS idx_matches_run     ON matches(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_open_items_run  ON open_items(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_perms_user      ON permissions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_pq_run          ON posting_queue(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_pq_status       ON posting_queue(status)",
    "CREATE INDEX IF NOT EXISTS idx_rj_run          ON run_journals(run_id)",

    # ── Payout system additions ───────────────────────────────────────────────

    # PIN columns on users
    "ALTER TABLE users ADD COLUMN pin_hash TEXT",
    "ALTER TABLE users ADD COLUMN pin_attempts INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN pin_locked_until TEXT",

    # Payment accounts — one row per entity × bank account
    """CREATE TABLE IF NOT EXISTS payment_accounts (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        entity         TEXT NOT NULL,
        bank_name      TEXT NOT NULL,
        account_name   TEXT NOT NULL,
        account_number TEXT NOT NULL,
        cut_off_time   TEXT NOT NULL DEFAULT '16:00',
        is_active      INTEGER NOT NULL DEFAULT 1,
        created_at     TEXT NOT NULL,
        UNIQUE(entity, account_number)
    )""",

    # Registered client beneficiaries
    """CREATE TABLE IF NOT EXISTS client_beneficiaries (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        entity         TEXT NOT NULL,
        client_name    TEXT NOT NULL,
        client_id      TEXT NOT NULL DEFAULT '',
        bank_name      TEXT NOT NULL,
        account_number TEXT NOT NULL,
        is_active      INTEGER NOT NULL DEFAULT 1,
        created_at     TEXT NOT NULL,
        UNIQUE(entity, account_number)
    )""",

    # Stand-in / escalation cover mappings
    """CREATE TABLE IF NOT EXISTS stand_ins (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email  TEXT NOT NULL UNIQUE,
        cover_email TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )""",

    # Payment requests — the master record for every payment instruction
    """CREATE TABLE IF NOT EXISTS payment_requests (
        id                   TEXT PRIMARY KEY,
        instruction_id       TEXT UNIQUE,
        entity               TEXT NOT NULL,
        request_type         TEXT NOT NULL,
        payment_account_id   INTEGER REFERENCES payment_accounts(id),
        amount_kobo          INTEGER NOT NULL,
        beneficiary_name     TEXT NOT NULL,
        beneficiary_bank     TEXT NOT NULL,
        beneficiary_account  TEXT NOT NULL,
        purpose              TEXT NOT NULL,
        supporting_doc_path  TEXT NOT NULL DEFAULT '',
        status               TEXT NOT NULL DEFAULT 'draft',
        compliance_flagged   INTEGER NOT NULL DEFAULT 0,
        raised_by            TEXT NOT NULL,
        submitted_at         TEXT,
        approved_at          TEXT,
        bank_reference       TEXT NOT NULL DEFAULT '',
        confirmation_doc_path TEXT NOT NULL DEFAULT '',
        created_at           TEXT NOT NULL,
        updated_at           TEXT NOT NULL
    )""",

    # Approval steps — one row per step per request
    """CREATE TABLE IF NOT EXISTS approval_steps (
        id             TEXT PRIMARY KEY,
        request_id     TEXT NOT NULL REFERENCES payment_requests(id) ON DELETE CASCADE,
        step_order     INTEGER NOT NULL,
        step_type      TEXT NOT NULL,
        assigned_to    TEXT NOT NULL,
        stand_in_for   TEXT,
        status         TEXT NOT NULL DEFAULT 'pending',
        due_by         TEXT NOT NULL,
        reminder_sent_at TEXT,
        escalated_at   TEXT,
        decided_at     TEXT,
        notes          TEXT NOT NULL DEFAULT '',
        created_at     TEXT NOT NULL,
        UNIQUE(request_id, step_order)
    )""",

    # Payout action log — immutable audit trail with SHA-256 tamper-evident chaining
    """CREATE TABLE IF NOT EXISTS payout_action_log (
        id          TEXT PRIMARY KEY,
        request_id  TEXT NOT NULL REFERENCES payment_requests(id),
        step_id     TEXT,
        actor_email TEXT NOT NULL,
        action      TEXT NOT NULL,
        notes       TEXT NOT NULL DEFAULT '',
        source      TEXT NOT NULL DEFAULT 'web',
        created_at  TEXT NOT NULL,
        prev_hash   TEXT NOT NULL DEFAULT '',  -- hash of previous entry in this request
        entry_hash  TEXT NOT NULL DEFAULT ''   -- SHA-256(request_id||actor_email||action||notes||created_at||prev_hash)
    )""",

    # Payout-related indexes
    "CREATE INDEX IF NOT EXISTS idx_pr_entity   ON payment_requests(entity)",
    "CREATE INDEX IF NOT EXISTS idx_pr_status   ON payment_requests(status)",
    "CREATE INDEX IF NOT EXISTS idx_pr_raised   ON payment_requests(raised_by)",
    "CREATE INDEX IF NOT EXISTS idx_as_request  ON approval_steps(request_id)",
    "CREATE INDEX IF NOT EXISTS idx_as_assigned ON approval_steps(assigned_to, status) WHERE status='pending'",
    "CREATE INDEX IF NOT EXISTS idx_pal_request ON payout_action_log(request_id)",

    # SHA-256 chain columns — added after initial deployment to existing DBs
    # The ALTER TABLE migrate() wrapper silently ignores duplicate-column errors.
    "ALTER TABLE payout_action_log ADD COLUMN prev_hash  TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE payout_action_log ADD COLUMN entry_hash TEXT NOT NULL DEFAULT ''",
]

# All available permissions in the system
ALL_PERMISSIONS = [
    "trigger_run",       # start a reconciliation run
    "upload_files",      # upload bank statements / ledger exports
    "fetch_statement",   # trigger automated bank statement pull
    "fetch_ledger",      # trigger automated GL pull from Symplus
    "approve_match",     # approve/reject proposed matches in review queue
    "signoff_run",       # checker sign-off on a completed run
    "approve_posting",   # approve draft journals for posting
    "post_to_ledger",    # execute the actual post to Symplus/ledger
    "view_audit",        # access the audit log
    "view_reports",      # view reconciliation reports
    "manage_accounts",   # configure accounts in accounts.yaml
    "manage_users",      # admin: add / edit / deactivate users
    "manage_connectors", # configure bank / ledger connection credentials
    "raise_payout",      # create and submit payment requests
    "approve_payout",    # act on approval steps
    "pay_payout",        # mark as sent to bank
    "confirm_payout",    # attach bank confirmation
]


def migrate():
    """Apply schema extensions and seed the admin user."""
    import sqlite3 as _sqlite3
    with get_db() as con:
        for sql in MIGRATIONS:
            stripped = sql.strip().upper()
            if stripped.startswith("ALTER TABLE"):
                # SQLite < 3.37 does not support IF NOT EXISTS in ALTER TABLE.
                # Catch the "duplicate column" error silently — it means the
                # column already exists, which is the intended idempotent result.
                try:
                    con.execute(sql)
                except _sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise
            else:
                con.execute(sql)

    _seed_admin()
    _seed_payment_accounts()
    _seed_beneficiaries()


def _seed_admin():
    """Create a default admin user on first boot if no users exist."""
    from app.config import settings
    with get_db() as con:
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count > 0:
            return

        import bcrypt
        pw = settings.admin_password.encode()
        hashed = bcrypt.hashpw(pw, bcrypt.gensalt()).decode()
        now = _now()
        cur = con.execute(
            "INSERT INTO users(name, email, password_hash, is_admin, is_active, created_at, updated_at) "
            "VALUES (?,?,?,1,1,?,?)",
            ("Administrator", settings.admin_email, hashed, now, now),
        )
        admin_id = cur.lastrowid
        # Admin gets all permissions
        con.executemany(
            "INSERT OR IGNORE INTO permissions(user_id, permission) VALUES (?,?)",
            [(admin_id, p) for p in ALL_PERMISSIONS],
        )
        print(f"[startup] Admin user created: {settings.admin_email}")


def _seed_payment_accounts():
    """Insert the two Providus NGN disbursement accounts if the table is empty."""
    with get_db() as con:
        count = con.execute("SELECT COUNT(*) FROM payment_accounts").fetchone()[0]
        if count > 0:
            return
        now = _now()
        accounts = [
            ("PAM", "Providus Bank", "PAGE ASSET - DISC PRESTIGE", "1309544279", "16:00"),
            ("PCL", "Providus Bank", "Page Capital Limited",        "5401941794", "16:00"),
        ]
        con.executemany(
            "INSERT OR IGNORE INTO payment_accounts"
            "(entity, bank_name, account_name, account_number, cut_off_time, is_active, created_at) "
            "VALUES (?,?,?,?,?,1,?)",
            [(*a, now) for a in accounts],
        )
        print(f"[startup] Seeded {len(accounts)} payment accounts")


def _seed_beneficiaries():
    """
    Load client beneficiaries from the PAML & PCL Excel register.
    Inserts with ON CONFLICT DO NOTHING so re-runs are idempotent.
    Requires openpyxl.
    """
    xlsx_path = Path(
        "/Users/nonsookoroafor/Downloads/Client Account Register-PAML & PCL.xlsx"
    )
    if not xlsx_path.exists():
        print(f"[startup] Beneficiary register not found at {xlsx_path} — skipping seed")
        return

    with get_db() as con:
        existing = con.execute("SELECT COUNT(*) FROM client_beneficiaries").fetchone()[0]
        if existing > 0:
            return

    try:
        import openpyxl
    except ImportError:
        print("[startup] openpyxl not installed — skipping beneficiary seed")
        return

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    now = _now()
    rows_to_insert: list[tuple] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        name_upper = sheet_name.strip().upper()
        if "PAML" in name_upper or "PAM" in name_upper:
            entity = "PAM"
        elif "PCL" in name_upper:
            entity = "PCL"
        else:
            # Try to infer from sheet content or skip
            continue

        header_row = None
        col_map: dict[str, int] = {}

        for row in ws.iter_rows():
            values = [str(c.value).strip() if c.value is not None else "" for c in row]
            if header_row is None:
                # Find the header row by looking for key column names
                lower_vals = [v.lower() for v in values]
                if any(kw in " ".join(lower_vals) for kw in ("client", "name", "account")):
                    header_row = values
                    for idx, h in enumerate(header_row):
                        hl = h.lower()
                        if "client" in hl and "name" in hl:
                            col_map.setdefault("client_name", idx)
                        elif "client" in hl and ("id" in hl or "code" in hl or "number" in hl):
                            col_map.setdefault("client_id", idx)
                        elif "bank" in hl:
                            col_map.setdefault("bank_name", idx)
                        elif "account" in hl and ("no" in hl or "num" in hl or "number" in hl):
                            col_map.setdefault("account_number", idx)
                        elif "account" in hl and "name" in hl:
                            col_map.setdefault("account_name_alt", idx)
                continue

            if not col_map:
                continue

            client_name = values[col_map["client_name"]] if "client_name" in col_map else ""
            client_id   = values[col_map["client_id"]]   if "client_id"   in col_map else ""
            bank_name   = values[col_map["bank_name"]]   if "bank_name"   in col_map else ""
            acc_num     = values[col_map["account_number"]] if "account_number" in col_map else ""

            # Fall back to account_name_alt for client_name if not found
            if not client_name and "account_name_alt" in col_map:
                client_name = values[col_map["account_name_alt"]]

            if not client_name or not acc_num:
                continue
            # Skip rows that are obviously blank or repeat the header
            if acc_num.lower() in ("account number", "account no", "acct no", "acct number"):
                continue

            rows_to_insert.append(
                (entity, client_name, client_id, bank_name, acc_num, 1, now)
            )

    wb.close()

    if not rows_to_insert:
        print("[startup] No beneficiary rows extracted from Excel — check column headers")
        return

    with get_db() as con:
        con.executemany(
            "INSERT OR IGNORE INTO client_beneficiaries"
            "(entity, client_name, client_id, bank_name, account_number, is_active, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            rows_to_insert,
        )
    print(f"[startup] Seeded {len(rows_to_insert)} client beneficiaries")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── User queries ───────────────────────────────────────────────────────────────

def user_get_by_email(email: str) -> dict | None:
    with get_db() as con:
        row = con.execute("SELECT * FROM users WHERE email=? AND is_active=1", (email,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["permissions"] = _user_permissions(d["id"])
    return d


def user_get_by_id(user_id: int) -> dict | None:
    with get_db() as con:
        row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["permissions"] = _user_permissions(d["id"])
    return d


def user_list() -> list[dict]:
    with get_db() as con:
        rows = con.execute("SELECT * FROM users ORDER BY name").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["permissions"] = _user_permissions(d["id"])
        d.pop("password_hash", None)
        result.append(d)
    return result


def user_create(name: str, email: str, password: str,
                is_admin: bool, permissions: list[str]) -> dict:
    import bcrypt
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    now = _now()
    with get_db() as con:
        cur = con.execute(
            "INSERT INTO users(name, email, password_hash, is_admin, is_active, created_at, updated_at) "
            "VALUES (?,?,?,?,1,?,?)",
            (name, email, hashed, int(is_admin), now, now),
        )
        uid = cur.lastrowid
        perms = list(set(permissions))
        if is_admin:
            perms = ALL_PERMISSIONS
        con.executemany(
            "INSERT OR IGNORE INTO permissions(user_id, permission) VALUES (?,?)",
            [(uid, p) for p in perms],
        )
    return user_get_by_id(uid)


def user_update(user_id: int, *, name: str | None = None, is_active: bool | None = None,
                permissions: list[str] | None = None, password: str | None = None) -> dict | None:
    with get_db() as con:
        if name is not None:
            con.execute("UPDATE users SET name=?, updated_at=? WHERE id=?", (name, _now(), user_id))
        if is_active is not None:
            con.execute("UPDATE users SET is_active=?, updated_at=? WHERE id=?", (int(is_active), _now(), user_id))
        if password is not None:
            import bcrypt
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            con.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?", (hashed, _now(), user_id))
        if permissions is not None:
            con.execute("DELETE FROM permissions WHERE user_id=?", (user_id,))
            con.executemany(
                "INSERT OR IGNORE INTO permissions(user_id, permission) VALUES (?,?)",
                [(user_id, p) for p in set(permissions)],
            )
    return user_get_by_id(user_id)


def user_delete(user_id: int):
    with get_db() as con:
        con.execute("DELETE FROM users WHERE id=?", (user_id,))


def user_verify_password(email: str, password: str) -> dict | None:
    import bcrypt
    user = user_get_by_email(email)
    if not user:
        return None
    row_hash = None
    with get_db() as con:
        row = con.execute("SELECT password_hash FROM users WHERE email=?", (email,)).fetchone()
        if row:
            row_hash = row[0]
    if not row_hash:
        return None
    if bcrypt.checkpw(password.encode(), row_hash.encode()):
        return user
    return None


def _user_permissions(user_id: int) -> list[str]:
    with get_db() as con:
        rows = con.execute("SELECT permission FROM permissions WHERE user_id=?", (user_id,)).fetchall()
    return [r[0] for r in rows]


# ── Run queries ────────────────────────────────────────────────────────────────

def run_list() -> list[dict]:
    with get_db() as con:
        rows = con.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def run_get(run_id: str) -> dict | None:
    with get_db() as con:
        row = con.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def run_open_items(run_id: str) -> list[dict]:
    with get_db() as con:
        rows = con.execute(
            "SELECT run_id, account_id, uid, side, payload FROM open_items WHERE run_id=?",
            (run_id,),
        ).fetchall()
    result = []
    for r in rows:
        try:
            item = json.loads(r[4])
        except Exception:
            item = {}
        item.setdefault("uid", r[2])
        item.setdefault("run_id", r[0])
        item.setdefault("account_id", r[1])
        item.setdefault("side", r[3])
        for k, v in [("source_row", 0), ("running_balance", None), ("doc_type", ""),
                     ("refs", ""), ("category", ""), ("origin_period", ""),
                     ("currency", "NGN"), ("reference", ""), ("description", "")]:
            item.setdefault(k, v)
        result.append(item)
    result.sort(key=lambda x: (x.get("side", ""), x.get("txn_date", "")))
    return result


def run_matches(run_id: str) -> list[dict]:
    with get_db() as con:
        rows = con.execute(
            "SELECT * FROM matches WHERE run_id=? ORDER BY confidence DESC",
            (run_id,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["bank_uids"] = json.loads(d["bank_uids"])
        d["book_uids"] = json.loads(d["book_uids"])
        result.append(d)
    return result


def decisions_for_account(account_id: str) -> list[dict]:
    with get_db() as con:
        rows = con.execute(
            "SELECT * FROM decisions WHERE account_id=? ORDER BY created_at DESC",
            (account_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def audit_list(limit: int = 200) -> list[dict]:
    with get_db() as con:
        rows = con.execute(
            "SELECT * FROM audit_log ORDER BY seq DESC LIMIT ?", (limit,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("detail") or "{}")
        except Exception:
            d["payload"] = {}
        result.append(d)
    return result


def save_matches(run_id: str, matches: list[dict]):
    with get_db() as con:
        con.execute("DELETE FROM matches WHERE run_id=?", (run_id,))
        con.executemany(
            """INSERT OR REPLACE INTO matches
               (match_id,run_id,rule,confidence,bank_uids,book_uids,status,difference,note)
               VALUES (:match_id,:run_id,:rule,:confidence,:bank_uids,:book_uids,:status,:difference,:note)""",
            [{**m, "run_id": run_id,
              "bank_uids": json.dumps(m["bank_uids"]),
              "book_uids": json.dumps(m["book_uids"])}
             for m in matches],
        )


def signoff_run(run_id: str, checker: str, note: str):
    with get_db() as con:
        run = con.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not run:
            raise ValueError(f"Run {run_id} not found")
        if run["maker"] == checker:
            raise PermissionError("Checker cannot be the same person as the maker")
        if run["signed_at"]:
            raise ValueError(f"Run {run_id} is already signed off")
        con.execute(
            "UPDATE runs SET checker=?, signed_at=?, signoff_note=? WHERE run_id=?",
            (checker, _now(), note, run_id),
        )


def save_decision(account_id: str, action: str, bank_uids: list, book_uids: list,
                  reviewer: str, note: str):
    with get_db() as con:
        con.execute(
            "INSERT INTO decisions(account_id,action,bank_uids,book_uids,reviewer,note,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (account_id, action, ";".join(bank_uids), ";".join(book_uids), reviewer, note, _now()),
        )


def save_uploaded_file(account_id: str, period: str, filename: str,
                       stored_path: str, size: int, file_hash: str,
                       uploaded_by: str) -> int:
    with get_db() as con:
        cur = con.execute(
            "INSERT INTO uploaded_files(account_id,period,filename,stored_path,size,file_hash,uploaded_by,uploaded_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (account_id, period, filename, stored_path, size, file_hash, uploaded_by, _now()),
        )
        return cur.lastrowid


def uploaded_files(account_id: str | None = None) -> list[dict]:
    with get_db() as con:
        if account_id:
            rows = con.execute(
                "SELECT * FROM uploaded_files WHERE account_id=? ORDER BY uploaded_at DESC",
                (account_id,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM uploaded_files ORDER BY uploaded_at DESC LIMIT 100"
            ).fetchall()
    return [dict(r) for r in rows]


# ── Run journals ──────────────────────────────────────────────────────────────

def save_run_journals(run_id: str, account_id: str, journals: list[dict]):
    """Persist draft journals produced by a reconciliation run."""
    with get_db() as con:
        con.execute("DELETE FROM run_journals WHERE run_id=?", (run_id,))
        con.executemany(
            """INSERT INTO run_journals
               (run_id, account_id, date, category, dr_gl, cr_gl, amount, narration, lines, uid, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [(run_id, account_id, j["date"], j["category"],
              j["dr_gl"], j["cr_gl"], j["amount"], j["narration"],
              j.get("lines", 1), j["uid"],
              "HOLD" if j.get("status", "").startswith("HOLD") else "DRAFT")
             for j in journals],
        )


def run_journals_list(run_id: str) -> list[dict]:
    with get_db() as con:
        rows = con.execute(
            "SELECT * FROM run_journals WHERE run_id=? ORDER BY date, category",
            (run_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def run_journal_approve(journal_id: int, approved_by: str):
    with get_db() as con:
        con.execute(
            "UPDATE run_journals SET status='APPROVED' WHERE id=?", (journal_id,)
        )


def update_report_path(run_id: str, path: str):
    with get_db() as con:
        con.execute("UPDATE runs SET report_path=? WHERE run_id=?", (path, run_id))


# ── Posting queue ──────────────────────────────────────────────────────────────

def posting_queue_add(run_id: str, account_id: str, journals: list[dict]) -> list[int]:
    ids = []
    with get_db() as con:
        for j in journals:
            cur = con.execute(
                "INSERT INTO posting_queue(run_id,account_id,category,payload,status,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (run_id, account_id, j.get("category", ""), json.dumps(j), "PENDING", _now()),
            )
            ids.append(cur.lastrowid)
    return ids


def posting_queue_approve(item_id: int, approved_by: str):
    with get_db() as con:
        con.execute(
            "UPDATE posting_queue SET status='APPROVED', approved_by=?, approved_at=? WHERE id=?",
            (approved_by, _now(), item_id),
        )


def posting_queue_list(run_id: str | None = None, status: str | None = None) -> list[dict]:
    with get_db() as con:
        clauses, params = [], []
        if run_id:
            clauses.append("run_id=?"); params.append(run_id)
        if status:
            clauses.append("status=?"); params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = con.execute(f"SELECT * FROM posting_queue {where} ORDER BY created_at DESC", params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["journal"] = json.loads(d["payload"])
        except Exception:
            d["journal"] = {}
        result.append(d)
    return result


def posting_queue_mark_posted(item_id: int, posted_by: str, post_ref: str):
    with get_db() as con:
        con.execute(
            "UPDATE posting_queue SET status='POSTED', posted_by=?, posted_at=?, post_ref=? WHERE id=?",
            (posted_by, _now(), post_ref, item_id),
        )


def posting_queue_mark_failed(item_id: int, error: str):
    with get_db() as con:
        con.execute(
            "UPDATE posting_queue SET status='FAILED', error=? WHERE id=?",
            (error, item_id),
        )


# ── Connector log ──────────────────────────────────────────────────────────────

def connector_log(connector: str, account_id: str, action: str,
                  status: str, detail: str | None = None, triggered_by: str | None = None):
    with get_db() as con:
        con.execute(
            "INSERT INTO connector_logs(connector,account_id,action,status,detail,triggered_by,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (connector, account_id, action, status, detail, triggered_by, _now()),
        )


# ── Payout helpers ─────────────────────────────────────────────────────────────

def payout_list_accounts(entity: str | None = None) -> list[dict]:
    """Return all active payment accounts, optionally filtered by entity."""
    with get_db() as con:
        if entity:
            rows = con.execute(
                "SELECT * FROM payment_accounts WHERE entity=? ORDER BY id",
                (entity,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM payment_accounts ORDER BY entity, id"
            ).fetchall()
    return [dict(r) for r in rows]


def payout_get_account(account_id: int) -> dict | None:
    """Fetch a single payment account by id."""
    with get_db() as con:
        row = con.execute(
            "SELECT * FROM payment_accounts WHERE id=?", (account_id,)
        ).fetchone()
    return dict(row) if row else None


def payout_check_beneficiary(entity: str, account_number: str) -> bool:
    """Return True if the account_number is registered as an active beneficiary for the entity."""
    with get_db() as con:
        row = con.execute(
            "SELECT id FROM client_beneficiaries WHERE entity=? AND account_number=? AND is_active=1",
            (entity, account_number),
        ).fetchone()
    return row is not None


def payout_get_approver(entity: str, role: str) -> str | None:
    """
    Read approval_roles.yaml and return the email for the given entity + role.
    Returns None if the entity or role is not found.
    """
    import yaml

    yaml_path = Path(__file__).parent / "approval_roles.yaml"
    if not yaml_path.exists():
        # Fallback to the config directory used by the engine
        yaml_path = Path(__file__).parent.parent.parent / "pcg_recon" / "config" / "approval_roles.yaml"
    if not yaml_path.exists():
        return None

    with open(yaml_path) as fh:
        data = yaml.safe_load(fh)

    try:
        return data["entities"][entity][role]
    except (KeyError, TypeError):
        return None


def payout_get_standin(email: str) -> str | None:
    """Return the cover email for the given user email, or None."""
    with get_db() as con:
        row = con.execute(
            "SELECT cover_email FROM stand_ins WHERE user_email=?", (email,)
        ).fetchone()
    return row["cover_email"] if row else None


def payout_count_for_year(entity: str, year: int) -> int:
    """Count payment requests for an entity in a given calendar year."""
    with get_db() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM payment_requests WHERE entity=? AND created_at LIKE ?",
            (entity, f"{year}%"),
        ).fetchone()
    return row[0] if row else 0


def payout_create(data: dict) -> dict:
    """Insert a new payment request row and return the created record."""
    with get_db() as con:
        con.execute(
            """INSERT INTO payment_requests
               (id, instruction_id, entity, request_type, payment_account_id,
                amount_kobo, beneficiary_name, beneficiary_bank, beneficiary_account,
                purpose, supporting_doc_path, status, compliance_flagged,
                raised_by, submitted_at, approved_at, bank_reference,
                confirmation_doc_path, created_at, updated_at)
               VALUES
               (:id, :instruction_id, :entity, :request_type, :payment_account_id,
                :amount_kobo, :beneficiary_name, :beneficiary_bank, :beneficiary_account,
                :purpose, :supporting_doc_path, :status, :compliance_flagged,
                :raised_by, :submitted_at, :approved_at, :bank_reference,
                :confirmation_doc_path, :created_at, :updated_at)""",
            data,
        )
    return payout_get(data["id"])


def payout_get(request_id: str) -> dict | None:
    """Fetch a single payment request by id."""
    with get_db() as con:
        row = con.execute(
            "SELECT * FROM payment_requests WHERE id=?", (request_id,)
        ).fetchone()
    return dict(row) if row else None


def payout_update(request_id: str, **kwargs) -> None:
    """Update arbitrary columns on a payment request."""
    if not kwargs:
        return
    kwargs["updated_at"] = _now()
    set_clause = ", ".join(f"{k}=?" for k in kwargs)
    params = list(kwargs.values()) + [request_id]
    with get_db() as con:
        con.execute(
            f"UPDATE payment_requests SET {set_clause} WHERE id=?", params
        )


def payout_list(
    entity: str | None = None,
    status: str | None = None,
    raised_by: str | None = None,
) -> list[dict]:
    """Return payment requests with optional filters."""
    clauses, params = [], []
    if entity:
        clauses.append("entity=?"); params.append(entity)
    if status:
        clauses.append("status=?"); params.append(status)
    if raised_by:
        clauses.append("raised_by=?"); params.append(raised_by)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_db() as con:
        rows = con.execute(
            f"SELECT * FROM payment_requests {where} ORDER BY created_at DESC", params
        ).fetchall()
    return [dict(r) for r in rows]


def payout_create_step(step: dict) -> None:
    """Insert an approval step row."""
    with get_db() as con:
        con.execute(
            """INSERT INTO approval_steps
               (id, request_id, step_order, step_type, assigned_to, stand_in_for,
                status, due_by, reminder_sent_at, escalated_at, decided_at,
                notes, created_at)
               VALUES
               (:id, :request_id, :step_order, :step_type, :assigned_to, :stand_in_for,
                :status, :due_by, :reminder_sent_at, :escalated_at, :decided_at,
                :notes, :created_at)""",
            step,
        )


def payout_get_active_step(request_id: str) -> dict | None:
    """Return the first pending step for a request, or None."""
    with get_db() as con:
        row = con.execute(
            "SELECT * FROM approval_steps WHERE request_id=? AND status='pending' "
            "ORDER BY step_order LIMIT 1",
            (request_id,),
        ).fetchone()
    return dict(row) if row else None


def payout_get_steps(request_id: str) -> list[dict]:
    """Return all approval steps for a request ordered by step_order."""
    with get_db() as con:
        rows = con.execute(
            "SELECT * FROM approval_steps WHERE request_id=? ORDER BY step_order",
            (request_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def payout_update_step(step_id: str, **kwargs) -> None:
    """Update arbitrary columns on an approval step."""
    if not kwargs:
        return
    set_clause = ", ".join(f"{k}=?" for k in kwargs)
    params = list(kwargs.values()) + [step_id]
    with get_db() as con:
        con.execute(
            f"UPDATE approval_steps SET {set_clause} WHERE id=?", params
        )


def payout_log_action(data: dict) -> None:
    """Insert an immutable, SHA-256 hash-chained entry into payout_action_log."""
    with get_db() as con:
        # Fetch the last entry_hash for this request to build the chain
        row = con.execute(
            "SELECT entry_hash FROM payout_action_log "
            "WHERE request_id=? ORDER BY created_at DESC LIMIT 1",
            (data["request_id"],),
        ).fetchone()
        prev_hash = row["entry_hash"] if row else ""

        # Compute entry_hash = SHA-256(request_id + actor_email + action + notes + created_at + prev_hash)
        raw = (
            (data["request_id"] or "")
            + (data["actor_email"] or "")
            + (data["action"] or "")
            + (data["notes"] or "")
            + (data["created_at"] or "")
            + prev_hash
        )
        entry_hash = hashlib.sha256(raw.encode()).hexdigest()

        row_data = {**data, "prev_hash": prev_hash, "entry_hash": entry_hash}
        con.execute(
            """INSERT INTO payout_action_log
               (id, request_id, step_id, actor_email, action, notes, source, created_at,
                prev_hash, entry_hash)
               VALUES
               (:id, :request_id, :step_id, :actor_email, :action, :notes, :source, :created_at,
                :prev_hash, :entry_hash)""",
            row_data,
        )


def payout_get_action_log(request_id: str) -> list[dict]:
    """Return the full action log for a request ordered chronologically."""
    with get_db() as con:
        rows = con.execute(
            "SELECT * FROM payout_action_log WHERE request_id=? ORDER BY created_at",
            (request_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def payout_verify_chain(request_id: str) -> bool:
    """
    Verify the SHA-256 tamper-evident chain for a request's action log.

    Loads all entries ordered by created_at, recomputes each entry_hash, and
    confirms it matches both the stored entry_hash and the next row's prev_hash.

    Returns True if the chain is intact, False if any entry has been tampered with.
    """
    with get_db() as con:
        rows = con.execute(
            "SELECT request_id, actor_email, action, notes, created_at, prev_hash, entry_hash "
            "FROM payout_action_log WHERE request_id=? ORDER BY created_at",
            (request_id,),
        ).fetchall()

    prev_hash = ""
    for row in rows:
        # Verify that the stored prev_hash matches what we expect
        if row["prev_hash"] != prev_hash:
            return False

        # Recompute entry_hash
        raw = (
            (row["request_id"] or "")
            + (row["actor_email"] or "")
            + (row["action"] or "")
            + (row["notes"] or "")
            + (row["created_at"] or "")
            + prev_hash
        )
        expected_hash = hashlib.sha256(raw.encode()).hexdigest()

        if row["entry_hash"] != expected_hash:
            return False

        prev_hash = row["entry_hash"]

    return True


def payout_pending_for_user(email: str) -> list[dict]:
    """
    Return all pending approval steps assigned to the given email,
    joined with their parent payment request data.
    """
    with get_db() as con:
        rows = con.execute(
            """SELECT
                   r.id,
                   s.id            AS step_id,
                   s.request_id,
                   s.step_order,
                   s.step_type,
                   s.assigned_to,
                   s.stand_in_for,
                   s.due_by,
                   s.reminder_sent_at,
                   s.escalated_at,
                   s.created_at    AS step_created_at,
                   r.instruction_id,
                   r.entity,
                   r.request_type,
                   r.amount_kobo,
                   r.beneficiary_name,
                   r.beneficiary_bank,
                   r.beneficiary_account,
                   r.purpose,
                   r.status        AS request_status,
                   r.raised_by,
                   r.submitted_at,
                   r.updated_at,
                   r.created_at    AS request_created_at
               FROM approval_steps s
               JOIN payment_requests r ON r.id = s.request_id
               WHERE s.assigned_to=? AND s.status='pending'
               ORDER BY s.due_by""",
            (email,),
        ).fetchall()
    return [dict(r) for r in rows]


def payout_get_overdue_steps() -> list[dict]:
    """
    Return all pending approval steps whose due_by timestamp is in the past,
    joined with key fields from the parent payment request.
    """
    now = _now()
    with get_db() as con:
        rows = con.execute(
            """SELECT
                   s.id            AS step_id,
                   s.request_id,
                   s.step_order,
                   s.step_type,
                   s.assigned_to,
                   s.stand_in_for,
                   s.due_by,
                   s.reminder_sent_at,
                   s.escalated_at,
                   r.instruction_id,
                   r.entity,
                   r.request_type,
                   r.amount_kobo,
                   r.raised_by
               FROM approval_steps s
               JOIN payment_requests r ON r.id = s.request_id
               WHERE s.status='pending' AND s.due_by < ?
               ORDER BY s.due_by""",
            (now,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── PIN helpers ────────────────────────────────────────────────────────────────

def pin_set(user_id: int, pin_hash: str) -> None:
    """Store (or replace) a PIN hash for the given user and clear any lockout."""
    with get_db() as con:
        con.execute(
            "UPDATE users SET pin_hash=?, pin_attempts=0, pin_locked_until=NULL WHERE id=?",
            (pin_hash, user_id),
        )


def pin_get(email: str) -> dict | None:
    """Return id, pin_hash, pin_attempts, pin_locked_until for the given email."""
    with get_db() as con:
        row = con.execute(
            "SELECT id, pin_hash, pin_attempts, pin_locked_until FROM users WHERE email=?",
            (email,),
        ).fetchone()
    return dict(row) if row else None


def pin_increment_attempts(user_id: int, lock_until: str | None) -> None:
    """Increment failed PIN attempts and optionally set a lockout timestamp."""
    with get_db() as con:
        con.execute(
            "UPDATE users SET pin_attempts=pin_attempts+1, pin_locked_until=? WHERE id=?",
            (lock_until, user_id),
        )


def pin_reset_attempts(user_id: int) -> None:
    """Clear failed PIN attempt count and remove any lockout."""
    with get_db() as con:
        con.execute(
            "UPDATE users SET pin_attempts=0, pin_locked_until=NULL WHERE id=?",
            (user_id,),
        )
