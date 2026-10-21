"""PostgreSQL ledger adapter — reads the bank GL account directly from the group's
double-entry ledger (the PostgreSQL design, AWS af-south-1).

The default SQL assumes a conventional journal_entry / journal_line schema with
amounts stored in minor units. Override `sql` / `opening_sql` in the feed config
to match the final schema; the query must return the columns
    source_row, txn_date, reference, description, amount_minor, doc_type
where amount_minor = debit - credit on the bank GL account (money in = positive).
"""
from __future__ import annotations

import os

from ..model import Txn, StatementMeta
from ..refs import extract_refs

DEFAULT_SQL = """
SELECT jl.line_id              AS source_row,
       je.posting_date         AS txn_date,
       COALESCE(je.reference,'') AS reference,
       COALESCE(jl.narration, je.narration, '') AS description,
       (jl.debit_minor - jl.credit_minor) AS amount_minor,
       COALESCE(je.doc_type,'') AS doc_type
FROM   gl.journal_line jl
JOIN   gl.journal_entry je ON je.entry_id = jl.entry_id
WHERE  je.entity_code   = %(entity)s
AND    jl.account_code  = %(gl_account)s
AND    je.status        = 'POSTED'
AND    je.posting_date BETWEEN %(start)s AND %(end)s
ORDER  BY je.posting_date, jl.line_id
"""

DEFAULT_OPENING_SQL = """
SELECT COALESCE(SUM(jl.debit_minor - jl.credit_minor), 0)
FROM   gl.journal_line jl JOIN gl.journal_entry je ON je.entry_id = jl.entry_id
WHERE  je.entity_code = %(entity)s AND jl.account_code = %(gl_account)s
AND    je.status = 'POSTED' AND je.posting_date < %(start)s
"""


def read_postgres(feed: dict, account_id: str, period, ctx: dict):
    try:
        import psycopg
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pip install 'psycopg[binary]' to use the postgres ledger feed") from e
    dsn = os.environ.get(feed.get("dsn_env", "PCG_LEDGER_DSN"))
    if not dsn:
        raise RuntimeError(f"Set {feed.get('dsn_env', 'PCG_LEDGER_DSN')} to the read-only ledger DSN")
    params = {"entity": ctx["entity"], "gl_account": ctx["gl_account"], "start": period[0], "end": period[1]}
    meta = StatementMeta(account_id=account_id, source="postgres:" + ctx["gl_account"])
    txns = []
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(feed.get("opening_sql", DEFAULT_OPENING_SQL), params)
        meta.opening_balance = int(cur.fetchone()[0])
        cur.execute(feed.get("sql", DEFAULT_SQL), params)
        for row in cur.fetchall():
            src, d, ref, desc, amt, dt = row
            t = Txn(side="BOOK", account_id=account_id, txn_date=d, amount=int(amt), description=desc,
                    reference=ref, source=meta.source, source_row=int(src), doc_type=dt)
            t.refs = extract_refs(desc, ref)
            txns.append(t)
    meta.closing_balance = meta.opening_balance + sum(t.amount for t in txns)
    meta.period_start, meta.period_end = period
    return txns, meta
