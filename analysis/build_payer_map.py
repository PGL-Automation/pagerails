"""
L03 — Build payer map from Providus statement history + customer register.
Outputs: analysis/payer_map.xlsx  (top 50 by total inflow + full list)
         analysis/replay_summary.txt  (M09 first-run findings)

Run from: /Users/nonsookoroafor/autopilot/
  python3 analysis/build_payer_map.py
"""
import re, sys
from collections import defaultdict
from pathlib import Path
from datetime import date, datetime

import xlrd
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent

# ── 1. Load Providus bank statement (bank-side, all inward transfers) ─────────
print("Loading Providus bank statement …")
wb_stmt = xlrd.open_workbook(str(ROOT / "STATEMENT - 2026-09-30T135049.445.xls"))
sh = wb_stmt.sheets()[0]

# Header at row 16 (0-indexed)
HEADER_ROW = 16
headers = [str(sh.cell_value(HEADER_ROW, c)).strip() for c in range(sh.ncols)]
col = {h: i for i, h in enumerate(headers)}

# Control totals from the statement
STMT_OPENING  =  1_874_611_147.58
STMT_CLOSING  = 10_002_487_312.74
STMT_DR_COUNT = 3_501
STMT_CR_COUNT =   985
STMT_DR_TOTAL = 144_099_792_144.61
STMT_CR_TOTAL = 152_227_668_309.77

inward_txns   = []   # credits = money IN = subscriptions/receipts
all_bank_txns = []

def parse_amount(v) -> float:
    if not v:
        return 0.0
    s = str(v).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0

def parse_date(v) -> date | None:
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None

for r in range(HEADER_ROW + 1, sh.nrows):
    txn_date_raw = sh.cell_value(r, col.get("Transaction Date", 0))
    desc         = str(sh.cell_value(r, col.get("Transaction Details", 2))).strip()
    debit        = parse_amount(sh.cell_value(r, col.get("Debit Amount",  4)))
    credit       = parse_amount(sh.cell_value(r, col.get("Credit Amount", 5)))
    balance_raw  = sh.cell_value(r, col.get("Current Balance", 6))
    doc_num      = str(sh.cell_value(r, col.get("DOC-NUM", 8))).strip()

    if not txn_date_raw or (not debit and not credit and not desc):
        continue
    txn_date = parse_date(txn_date_raw)
    if txn_date is None:
        continue
    balance = parse_amount(balance_raw)
    net = credit - debit  # positive = money in

    txn = dict(date=txn_date, desc=desc, debit=debit, credit=credit,
               net=net, balance=balance, doc_num=doc_num)
    all_bank_txns.append(txn)
    if credit > 0:
        inward_txns.append(txn)

print(f"  Bank rows parsed: {len(all_bank_txns):,}  |  Inward (credit) txns: {len(inward_txns):,}")

# ── 2. Load customer bank details (payer register) ────────────────────────────
print("Loading customer bank details …")
wb_cust = openpyxl.load_workbook(str(ROOT / "Bank_GL_Customers List.xlsx"), data_only=True)
ws_cust = wb_cust["Customers bank details"]
cust_headers = [c.value for c in ws_cust[1]]
col_c = {h: i for i, h in enumerate(cust_headers) if h}

customers = {}  # account_number -> {name, account_name, bank, account_number}
for row in ws_cust.iter_rows(min_row=2, values_only=True):
    name    = str(row[col_c.get("NAMES", 0)] or "").strip()
    acct_nm = str(row[col_c.get("ACCOUNT NAME", 1)] or "").strip()
    bank    = str(row[col_c.get("BANK NAME", 2)] or "").strip()
    acct_no = str(row[col_c.get("ACCOUNT NUMBER", 3)] or "").strip().replace(".0","")
    if name or acct_no:
        customers[acct_no] = dict(name=name, account_name=acct_nm, bank=bank, account_number=acct_no)

print(f"  Customer records: {len(customers):,}")

# ── 3. Build NIP session ID → payer account number map from narrations ────────
#  Providus narration pattern:
#  "INWARD TRANSFER (N) <SESSION_ID>  FROM <BANK>/<PAYER_NAME>"
#  "NAPS CREDIT <SESSION_ID> FROM <BANK>/<PAYER_NAME>"
#  "PAYSTACK SETTLEMENT <batch>"

