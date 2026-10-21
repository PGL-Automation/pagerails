"""Run store (SQLite): run history, carried-forward open items, reviewer decisions,
maker-checker sign-off and a hash-chained audit log.

SQLite keeps v1 dependency-free; the schema is plain SQL and moves to PostgreSQL
unchanged (swap the connection) when it joins the group ledger database.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, account_id TEXT, entity TEXT, period_start TEXT, period_end TEXT,
  created_at TEXT, maker TEXT, rules_hash TEXT, inputs_hash TEXT,
  bank_open INTEGER, bank_close INTEGER, book_open INTEGER, book_close INTEGER,
  adj_bank INTEGER, adj_book INTEGER, difference INTEGER, status TEXT,
  checker TEXT, signed_at TEXT, signoff_note TEXT, report_path TEXT);
CREATE TABLE IF NOT EXISTS open_items (
  run_id TEXT, account_id TEXT, uid TEXT, side TEXT, payload TEXT, PRIMARY KEY (run_id, uid));
CREATE TABLE IF NOT EXISTS matches (
  match_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, rule TEXT NOT NULL,
  confidence REAL NOT NULL, bank_uids TEXT NOT NULL, book_uids TEXT NOT NULL,
  status TEXT NOT NULL, difference INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT, action TEXT, bank_uids TEXT,
  book_uids TEXT, reviewer TEXT, note TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, detail TEXT,
  prev_hash TEXT, hash TEXT);
CREATE INDEX IF NOT EXISTS idx_matches_run ON matches(run_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ---------------------------------------------------------------- audit
    def audit(self, actor: str, action: str, detail: dict):
        row = self.db.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else "GENESIS"
        ts = now()
        body = json.dumps(detail, sort_keys=True, default=str)
        h = hashlib.sha256(f"{prev}|{ts}|{actor}|{action}|{body}".encode()).hexdigest()
        self.db.execute("INSERT INTO audit_log(ts,actor,action,detail,prev_hash,hash) VALUES (?,?,?,?,?,?)",
                        (ts, actor, action, body, prev, h))
        self.db.commit()

    def verify_audit_chain(self) -> tuple[bool, int]:
        prev = "GENESIS"
        n = 0
        for r in self.db.execute("SELECT * FROM audit_log ORDER BY seq"):
            h = hashlib.sha256(f"{prev}|{r['ts']}|{r['actor']}|{r['action']}|{r['detail']}".encode()).hexdigest()
            if r["prev_hash"] != prev or r["hash"] != h:
                return False, r["seq"]
            prev = h
            n += 1
        return True, n

    # ---------------------------------------------------------------- runs
    def prior_run(self, account_id: str, period_start: str):
        return self.db.execute(
            "SELECT * FROM runs WHERE account_id=? AND period_end < ? "
            "ORDER BY period_end DESC, (signed_at IS NOT NULL) DESC, created_at DESC LIMIT 1",
            (account_id, period_start)).fetchone()

    def carried_items(self, run_id: str) -> list[dict]:
        return [json.loads(r["payload"]) for r in
                self.db.execute("SELECT payload FROM open_items WHERE run_id=?", (run_id,))]

    def save_run(self, rec: dict, open_items: list, matches: list | None = None):
        cols = ",".join(rec)
        self.db.execute(f"INSERT OR REPLACE INTO runs({cols}) VALUES ({','.join('?' * len(rec))})",
                        list(rec.values()))
        self.db.execute("DELETE FROM open_items WHERE run_id=?", (rec["run_id"],))
        self.db.executemany("INSERT INTO open_items VALUES (?,?,?,?,?)",
                            [(rec["run_id"], rec["account_id"], t.uid, t.side,
                              json.dumps(t.to_row(), default=str)) for t in open_items])
        if matches is not None:
            self.db.execute("DELETE FROM matches WHERE run_id=?", (rec["run_id"],))
            self.db.executemany(
                "INSERT OR REPLACE INTO matches(match_id,run_id,rule,confidence,bank_uids,book_uids,status,difference,note) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                [(m.match_id, rec["run_id"], m.rule, m.confidence,
                  json.dumps(m.bank_uids), json.dumps(m.book_uids),
                  m.status, m.difference, m.note) for m in matches],
            )
        self.db.commit()

    def signoff(self, run_id: str, checker: str, note: str = ""):
        r = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not r:
            raise ValueError(f"No run {run_id}")
        if r["signed_at"]:
            raise ValueError(f"{run_id} already signed off by {r['checker']}")
        if checker.strip().lower() == (r["maker"] or "").strip().lower():
            raise PermissionError("Maker-checker: the preparer cannot sign off their own reconciliation")
        if r["difference"] != 0 and not note:
            raise PermissionError("Unreconciled difference: sign-off requires an explanatory note")
        self.db.execute("UPDATE runs SET checker=?, signed_at=?, signoff_note=? WHERE run_id=?",
                        (checker, now(), note, run_id))
        self.db.commit()
        self.audit(checker, "SIGNOFF", {"run_id": run_id, "difference": r["difference"], "note": note})

    # ---------------------------------------------------------------- decisions
    def add_decision(self, account_id, action, bank_uids, book_uids, reviewer, note=""):
        self.db.execute("INSERT INTO decisions(account_id,action,bank_uids,book_uids,reviewer,note,created_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (account_id, action.upper(), ";".join(bank_uids), ";".join(book_uids), reviewer, note, now()))
        self.db.commit()
        self.audit(reviewer, f"DECISION_{action.upper()}",
                   {"account_id": account_id, "bank": bank_uids, "book": book_uids, "note": note})

    def decisions(self, account_id: str) -> list[dict]:
        out = []
        for r in self.db.execute("SELECT * FROM decisions WHERE account_id=? ORDER BY id", (account_id,)):
            out.append({"action": r["action"], "bank_uids": (r["bank_uids"] or "").split(";"),
                        "book_uids": (r["book_uids"] or "").split(";"), "reviewer": r["reviewer"],
                        "note": r["note"]})
        return out

    def runs(self, period_end: str | None = None):
        q = "SELECT * FROM runs" + (" WHERE period_end=?" if period_end else "") + " ORDER BY account_id"
        return self.db.execute(q, (period_end,) if period_end else ()).fetchall()
