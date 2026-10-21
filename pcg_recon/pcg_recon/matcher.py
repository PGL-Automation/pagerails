"""Multi-pass matching engine.

Passes run in order of certainty; each pass only sees items left by earlier passes.

  D  : reviewer decisions from previous runs (APPROVE / MANUAL / REJECT) applied first
  P0 : self-cancelling reversals on the same side (failed NIP + reversal, reversed JV)
  P1 : shared strong reference (NIP session id, cheque no, ref code) + equal amount
  P2 : equal amount within the date window, ranked by date proximity + text similarity
  P3 : aggregates — one bank line vs several book lines (bulk payments, batched
       settlements) and one book line vs several bank lines (tranched receipts)
  P5 : charge sweep — bank-only charges booked as one journal per charge type, for a
       month or for all carried prior-period items (runs before P2)
  P4 : fuzzy — text similarity with optional amount tolerance (never auto-accepted)

Confidence >= auto_accept_confidence => AUTO; otherwise PROPOSED and the items stay
OPEN in the reconciliation statement until a reviewer approves the match.
"""
from __future__ import annotations

import itertools
from collections import defaultdict

from rapidfuzz import fuzz

from .model import Match, Txn
from .refs import strong, clean_text

REV_WORDS = ("REV ", "REV-", "REVERSAL", "RETURNED", "RVSL", "REVERSED")


def _sim(a: Txn, b: Txn) -> float:
    ta, tb = clean_text(a.description + " " + a.reference), clean_text(b.description + " " + b.reference)
    if not ta or not tb:
        return 0.0
    return fuzz.token_set_ratio(ta, tb) / 100.0


def _is_cheque(t: Txn) -> bool:
    return any(r.startswith("CHQ:") for r in t.refs) or t.doc_type.upper() in ("CHQ", "CHEQUE")