INWARD_RE = re.compile(
    r"(?:INWARD TRANSFER|NAPS CREDIT|INTERBANK RECEIPT|TRANSFER IN)[^\d]*"
    r"(\d{6,})",  # session/reference
    re.IGNORECASE,
)
NAME_RE = re.compile(r"FROM\s+[^/]+/(.+)", re.IGNORECASE)

def extract_payer_name(desc: str) -> str:
    m = NAME_RE.search(desc)
    if m:
        return m.group(1).strip()[:80]
    return desc[:60]

def extract_ref(desc: str, doc_num: str) -> str:
    if doc_num and doc_num not in ("0", ""):
        return doc_num
    m = INWARD_RE.search(desc)
    if m:
        return m.group(1)
    return ""

# ── 4. Aggregate inward transfers by payer name (normalised) ──────────────────
payer_totals: dict[str, dict] = defaultdict(lambda: dict(
    name="", bank="", account_number="", total=0.0, count=0, months=set(), first=None, last=None, sample_desc=""
))

for txn in inward_txns:
    desc    = txn["desc"]
    ref     = extract_ref(desc, txn["doc_num"])
    raw_name = extract_payer_name(desc)

    # Normalise key: uppercase, strip common suffixes
    key = re.sub(r"\s+", " ", raw_name.upper()).strip()
    key = re.sub(r"\bLIMITED\b|\bLTD\.?\b|\bPLC\b", "", key).strip()

    p = payer_totals[key]
    p["name"]   = raw_name if not p["name"] else p["name"]
    p["total"] += txn["credit"]
    p["count"] += 1
    p["months"].add(txn["date"].strftime("%Y-%m"))
    if p["first"] is None or txn["date"] < p["first"]:
        p["first"] = txn["date"]
    if p["last"] is None or txn["date"] > p["last"]:
        p["last"] = txn["date"]
    p["sample_desc"] = desc[:100]

    # Try to match to customer register via name fuzzy
    # Simple: check if any customer name contains the key (or vice versa)
    if not p.get("account_number"):
        for cust_acct, cust in customers.items():
            cn = re.sub(r"\bLIMITED\b|\bLTD\.?\b|\bPLC\b", "", cust["name"].upper()).strip()
            if key and cn and (key[:20] in cn or cn[:20] in key):
                p["bank"]           = cust["bank"]
                p["account_number"] = cust["account_number"]
                break

# Sort by total inflow descending
ranked = sorted(payer_totals.items(), key=lambda x: -x[1]["total"])

# ── 5. Load running deposit/investment schedules ───────────────────────────────
print("Loading deposit and investment schedules …")
wb_dep = openpyxl.load_workbook(str(ROOT / "Deposit-Schedule_Running.xlsx"), data_only=True)
ws_dep = wb_dep["Running"]
dep_headers = [c.value for c in ws_dep[1]]
dep_col = {h: i for i, h in enumerate(dep_headers) if h}

running_deposits = []
for row in ws_dep.iter_rows(min_row=2, values_only=True):
    if row[0] is None:
        continue
    customer   = str(row[dep_col.get("Customer", 1)] or "").strip()
    principal  = float(row[dep_col.get("Principal", 2)] or 0)
    rate       = float(row[dep_col.get("Rate", 4)] or 0)
    tenor      = int(row[dep_col.get("Tenor", 5)] or 0)
    carrying   = float(row[dep_col.get("Carrying Value", 6)] or 0)
    accrued    = float(row[dep_col.get("Accrued Interest", 7)] or 0)
    maturity   = row[dep_col.get("Maturity Date", 9)]
    running_deposits.append(dict(customer=customer, principal=principal, rate=rate,
                                  tenor=tenor, carrying=carrying, accrued=accrued, maturity=maturity))

wb_inv = openpyxl.load_workbook(str(ROOT / "Investment_CP & FD.xlsx"), data_only=True)
ws_inv = wb_inv["Running "]
inv_headers = [c.value for c in ws_inv[2]]  # row 2 is the real header (row 1 is cut-off date)
inv_col = {h: i for i, h in enumerate(inv_headers) if h}

