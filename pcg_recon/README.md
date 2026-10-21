# PageRails — Financial Operations Platform (v0.1)

Reconciles every bank and custodian cash account of **Page Asset Management Limited** and
**Page Capital Limited** against the books, produces an auditable Excel reconciliation pack,
and enforces maker-checker sign-off with a tamper-evident audit log.

## What it handles

| Side | Formats |
|---|---|
| Bank | Internet-banking CSV/XLS/XLSX (split Dr/Cr or signed + DR/CR flag, letterhead rows auto-skipped), PDF statements (text layer; sign derived from running balance), SWIFT MT940, custodian cash statements |
| Book | Sage cashbook, QuickBooks register, Odoo journal items, finance Excel cashbooks, and the group PostgreSQL ledger (direct SQL, read-only DSN) |

## Install & run

```bash
pip install -e .            # add [postgres] for the ledger adapter
python samples/generate.py samples/inputs          # synthetic Sep/Oct 2026 data, all 5 formats
pagerails run --inputs samples/inputs --period 2026-09 --maker "A. Preparer"
pagerails run --inputs samples/inputs --period 2026-10 --maker "A. Preparer"   # carries Sep open items forward
pagerails status
pagerails signoff --run <RUN_ID> --checker "B. Reviewer"
pagerails verify-audit
pytest -q
```

`--period` accepts a month (`2026-09`), a day (`2026-09-29`, for daily client-money recs) or a range (`2026-09-01:2026-09-15`).

## Monthly / daily workflow

1. **Drop files** into `inputs/<ACCOUNT-ID>/` (or leave the ledger feed on Postgres).
2. **Maker runs** `pagerails run`. Each account is independent — one bad file does not stop the others.
3. **Review** the pack: `Summary` → each `REC <account>` sheet → `Alerts` → `Review Queue`.
4. **Reviewer decides** proposed matches in the `Review Queue` sheet (APPROVE/REJECT + name), then
   `pagerails decide --file <pack.xlsx>` and re-run. One-off manual pairings: `pagerails manual`.
5. **Finance posts** the `Draft Journals` (charges, EMTL, VAT, WHT, interest) through the normal approval flow.
6. **Checker signs off** with `pagerails signoff`. The preparer cannot sign their own run; a run with a
   non-zero difference needs an explanatory note.

## Matching passes (confidence ≥ 0.90 auto-accepted; below goes to Review Queue)

| Pass | Rule |
|---|---|
| D | Prior reviewer decisions (APPROVE / MANUAL / REJECT) |
| P0 | Self-cancelling reversals on one side (failed NIP + reversal, reversed JV) |
| P1 | Shared strong reference — NIP session ID, cheque number, ref code — and equal amount |
| P5 | Prior-period bank-only items cleared by a later catch-up journal (per charge type) |
| P2 | Equal amount inside the date window, ranked by date proximity + narration similarity |
| P3 | Aggregates: 1 bank ↔ N book (bulk payments) and 1 book ↔ N bank (tranched receipts) |
| P4 | Fuzzy narration match outside the window — always PROPOSED, never auto |

Proposed matches do **not** reduce the open items on the statement until a reviewer approves them.
Tolerance matches are never auto-accepted on client-money accounts.

## Controls built in

* Statement continuity: every running balance is re-computed; a missing, duplicated or mis-parsed line raises a HIGH alert.
* Opening balances checked against the prior run's closing balances (catches back-dated postings into closed periods).
* Client-money / fund accounts: 2-day escalation, zero tolerance, unidentified credits routed to AML review.
* Stale cheques (> 180 days), aged items (> 30 days), large items (≥ NGN 50m) escalated.
* Hash of `rules.yaml` and of every input file stamped on each run; SHA-256 chained audit log (`verify-audit`).

## Onboarding a real bank account

1. Add the account to `config/accounts.yaml` (real GL code, masked number, purpose, feed paths).
2. Take one real statement download; if its headers aren't in an existing profile, add a profile to
   `config/profiles.yaml` — header synonyms only, no code.
3. Run for a closed month you have already reconciled manually and confirm the engine lands on the same
   open items. Save that file as a regression fixture in `tests/`.
4. Set `opening_book_balance` for the first run only.

## Known limits of v0.1

* Bank column layouts in `profiles.yaml` are generic; each bank's real export must be confirmed before go-live.
* Scanned (image-only) PDFs need OCR first (`ocrmypdf in.pdf out.pdf`).
* Single-currency per account; FX accounts reconcile in account currency only.
* No UI yet — Excel pack + CLI. The spec covers the web front end and scheduler.
* Run store is SQLite; the schema moves to the group PostgreSQL unchanged.