class Matcher:
    def __init__(self, bank: list[Txn], book: list[Txn], rules: dict, window_days: int,
                 client_money: bool = False, current_period: str = ""):
        self.rules_full = rules
        self.current_period = current_period
        self.bank = {t.uid: t for t in bank}
        self.book = {t.uid: t for t in book}
        self.open_bank = set(self.bank)
        self.open_book = set(self.book)
        self.m = rules["matching"]
        self.window = window_days
        self.client_money = client_money
        self.matches: list[Match] = []
        self.rejected: set[tuple[frozenset, frozenset]] = set()
        self._n = 0

    # ------------------------------------------------------------------ helpers
    def _mid(self) -> str:
        self._n += 1
        return f"M{self._n:05d}"

    def _commit(self, rule, conf, bank_uids, book_uids, note="", diff=0, status=None):
        key = (frozenset(bank_uids), frozenset(book_uids))
        if key in self.rejected:
            return False
        if status is None:
            status = "AUTO" if conf >= self.m["auto_accept_confidence"] else "PROPOSED"
        if self.client_money and diff != 0 and status == "AUTO":
            status = "PROPOSED"   # tolerance matches on client money always need a human
        self.matches.append(Match(self._mid(), rule, round(conf, 3), list(bank_uids), list(book_uids),
                                  status, diff, note))
        self.open_bank -= set(bank_uids)
        self.open_book -= set(book_uids)
        return True

    def _window_ok(self, bank_t: Txn, book_t: Txn) -> bool:
        dd = (bank_t.txn_date - book_t.txn_date).days
        if _is_cheque(bank_t) or _is_cheque(book_t):
            return -2 <= dd <= self.m["cheque_window_days"]     # cheque clears after issue
        return abs(dd) <= self.window

    # ------------------------------------------------------------------ passes
    def apply_decisions(self, decisions: list[dict]):
        for d in decisions:
            b = [u for u in d["bank_uids"] if u]
            k = [u for u in d["book_uids"] if u]
            if d["action"] == "REJECT":
                self.rejected.add((frozenset(b), frozenset(k)))
                continue
            if all(u in self.open_bank for u in b) and all(u in self.open_book for u in k) and (b or k):
                diff = sum(self.bank[u].amount for u in b) - sum(self.book[u].amount for u in k)
                self._commit("MANUAL" if d["action"] == "MANUAL" else "REVIEWED", 1.0, b, k,
                             note=f"{d['action']} by {d.get('reviewer', '?')}: {d.get('note', '')}",
                             diff=diff, status="APPROVED")

    def p0_reversals(self):
        """Equal-and-opposite items on one side. Stage A pairs on a shared reference
        (NIP session ID / doc number) — this is how banks like Providus reverse a failed
        transfer: every leg (principal, commission, VAT, stamp duty) comes back as its own
        credit carrying the original session ID. Stage B pairs on reversal wording alone,
        nearest date first; ties on small amounts go to review."""
        for side, pool, openset in (("BANK", self.bank, self.open_bank), ("BOOK", self.book, self.open_book)):
            by_abs = defaultdict(list)
            for u in openset:
                by_abs[abs(pool[u].amount)].append(pool[u])

            def commit(n, p, conf, note):
                uids = [n.uid, p.uid]
                if side == "BANK":
                    self._commit("P0_REVERSAL", conf, uids, [], note=note)
                else:
                    self._commit("P0_REVERSAL", conf, [], uids, note=note)

            for stage in ("A", "B"):
                for items in by_abs.values():
                    pos = sorted([t for t in items if t.amount > 0], key=lambda t: (t.txn_date, t.uid))
                    neg = sorted([t for t in items if t.amount < 0], key=lambda t: (t.txn_date, t.uid))
                    for n in neg:
                        if n.uid not in openset:
                            continue
                        cands = []
                        for p_ in pos:
                            if p_.uid not in openset:
                                continue
                            dd = abs((p_.txn_date - n.txn_date).days)
                            shared = strong(p_.refs) & strong(n.refs)
                            if stage == "A" and shared and dd <= 30:
                                cands.append((dd, p_))
                            elif stage == "B" and dd <= 7:
                                p_rev = any(w in p_.description.upper() + " " for w in REV_WORDS)
                                n_rev = any(w in n.description.upper() + " " for w in REV_WORDS)
                                # the entry that says "reversal" must come on or after the one it reverses
                                if (p_rev and (p_.txn_date - n.txn_date).days >= -1) or \
                                        (n_rev and not p_rev and (n.txn_date - p_.txn_date).days >= -1):
                                    cands.append((dd, p_))
                        if not cands:
                            continue
                        cands.sort(key=lambda c: (c[0], c[1].uid))
                        dd, p_ = cands[0]
                        if stage == "A":
                            commit(n, p_, 0.99, f"reversal on shared reference, {dd}d")
                        else:
                            tie = len(cands) > 1 and cands[1][0] == dd
                            conf = 0.85 if (tie and abs(n.amount) < 1_000_000) else (0.93 if tie else 0.97)
                            commit(n, p_, conf, f"reversal wording, {dd}d" + (" (several candidates)" if tie else ""))

            # Stage C/D: one reversal credit against several legs of the same session
            # (e.g. commission + VAT refunded as one 53.75 line), or against a single leg
            # that differs by a few kobo — the latter is a short/over reversal to review.
            by_ref = defaultdict(list)
            for u in openset:
                for r in strong(pool[u].refs):
                    if r.startswith("NIP:"):
                        by_ref[r].append(pool[u])
            for u in sorted(openset, key=lambda x: (pool[x].txn_date, x)):
                p_ = pool[u]
                if u not in openset or p_.amount <= 0 or not any(w in p_.description.upper() + " " for w in REV_WORDS):
                    continue
                legs = sorted({t.uid: t for r in strong(p_.refs) if r.startswith("NIP:") for t in by_ref[r]
                               if t.uid in openset and t.amount < 0}.values(), key=lambda t: t.uid)
                if not legs:
                    continue
                sols = []
                for r_ in range(2, min(4, len(legs)) + 1):
                    for combo in itertools.combinations(legs, r_):
                        if sum(t.amount for t in combo) == -p_.amount:
                            sols.append(combo)
                    if sols:
                        break
                # alternatives with the same amounts (a 50.00 commission vs a 50.00 stamp duty)
                # are interchangeable for the reconciliation; genuinely different ones are not
                if sols and len({tuple(sorted(t.amount for t in c)) for c in sols}) == 1:
                    found = (list(sols[0]), 1)
                    uids = [t.uid for t in found[0]] + [p_.uid]
                    if side == "BANK":
                        self._commit("P0_REVERSAL", 0.97, uids, [], note=f"{len(found[0])} legs reversed as one credit")
                    else:
                        self._commit("P0_REVERSAL", 0.97, [], uids, note=f"{len(found[0])} legs reversed as one credit")
                    continue
                near = [t for t in legs if abs(-t.amount - p_.amount) <= 100]
                if near:
                    n = min(near, key=lambda t: abs(-t.amount - p_.amount))
                    diff = p_.amount + n.amount
                    uids = [n.uid, p_.uid]
                    note = f"reversal {'short' if diff < 0 else 'over'} by {abs(diff) / 100:,.2f} on shared reference"
                    if side == "BANK":
                        self._commit("P0_REVERSAL", 0.80, uids, [], note=note, diff=diff, status="PROPOSED")
                    else:
                        self._commit("P0_REVERSAL", 0.80, [], uids, note=note, diff=diff, status="PROPOSED")

    def p1_reference(self):
        book_by_amt = defaultdict(list)
        for u in self.open_book:
            book_by_amt[self.book[u].amount].append(self.book[u])
        for u in sorted(self.open_bank, key=lambda x: (self.bank[x].txn_date, x)):
            b = self.bank[u]
            sb = strong(b.refs)
            if not sb:
                continue
            cands = [k for k in book_by_amt.get(b.amount, []) if k.uid in self.open_book
                     and sb & strong(k.refs) and self._window_ok(b, k)]
            if not cands:
                continue
            cands.sort(key=lambda k: abs((b.txn_date - k.txn_date).days))
            conf = 1.0 if len(cands) == 1 else 0.95
            ref = sorted(sb & strong(cands[0].refs))[0]
            self._commit("P1_REF", conf, [b.uid], [cands[0].uid], note=f"ref {ref}")

    def p2_amount_date(self):
        book_by_amt = defaultdict(list)
        for u in self.open_book:
            book_by_amt[self.book[u].amount].append(self.book[u])
        pairs = []
        cand_count_bank = defaultdict(int)
        cand_count_book = defaultdict(int)
        for u in self.open_bank:
            b = self.bank[u]
            for k in book_by_amt.get(b.amount, []):
                if k.uid in self.open_book and self._window_ok(b, k):
                    dd = abs((b.txn_date - k.txn_date).days)
                    sim = _sim(b, k)
                    wnd = self.m["cheque_window_days"] if (_is_cheque(b) or _is_cheque(k)) else max(self.window, 1)
                    score = 0.6 * (1 - dd / (wnd + 1)) + 0.4 * sim
                    pairs.append((score, dd, sim, b.uid, k.uid))
                    cand_count_bank[b.uid] += 1
                    cand_count_book[k.uid] += 1
        pairs.sort(key=lambda p: (-p[0], p[1]))
        for score, dd, sim, bu, ku in pairs:
            if bu not in self.open_bank or ku not in self.open_book:
                continue
            unique = cand_count_bank[bu] == 1 and cand_count_book[ku] == 1
            if unique:
                conf = 0.96 if dd <= 2 else 0.92
                if abs(self.bank[bu].amount) < 1_000_000 and sim < 0.30:
                    conf = 0.85      # small amounts (charges, levies) collide by chance: need narration support
            else:
                conf = 0.80 + 0.12 * sim       # ambiguous: only auto if narrations agree strongly
            self._commit("P2_AMT_DATE", conf, [bu], [ku],
                         note=f"Δ{dd}d sim {sim:.2f}{'' if unique else ' (ambiguous candidates)'}")

    def p3_aggregates(self):
        maxn = self.m["aggregate_max_items"]
        wnd = self.m["aggregate_window_days"]
        for one_side, many_side in (("BANK", "BOOK"), ("BOOK", "BANK")):
            one_pool = self.bank if one_side == "BANK" else self.book
            many_pool = self.book if one_side == "BANK" else self.bank
            one_open = self.open_bank if one_side == "BANK" else self.open_book
            many_open = self.open_book if one_side == "BANK" else self.open_bank
            for u in sorted(one_open, key=lambda x: -abs(one_pool[x].amount)):
                if u not in one_open:
                    continue
                t = one_pool[u]
                cands = [many_pool[v] for v in many_open
                         if (many_pool[v].amount > 0) == (t.amount > 0)
                         and abs(many_pool[v].amount) < abs(t.amount)
                         and abs((many_pool[v].txn_date - t.txn_date).days) <= wnd]
                if len(cands) < 2:
                    continue
                # prefer items sharing a reference with the single item, then nearest dates
                sref = strong(t.refs)
                cands.sort(key=lambda c: (not (strong(c.refs) & sref), abs((c.txn_date - t.txn_date).days)))
                cands = cands[:18]
                found = self._subset(cands, t.amount, maxn)
                if not found:
                    continue
                best, n_solutions = found
                shares_ref = any(strong(c.refs) & sref for c in best) or \
                    len(set.intersection(*[strong(c.refs) or {"_"} for c in best]) - {"_"}) > 0
                text_agree = min(_sim(c, t) for c in best) >= 0.60
                if n_solutions == 1 and (shares_ref or text_agree):
                    conf = 0.95 if shares_ref else 0.93
                else:
                    conf = 0.88 if n_solutions == 1 else 0.70
                uids = [c.uid for c in best]
                note = f"{len(uids)} {many_side.lower()} items sum to 1 {one_side.lower()} item" + \
                       ("" if n_solutions == 1 else f"; {n_solutions} alternative combinations — review")
                if one_side == "BANK":
                    self._commit("P3_AGGREGATE", conf, [u], uids, note=note)
                else:
                    self._commit("P3_AGGREGATE", conf, uids, [u], note=note)

    @staticmethod
    def _subset(cands: list[Txn], target: int, maxn: int):
        sols = []
        for r in range(2, min(maxn, len(cands)) + 1):
            for combo in itertools.combinations(cands, r):
                if sum(c.amount for c in combo) == target:
                    sols.append(combo)
                    if len(sols) > 3:
                        break
            if sols:
                break      # smallest-cardinality solutions only
        if not sols:
            return None
        return list(sols[0]), len(sols)

    def p4_fuzzy(self):
        tol = 0 if self.client_money else self.m["fuzzy_amount_tolerance_minor"]
        minsim = self.m["fuzzy_min_similarity"] / 100
        pairs = []
        for u in self.open_bank:
            b = self.bank[u]
            for v in self.open_book:
                k = self.book[v]
                if (b.amount > 0) != (k.amount > 0) or abs(b.amount - k.amount) > tol:
                    continue
                if abs((b.txn_date - k.txn_date).days) > self.window * 3:
                    continue
                s = _sim(b, k)
                if s >= minsim:
                    pairs.append((s, u, v, b.amount - k.amount))
        pairs.sort(reverse=True)
        for s, u, v, diff in pairs:
            if u in self.open_bank and v in self.open_book:
                self._commit("P4_FUZZY", min(0.85, 0.5 + 0.35 * s), [u], [v],
                             note=f"sim {s:.2f}, outside date window", diff=diff, status="PROPOSED")

    def p5_charge_sweep(self):
        """Bank-only charges booked in bulk: ONE journal per charge type covering either
        (a) all carried prior-period items of that type, or (b) one calendar month of
        that type (e.g. 1,298 Providus stamp-duty lines booked as a monthly EMTL JV).
        A current-period group only clears when the book narration names the same
        charge type; a carried group may also clear on strong narration similarity."""
        from .reconcile import classify
        if not self.rules_full:
            return
        agg_cats = {r["category"] for r in self.rules_full["classification"] if r.get("aggregate")}
        groups = defaultdict(list)
        for u in self.open_bank:
            t = self.bank[u]
            cat = classify(t, self.rules_full)[0]
            if t.origin_period and t.origin_period != self.current_period:
                groups[(cat, "carried")].append(t)
            elif cat in agg_cats:
                groups[(cat, t.txn_date.strftime("%Y-%m"))].append(t)
        if not groups:
            return
        for v in sorted(self.open_book, key=lambda x: (self.book[x].txn_date, x)):
            k = self.book[v]
            if k.origin_period and k.origin_period != self.current_period:
                continue
            kcat = classify(k, self.rules_full)[0]
            for (cat, scope), items in sorted(groups.items(), key=lambda g: (g[0][0] != kcat, g[0][1] != "carried", g[0][1])):
                live = [t for t in items if t.uid in self.open_bank]
                if not live:
                    continue
                same_cat = kcat == cat
                if scope != "carried" and not same_cat:
                    continue
                if sum(t.amount for t in live) == k.amount:
                    pick = live
                elif scope == "carried":
                    pick = [t for t in live if t.amount == k.amount][:1]
                else:
                    pick = []
                if not pick:
                    continue
                s_ = max(_sim(t, k) for t in pick)
                if not same_cat and s_ < 0.60:
                    continue
                conf = 0.95 if same_cat else (0.90 if s_ >= 0.55 else 0.80)
                rule = "P5_PRIOR_PERIOD" if scope == "carried" else "P5_CHARGE_SWEEP"
                self._commit(rule, conf, [t.uid for t in pick], [v],
                             note=f"{len(pick)} {cat} line(s) [{scope}] cleared by one book entry"
                                  f"{' (category agrees)' if same_cat else ''} sim {s_:.2f}")
                break

    def run(self, decisions=None) -> list[Match]:
        self.apply_decisions(decisions or [])
        self.p0_reversals()
        self.p1_reference()
        self.p5_charge_sweep()          # before P2: category-aware, stops tiny charges pairing by amount alone
        self.p2_amount_date()
        self.p3_aggregates()
        self.p4_fuzzy()
        return self.matches

    # items still open for the reconciliation statement = unmatched + in PROPOSED matches
    def open_items(self):
        proposed_bank = {u for m in self.matches if m.status == "PROPOSED" for u in m.bank_uids}
        proposed_book = {u for m in self.matches if m.status == "PROPOSED" for u in m.book_uids}
        return ([self.bank[u] for u in self.open_bank | proposed_bank],
                [self.book[u] for u in self.open_book | proposed_book])