running_investments = []
for row in ws_inv.iter_rows(min_row=3, values_only=True):
    if row[0] is None:
        continue
    inv_type   = str(row[inv_col.get("Investment Type", 1)] or "").strip()
    counterpty = str(row[inv_col.get("Counterparty", 2)] or "").strip()
    principal  = float(row[inv_col.get("Principal", 3)] or 0)
    carrying   = float(row[inv_col.get("Carrying Value", 4)] or 0)
    accrued    = float(row[inv_col.get("Accrued Interest", 5)] or 0)
    rate       = float(row[inv_col.get("Rate", 7)] or 0)
    maturity   = row[inv_col.get("Maturity Date", 11)]
    running_investments.append(dict(type=inv_type, counterparty=counterpty, principal=principal,
                                     carrying=carrying, accrued=accrued, rate=rate, maturity=maturity))

print(f"  Running deposits:    {len(running_deposits):,}")
print(f"  Running investments: {len(running_investments):,}")

# ── 6. Write output workbook ───────────────────────────────────────────────────
Path(ROOT / "analysis").mkdir(exist_ok=True)
out_path = ROOT / "analysis" / "payer_map_L03.xlsx"
print(f"Writing {out_path} …")

wb_out = Workbook()

# ── Styles ──
HDR_FILL   = PatternFill("solid", fgColor="111111")
HDR_FONT   = Font(bold=True, color="FFFFFF", size=10)
SUB_FILL   = PatternFill("solid", fgColor="F5F5F5")
AMOUNT_FMT = '#,##0.00'
PCT_FMT    = '0.00%'
DATE_FMT   = 'DD-MMM-YYYY'

def style_header(ws, row=1):
    for cell in ws[row]:
        cell.font    = HDR_FONT
        cell.fill    = HDR_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

def col_width(ws, widths: list[float]):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

# ── Sheet 1: Top 50 Payers ───────────────────────────────────────────────────
ws1 = wb_out.active
ws1.title = "Top 50 Payers"
ws1.row_dimensions[1].height = 28
ws1.append([
    "Rank", "Payer Name", "Bank", "Account Number",
    "Total Inflow (NGN)", "Transactions", "Active Months",
    "First Txn", "Last Txn", "In Register?", "Sample Narration",
])
style_header(ws1)
col_width(ws1, [5, 35, 20, 16, 18, 12, 14, 12, 12, 12, 50])

total_inflow = sum(p["total"] for _, p in ranked)

for rank, (key, p) in enumerate(ranked[:50], 1):
    in_register = "✓" if p.get("account_number") else "✗"
    ws1.append([
        rank, p["name"], p.get("bank", ""), p.get("account_number", ""),
        p["total"], p["count"], len(p["months"]),
        p["first"], p["last"], in_register, p["sample_desc"],
    ])
    row = ws1.max_row
    if rank % 2 == 0:
        for c in ws1[row]:
            c.fill = SUB_FILL
    ws1.cell(row, 5).number_format = AMOUNT_FMT
    ws1.cell(row, 8).number_format = DATE_FMT
    ws1.cell(row, 9).number_format = DATE_FMT
    ws1.cell(row, 10).alignment = Alignment(horizontal="center")

ws1.freeze_panes = "A2"

# ── Sheet 2: Full Payer Map ───────────────────────────────────────────────────
ws2 = wb_out.create_sheet("Full Payer Map")
ws2.append(["Rank", "Normalised Key", "Display Name", "Bank", "Account Number",
            "Total Inflow", "Count", "Months"])
style_header(ws2)
col_width(ws2, [5, 40, 40, 20, 16, 18, 8, 8])
for rank, (key, p) in enumerate(ranked, 1):
    ws2.append([rank, key, p["name"], p.get("bank",""), p.get("account_number",""),
                p["total"], p["count"], len(p["months"])])
    ws2.cell(ws2.max_row, 6).number_format = AMOUNT_FMT

ws2.freeze_panes = "A2"

# ── Sheet 3: Running Deposits ─────────────────────────────────────────────────
ws3 = wb_out.create_sheet("Running Deposits")
ws3.append(["Customer", "Principal", "Carrying Value", "Accrued Interest",
            "Rate", "Tenor (days)", "Maturity Date"])
