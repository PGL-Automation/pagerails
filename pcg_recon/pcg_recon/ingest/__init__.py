"""Source dispatcher: turns an account's feed config into canonical Txns."""
from __future__ import annotations

import glob
from pathlib import Path

from ..model import Txn, StatementMeta
from .tabular import read_tabular, finalize_meta
from .mt940 import read_mt940
from .pdf import read_pdf
from .ledger_pg import read_postgres


def _files(pattern: str, base: Path) -> list[Path]:
    hits = sorted(glob.glob(str(base / pattern)))
    return [Path(h) for h in hits]


def load_feed(feed: dict, account_id: str, side: str, period, profiles: dict, base: Path,
              ctx: dict | None = None) -> tuple[list[Txn], StatementMeta]:
    fmt = feed["format"]
    if fmt == "postgres":
        return read_postgres(feed, account_id, period, ctx or {})
    files = _files(feed["path"], base)
    if not files:
        raise FileNotFoundError(f"{account_id} {side}: no file matches {feed['path']}")
    all_txns: list[Txn] = []
    metas: list[StatementMeta] = []
    for f in files:
        if fmt == "mt940":
            t, m = read_mt940(f, account_id, period)
        elif fmt == "pdf":
            t, m = read_pdf(f, account_id, profiles.get(feed.get("profile"), {}), period)
        elif fmt == "tabular":
            prof = profiles[feed["profile"]]
            prof = {**prof, **{k: v for k, v in feed.items() if k in ("account_filter", "sheet")}}
            t, m = read_tabular(f, prof, account_id, side, period)
        else:
            raise ValueError(f"Unknown feed format {fmt}")
        if period and not t:
            continue          # file covers another period (e.g. last month's download)
        for x in t:
            x.side = side
        all_txns.extend(t)
        metas.append(m)
    if not metas:
        raise ValueError(f"{account_id} {side}: files found but none contain transactions in the period "
                         f"({', '.join(f.name for f in files)})")
    # multi-file: statements must chain (close of file n == open of file n+1)
    meta = metas[0]
    for m in metas[1:]:
        if meta.closing_balance is not None and m.opening_balance is not None \
                and meta.closing_balance != m.opening_balance:
            meta.continuity_breaks.append({"row": f"{m.source} (file chain)", "expected": meta.closing_balance,
                                           "stated": m.opening_balance,
                                           "gap": m.opening_balance - meta.closing_balance})
        meta.closing_balance = m.closing_balance
        meta.continuity_breaks.extend(m.continuity_breaks)
        meta.period_end = m.period_end
        meta.source += f", {m.source}"
    # de-duplicate overlapping downloads (same row exported twice across files)
    seen, uniq = set(), []
    for t in all_txns:
        key = (t.txn_date, t.amount, t.reference, t.description, t.running_balance)
        if len(files) > 1 and key in seen and t.running_balance is not None:
            continue
        seen.add(key)
        uniq.append(t)
    return uniq, meta