style_header(ws3)
col_width(ws3, [40, 20, 20, 20, 10, 12, 14])
total_principal = total_carrying = total_accrued = 0
for d in sorted(running_deposits, key=lambda x: -x["principal"]):
    mat = d["maturity"]
    if hasattr(mat, "strftime"):
        mat_str = mat
    else:
        mat_str = str(mat) if mat else ""
    ws3.append([d["customer"], d["principal"], d["carrying"], d["accrued"],
                d["rate"], d["tenor"], mat_str])
    r = ws3.max_row
    for ci in [2,3,4]: ws3.cell(r, ci).number_format = AMOUNT_FMT
    ws3.cell(r, 5).number_format = PCT_FMT
    if r % 2 == 0:
        for c in ws3[r]: c.fill = SUB_FILL
    total_principal += d["principal"]
    total_carrying  += d["carrying"]
    total_accrued   += d["accrued"]

ws3.append(["TOTAL", total_principal, total_carrying, total_accrued, "", "", ""])
r = ws3.max_row
for ci in [2,3,4]:
    ws3.cell(r, ci).number_format = AMOUNT_FMT
    ws3.cell(r, ci).font = Font(bold=True)
ws3.cell(r, 1).font = Font(bold=True)
ws3.freeze_panes = "A2"

# ── Sheet 4: Running Investments ──────────────────────────────────────────────
ws4 = wb_out.create_sheet("Running Investments")
ws4.append(["Type", "Counterparty", "Principal", "Carrying Value", "Accrued Interest",
            "Rate", "Maturity Date"])
style_header(ws4)
col_width(ws4, [20, 35, 20, 20, 20, 10, 14])
inv_principal = inv_carrying = inv_accrued = 0
for inv in sorted(running_investments, key=lambda x: -x["principal"]):
    mat = inv["maturity"]
    ws4.append([inv["type"], inv["counterparty"], inv["principal"], inv["carrying"],
                inv["accrued"], inv["rate"], mat])
    r = ws4.max_row
    for ci in [3,4,5]: ws4.cell(r, ci).number_format = AMOUNT_FMT
    ws4.cell(r, 6).number_format = PCT_FMT
    if r % 2 == 0:
        for c in ws4[r]: c.fill = SUB_FILL
    inv_principal += inv["principal"]
    inv_carrying  += inv["carrying"]
    inv_accrued   += inv["accrued"]

ws4.append(["", "TOTAL", inv_principal, inv_carrying, inv_accrued, "", ""])
r = ws4.max_row
for ci in [3,4,5]:
    ws4.cell(r, ci).number_format = AMOUNT_FMT
    ws4.cell(r, ci).font = Font(bold=True)
ws4.cell(r, 2).font = Font(bold=True)
ws4.freeze_panes = "A2"

# ── Sheet 5: Summary ──────────────────────────────────────────────────────────
ws5 = wb_out.create_sheet("Summary", 0)
ws5.column_dimensions["A"].width = 38
ws5.column_dimensions["B"].width = 28

def ws5_title(label):
    ws5.append([label, ""])
    ws5.cell(ws5.max_row, 1).font = Font(bold=True, size=11)

def ws5_row(label, value, fmt=None):
    ws5.append([label, value])
    if fmt:
        ws5.cell(ws5.max_row, 2).number_format = fmt

ws5_title("PROVIDUS CLIENT ACCOUNT — ANALYSIS SUMMARY")
ws5.append(["As at", "30 September 2026"])
ws5.append(["Prepared by", "Claude (M09 + L03)"])
ws5.append([""])
ws5_title("Bank Statement (Providus ****2286)")
ws5_row("Opening Balance",          STMT_OPENING,  AMOUNT_FMT)
ws5_row("Closing Balance",          STMT_CLOSING,  AMOUNT_FMT)
ws5_row("Net movement",             STMT_CLOSING - STMT_OPENING, AMOUNT_FMT)
ws5_row("Total Credit transactions",STMT_CR_TOTAL, AMOUNT_FMT)
ws5_row("Total Debit transactions", STMT_DR_TOTAL, AMOUNT_FMT)
ws5_row("Credit count",             STMT_CR_COUNT)
ws5_row("Debit count",              STMT_DR_COUNT)
ws5.append([""])
ws5_title("Payer Analysis (L03)")
ws5_row("Total inward transfers",   len(inward_txns))
ws5_row("Total inflow (NGN)",       sum(t["credit"] for t in inward_txns), AMOUNT_FMT)
ws5_row("Unique payers identified", len(payer_totals))
ws5_row("Payers matched to register", sum(1 for _,p in ranked if p.get("account_number")))
top10 = sum(p["total"] for _, p in ranked[:10])
ws5_row("Top 10 payers — total inflow", top10, AMOUNT_FMT)
ws5_row("Top 10 as % of total inflow",  top10 / total_inflow if total_inflow else 0, PCT_FMT)
ws5.append([""])
ws5_title("Running Books (as at 30 Sep 2026)")
ws5_row("Deposit book: customers",  len(running_deposits))
ws5_row("Deposit book: total principal", total_principal, AMOUNT_FMT)
ws5_row("Deposit book: total carrying value", total_carrying, AMOUNT_FMT)
ws5_row("Deposit book: total accrued interest", total_accrued, AMOUNT_FMT)
ws5.append([""])
ws5_row("Investment book: positions", len(running_investments))
ws5_row("Investment book: total principal", inv_principal, AMOUNT_FMT)
ws5_row("Investment book: total carrying", inv_carrying, AMOUNT_FMT)
ws5_row("Investment book: total accrued", inv_accrued, AMOUNT_FMT)
ws5.append([""])
ws5_title("First Replay Run — M09 (1 Oct 2026)")
ws5_row("Period",                   "May – Sep 2026")
ws5_row("Bank lines processed",     len(all_bank_txns))
ws5_row("Symplus GL lines",         1363)
ws5_row("Auto-match rate",          0.19, PCT_FMT)
ws5_row("Open items (bank + book)", 1225)
ws5_row("Reconciling difference",   350_892_212.40, AMOUNT_FMT)
ws5.append([""])
ws5_title("Key findings")
findings = [
    ("Sign convention", "Symplus GL shows credit-balance convention; mapping confirmed Credit=IN, Debit=OUT"),
    ("Coverage gap",    "Symplus has 1,363 rows vs 4,487 bank lines — bank charges, EMTL, SMS not yet in Symplus"),
    ("Next step",       "M04: export Symplus Jan–Apr 2026 to extend replay; M06: confirm GL code list"),
    ("Payer map",       f"{len(payer_totals)} unique payers; top 50 on 'Top 50 Payers' sheet — finance to confirm"),
]
for label, val in findings:
    ws5.append([label, val])
    ws5.cell(ws5.max_row, 2).alignment = Alignment(wrap_text=True)

ws5.row_dimensions[1].height = 30
for r in range(1, ws5.max_row + 1):
    ws5.row_dimensions[r].height = 16

wb_out.save(str(out_path))
print(f"\n✓  Written: {out_path}")
print(f"\n{'='*60}")
print("REPLAY SUMMARY — M09 (Page Capital Group, 1 Oct 2026)")
print(f"{'='*60}")
print(f"Account:           PAM-PRV-CLIENTS (Providus ****2286)")
print(f"Period:            May 2026 – Sep 2026")
print(f"Bank lines:        {len(all_bank_txns):,}")
print(f"Inward txns:       {len(inward_txns):,}  (credits = subscriptions/receipts in)")
print(f"Symplus GL lines:  1,363")
print(f"")
print(f"Bank statement:    Opening ₦{STMT_OPENING:,.2f} → Closing ₦{STMT_CLOSING:,.2f}")
print(f"                   Credits ₦{STMT_CR_TOTAL:,.2f} ({STMT_CR_COUNT:,} txns)")
print(f"                   Debits  ₦{STMT_DR_TOTAL:,.2f} ({STMT_DR_COUNT:,} txns)")
print(f"")
print(f"First replay:      auto-match rate 19%,  open items 1,225,  diff ₦350,892,212.40")
print(f"")
print(f"Payer map:         {len(payer_totals):,} unique payers identified from narrations")
print(f"  Top 5:")
for rank, (key, p) in enumerate(ranked[:5], 1):
    print(f"  {rank}. {p['name'][:40]:<40}  ₦{p['total']:>20,.2f}  ({p['count']} txns)")
print(f"")
print(f"Running deposits:  {len(running_deposits):,} positions  ·  Principal ₦{total_principal:,.2f}")
print(f"Running investments: {len(running_investments):,} positions  ·  Principal ₦{inv_principal:,.2f}")
print(f"")
print(f"Key actions needed:")
print(f"  M04: Symplus export Jan–Apr 2026 to complete the full 9-month replay (L01)")
print(f"  M06: Confirm GL code list (chart of accounts) — Symplus admin")
print(f"  M03: Providus statement API or daily e-statement for live feed")
print(f"  L02: Finance review of the 1,225 open items — real breaks vs mapping gaps")
