"""Excel reconciliation pack.

The statement on each REC sheet is built from live SUMIFS formulas over the
'Open Items' sheet, so reviewers and auditors can trace every adjusting figure to
the underlying lines, and edits to the open-items list flow through.
"""
from __future__ import annotations

from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule

F = "Arial"
NUM = '#,##0.00;(#,##0.00);"-"'
HDR_FILL = PatternFill("solid", fgColor="1F2A44")
HDR_FONT = Font(name=F, bold=True, color="FFFFFF", size=10)
BODY = Font(name=F, size=10)
BOLD = Font(name=F, size=10, bold=True)
TITLE = Font(name=F, size=14, bold=True, color="1F2A44")
INPUT_FILL = PatternFill("solid", fgColor="FFF4CC")
thin = Side(style="thin", color="BFBFBF")
TOP = Border(top=Side(style="thin", color="000000"))
DBL = Border(top=Side(style="thin", color="000000"), bottom=Side(style="double", color="000000"))
RED = PatternFill("solid", fgColor="F8D7DA")
GREEN = PatternFill("solid", fgColor="D4EDDA")
AMBER = PatternFill("solid", fgColor="FFF3CD")


def _table(ws, headers, rows, widths=None, start_row=1, num_cols=()):
    for j, h in enumerate(headers, 1):
        c = ws.cell(start_row, j, h)
        c.fill, c.font = HDR_FILL, HDR_FONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for i, row in enumerate(rows, start_row + 1):
        for j, v in enumerate(row, 1):
            c = ws.cell(i, j, v)
            c.font = BODY
            if headers[j - 1] in num_cols:
                c.number_format = NUM
    ws.freeze_panes = ws.cell(start_row + 1, 1)
    if rows:
        ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(headers))}{start_row + len(rows)}"
    for j, w in enumerate(widths or [], 1):
        ws.column_dimensions[get_column_letter(j)].width = w


def write_pack(results: list, path: str, period_label: str, maker: str, entities: dict):
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"

    # ------------------------------------------------------------ Open Items (built first; REC sheets reference it)
    wo = wb.create_sheet("Open Items")
    oh = ["Account", "Side", "Category", "Date", "Age (days)", "Age bucket", "Amount", "Description",
          "Reference", "In proposed match", "Carried from", "UID", "Source", "Row"]
    orows = []
    for r in results:
        prop = {u for m in r.matches if m.status == "PROPOSED" for u in m.bank_uids + m.book_uids}
        for t in sorted(r.open_bank + r.open_book, key=lambda x: (x.side, x.txn_date)):
            orows.append([r.account["id"], t.side, t.category, t.txn_date, t.__dict__.get("age_days"),
                          t.__dict__.get("age_bucket"), t.amount / 100, t.description[:120], t.reference,
                          "YES" if t.uid in prop else "", t.origin_period if t.origin_period != r.period_end.isoformat() else "",
                          t.uid, t.source, t.source_row])
    _table(wo, oh, orows, [14, 7, 24, 11, 9, 10, 16, 55, 20, 10, 12, 20, 22, 6], num_cols=("Amount",))
    for i in range(2, len(orows) + 2):
        wo.cell(i, 4).number_format = "dd-mmm-yyyy"
    n_open = max(len(orows) + 1, 2)
    OA = f"'Open Items'!$A$2:$A${n_open}"
    OC = f"'Open Items'!$C$2:$C${n_open}"
    OB = f"'Open Items'!$B$2:$B${n_open}"
    OG = f"'Open Items'!$G$2:$G${n_open}"

    # ------------------------------------------------------------ per-account REC sheets
    rec_refs = {}
    for r in results:
        a = r.account
        wr = wb.create_sheet(f"REC {a['id']}"[:31])
        wr.column_dimensions["A"].width = 52
        wr.column_dimensions["B"].width = 20
        wr.column_dimensions["C"].width = 20
        wr["A1"] = "BANK RECONCILIATION STATEMENT"
        wr["A1"].font = TITLE
        info = [("Entity", entities[a["entity"]]["name"]), ("Account", f"{a['id']}  ({a['bank']} {a['account_masked']})"),
                ("GL account", a["gl_account"]), ("Purpose", a["purpose"] + ("  — CLIENT MONEY" if a.get("client_money") else "")),
                ("Period end", r.period_end.strftime("%d %B %Y")), ("Run ID", r.__dict__.get("run_id", ""))]
        for i, (k, v) in enumerate(info, 3):
            wr.cell(i, 1, k).font = BOLD
            wr.cell(i, 2, v).font = BODY
        q = f'"{a["id"]}"'

        def sumifs(cat=None, side=None, sign=None):
            parts = [OG, OA, q]
            if cat:
                parts += [OC, f'"{cat}"']
            if side:
                parts += [OB, f'"{side}"']
            if sign:
                parts += [OG, f'"{sign}0"']
            return "=SUMIFS(" + ",".join(parts) + ")"

        row = 10
        lines = [
            ("Balance per bank statement", r.bank_close / 100, "bank"),
            ("Add: deposits in transit (in book, not yet on statement)", sumifs("DEPOSIT_IN_TRANSIT"), None),
            ("Less: unpresented cheques", sumifs("UNPRESENTED_CHEQUE"), None),
            ("Less: outstanding payments (in book, not yet on statement)", sumifs("OUTSTANDING_PAYMENT"), None),
        ]
        wr.cell(row - 1, 1, "BANK SIDE").font = BOLD
        start = row
        for label, val, _ in lines:
            wr.cell(row, 1, label).font = BODY
            c = wr.cell(row, 2, val)
            c.number_format, c.font = NUM, BODY
            row += 1
        wr.cell(row, 1, "Adjusted bank balance").font = BOLD
        c = wr.cell(row, 2, f"=SUM(B{start}:B{row - 1})")
        c.number_format, c.font, c.border = NUM, BOLD, TOP
        adj_bank_cell = f"B{row}"
        row += 2
        wr.cell(row, 1, "BOOK SIDE").font = BOLD
        row += 1
        bstart = row
        blines = [
            ("Balance per cashbook / GL", r.book_close / 100),
            ("Add: bank credits not yet in book (direct credits, interest)", sumifs(side="BANK", sign=">")),
            ("Less: bank debits not yet in book (charges, EMTL, VAT, WHT)", sumifs(side="BANK", sign="<")),
        ]
        for label, val in blines:
            wr.cell(row, 1, label).font = BODY
            c = wr.cell(row, 2, val)
            c.number_format, c.font = NUM, BODY
            row += 1
        wr.cell(row, 1, "Adjusted book balance").font = BOLD
        c = wr.cell(row, 2, f"=SUM(B{bstart}:B{row - 1})")
        c.number_format, c.font, c.border = NUM, BOLD, TOP
        adj_book_cell = f"B{row}"
        row += 2
        wr.cell(row, 1, "UNRECONCILED DIFFERENCE (must be nil)").font = BOLD
        c = wr.cell(row, 2, f"={adj_bank_cell}-{adj_book_cell}")
        c.number_format, c.font, c.border = NUM, BOLD, DBL
        wr.conditional_formatting.add(f"B{row}", CellIsRule(operator="notEqual", formula=["0"], fill=RED))
        wr.conditional_formatting.add(f"B{row}", CellIsRule(operator="equal", formula=["0"], fill=GREEN))
        rec_refs[a["id"]] = (wr.title, adj_bank_cell, adj_book_cell, f"B{row}")
        row += 2
        # breakdown of bank-only items by category
        wr.cell(row, 1, "Bank-only items by category (draft journals on 'Draft Journals')").font = BOLD
        row += 1
        cats = sorted({t.category for t in r.open_bank})
        for cat in cats:
            wr.cell(row, 1, "   " + cat).font = BODY
            c = wr.cell(row, 2, sumifs(cat, side="BANK"))
            c.number_format, c.font = NUM, BODY
            row += 1
        row += 1
        s = r.stats
        wr.cell(row, 1, "Matching statistics").font = BOLD
        row += 1
        for k, v in [("Bank lines (incl. carried)", s["bank_lines"]), ("Book lines (incl. carried)", s["book_lines"]),
                     ("Auto/approved match rate (bank lines)", s["auto_match_rate"]),
                     ("Proposed matches awaiting review", s["proposed_matches"]),
                     ("Open bank items", s["open_bank"]), ("Open book items", s["open_book"])]:
            wr.cell(row, 1, "   " + k).font = BODY
            c = wr.cell(row, 2, v)
            c.font = BODY
            if "rate" in k:
                c.number_format = "0.0%"
            row += 1
        row += 1
        wr.cell(row, 1, "SIGN-OFF (maker-checker)").font = BOLD
        row += 1
        for k, v in [("Prepared by (maker)", maker), ("Prepared on", datetime.now().strftime("%d-%b-%Y %H:%M")),
                     ("Reviewed by (checker)", ""), ("Reviewed on", ""), ("Reviewer comments", "")]:
            wr.cell(row, 1, "   " + k).font = BODY
            c = wr.cell(row, 2, v)
            c.font = BODY
            if not v:
                c.fill = INPUT_FILL
            row += 1
        wr.cell(row + 1, 1, "Yellow cells are for the reviewer. Formal sign-off is recorded with "
                             "`pagerails signoff` so it enters the audit log.").font = Font(name=F, size=8, italic=True)

    # ------------------------------------------------------------ Summary
    ws["A1"] = f"PageRails — Bank Reconciliation Summary — {period_label}"
    ws["A1"].font = TITLE
    ws["A2"] = f"Prepared by {maker} on {datetime.now().strftime('%d %b %Y %H:%M')}. " \
               "Adjusted balances and differences link to each account's REC sheet."
    ws["A2"].font = Font(name=F, size=9, italic=True)
    sh = ["Entity", "Account", "Bank", "Purpose", "Client money", "Bank balance", "Book balance",
          "Adjusted bank", "Adjusted book", "Difference", "Status", "Auto-match %", "Proposed", "Open items",
          "HIGH alerts", "Run ID"]
    srows = []
    for r in results:
        a = r.account
        t, ab, ak, df = rec_refs[a["id"]]
        srows.append([a["entity"], a["id"], a["bank"], a["purpose"], "YES" if a.get("client_money") else "",
                      r.bank_close / 100, r.book_close / 100, f"='{t}'!{ab}", f"='{t}'!{ak}", f"='{t}'!{df}",
                      r.status, r.stats["auto_match_rate"], r.stats["proposed_matches"],
                      len(r.open_bank) + len(r.open_book),
                      sum(1 for x in r.alerts if x["severity"] == "HIGH"), r.__dict__.get("run_id", "")])
    _table(ws, sh, srows, [7, 15, 12, 13, 8, 17, 17, 17, 17, 14, 26, 10, 9, 9, 8, 30], start_row=4,
           num_cols=("Bank balance", "Book balance", "Adjusted bank", "Adjusted book", "Difference"))
    last = 4 + len(srows)
    for i in range(5, last + 1):
        ws.cell(i, 12).number_format = "0.0%"
    ws.conditional_formatting.add(f"J5:J{last}", CellIsRule(operator="notEqual", formula=["0"], fill=RED))
    tr = last + 2
    for ent in sorted({r.account["entity"] for r in results}):
        ws.cell(tr, 1, ent).font = BOLD
        ws.cell(tr, 2, "Entity total").font = BOLD
        for col in (6, 7, 8, 9, 10):
            L = get_column_letter(col)
            c = ws.cell(tr, col, f'=SUMIFS({L}5:{L}{last},$A$5:$A${last},"{ent}")')
            c.number_format, c.font = NUM, BOLD
        tr += 1

    # ------------------------------------------------------------ Matches
    wm = wb.create_sheet("Matches")
    mh = ["Account", "Match ID", "Rule", "Confidence", "Status", "Bank lines", "Book lines",
          "Bank dates", "Book dates", "Amount", "Difference", "Note", "Bank UIDs", "Book UIDs"]
    mrows = []
    for r in results:
        bmap = {t.uid: t for t in r.__dict__["all_bank"]}
        kmap = {t.uid: t for t in r.__dict__["all_book"]}
        for m in r.matches:
            bb = [bmap[u] for u in m.bank_uids if u in bmap]
            kk = [kmap[u] for u in m.book_uids if u in kmap]
            amt = sum(t.amount for t in bb) if bb else sum(t.amount for t in kk)
            mrows.append([r.account["id"], m.match_id, m.rule, m.confidence, m.status, len(bb), len(kk),
                          ", ".join(sorted({t.txn_date.strftime('%d-%b') for t in bb})),
                          ", ".join(sorted({t.txn_date.strftime('%d-%b') for t in kk})),
                          amt / 100, m.difference / 100, m.note, ";".join(m.bank_uids), ";".join(m.book_uids)])
    _table(wm, mh, mrows, [14, 9, 14, 10, 10, 8, 8, 16, 16, 16, 12, 45, 24, 24], num_cols=("Amount", "Difference"))

    # ------------------------------------------------------------ Review queue
    wq = wb.create_sheet("Review Queue")
    wq["A1"] = ("Proposed matches below the auto-accept threshold. Enter APPROVE or REJECT in column A and "
                "your name in column B, then load with:  pagerails decide --file <this workbook>")
    wq["A1"].font = Font(name=F, size=9, italic=True)
    qh = ["Decision", "Reviewer", "Note", "Account", "Match ID", "Rule", "Confidence", "Bank side", "Book side",
          "Amount", "Difference", "Engine note", "Bank UIDs", "Book UIDs"]
    qrows = []
    for r in results:
        bmap = {t.uid: t for t in r.__dict__["all_bank"]}
        kmap = {t.uid: t for t in r.__dict__["all_book"]}
        for m in r.matches:
            if m.status != "PROPOSED":
                continue
            bb = [bmap[u] for u in m.bank_uids]
            kk = [kmap[u] for u in m.book_uids]
            qrows.append(["", "", "", r.account["id"], m.match_id, m.rule, m.confidence,
                          " | ".join(f"{t.txn_date:%d-%b} {t.description[:40]}" for t in bb),
                          " | ".join(f"{t.txn_date:%d-%b} {t.description[:40]}" for t in kk),
                          (sum(t.amount for t in bb) if bb else sum(t.amount for t in kk)) / 100,
                          m.difference / 100, m.note, ";".join(m.bank_uids), ";".join(m.book_uids)])
    _table(wq, qh, qrows, [11, 14, 22, 14, 9, 14, 10, 45, 45, 16, 12, 40, 24, 24], start_row=3,
           num_cols=("Amount", "Difference"))
    if qrows:
        dv = DataValidation(type="list", formula1='"APPROVE,REJECT"', allow_blank=True)
        wq.add_data_validation(dv)
        dv.add(f"A4:A{3 + len(qrows)}")
        for i in range(4, 4 + len(qrows)):
            for j in (1, 2, 3):
                wq.cell(i, j).fill = INPUT_FILL

    # ------------------------------------------------------------ Balance Reconciliation (matching manual format)
    wb_rec = wb.create_sheet("Balance Rec")
    wb_rec.column_dimensions["A"].width = 8
    wb_rec.column_dimensions["B"].width = 50
    wb_rec.column_dimensions["C"].width = 18
    wb_rec.column_dimensions["D"].width = 18
    wb_rec.column_dimensions["E"].width = 18

    row = 1
    for r in results:
        a = r.account
        is_credit_gl = a.get("gl_balance_convention") == "credit"
        L = r.lines

        wb_rec.cell(row, 1, a["id"]).font = TITLE
        wb_rec.cell(row, 2, a.get("gl_account", "")).font = Font(name=F, size=12, bold=True, color="1F2A44")
        row += 1
        wb_rec.cell(row, 2, f"{entities[a['entity']]['name']}").font = BOLD
        row += 1
        wb_rec.cell(row, 2, f"{a['bank']} Account — Client").font = BODY
        row += 1
        wb_rec.cell(row, 2, f"{r.period_end.strftime('%B %Y')} Bank Reconciliation").font = BOLD
        row += 2

        def brc(label, amount, bold=False, border=None):
            nonlocal row
            c1 = wb_rec.cell(row, 2, label)
            c1.font = BOLD if bold else BODY
            if amount is not None:
                c3 = wb_rec.cell(row, 4 if not bold else 5, amount / 100 if isinstance(amount, int) else amount)
                c3.number_format = NUM
                c3.font = BOLD if bold else BODY
                if border:
                    c3.border = border
            row += 1

        # Bank side
        brc("Balance as per Bank Statement", r.bank_close, bold=True)
        row += 1

        # Credits in bank not in GL
        cred_items = [(t.txn_date.strftime("%d/%m/%Y"), t.description[:60], t.amount)
                      for t in r.open_bank if t.amount > 0]
        wb_rec.cell(row, 2, "Credit in Bank Not in Ledger").font = BOLD
        row += 1
        wb_rec.cell(row, 3, "Date").font = Font(name=F, size=9, bold=True, color="595959")
        wb_rec.cell(row, 4, "Details").font = Font(name=F, size=9, bold=True, color="595959")
        wb_rec.cell(row, 5, "Amount").font = Font(name=F, size=9, bold=True, color="595959")
        row += 1
        for dt, desc, amt in cred_items:
            wb_rec.cell(row, 3, dt).font = Font(name=F, size=9)
            wb_rec.cell(row, 4, desc).font = Font(name=F, size=9)
            c = wb_rec.cell(row, 5, amt / 100)
            c.number_format = NUM
            c.font = Font(name=F, size=9)
            row += 1
        # subtotal credits
        cred_total = L["credits_bank_not_gl"]
        c = wb_rec.cell(row, 5, cred_total / 100)
        c.number_format = NUM
        c.font = BOLD
        c.border = TOP
        row += 2

        # Debits in bank not in GL
        deb_items = [(t.txn_date.strftime("%d/%m/%Y"), t.description[:60], abs(t.amount))
                     for t in r.open_bank if t.amount < 0]
        wb_rec.cell(row, 2, "Debit in Bank Not in Ledger").font = BOLD
        row += 1
        wb_rec.cell(row, 3, "Date").font = Font(name=F, size=9, bold=True, color="595959")
        wb_rec.cell(row, 4, "Details").font = Font(name=F, size=9, bold=True, color="595959")
        wb_rec.cell(row, 5, "Amount").font = Font(name=F, size=9, bold=True, color="595959")
        row += 1
        for dt, desc, amt in deb_items:
            wb_rec.cell(row, 3, dt).font = Font(name=F, size=9)
            wb_rec.cell(row, 4, desc).font = Font(name=F, size=9)
            c = wb_rec.cell(row, 5, amt / 100)
            c.number_format = NUM
            c.font = Font(name=F, size=9)
            row += 1
        deb_total = abs(L["debits_bank_not_gl"])
        c = wb_rec.cell(row, 5, deb_total / 100)
        c.number_format = NUM
        c.font = BOLD
        c.border = TOP
        row += 2

        # GL side
        brc("Balance as per General Ledger (GL)", r.book_close, bold=True)
        row += 1

        # Credits in GL not in bank
        gl_cred = [(t.txn_date.strftime("%d/%m/%Y"), t.description[:60], t.amount)
                   for t in r.open_book if t.amount > 0]
        wb_rec.cell(row, 2, "Credit in Ledger Not in Bank").font = BOLD
        row += 1
        for dt, desc, amt in gl_cred:
            wb_rec.cell(row, 3, dt).font = Font(name=F, size=9)
            wb_rec.cell(row, 4, desc).font = Font(name=F, size=9)
            c = wb_rec.cell(row, 5, amt / 100); c.number_format = NUM; c.font = Font(name=F, size=9)
            row += 1
        c = wb_rec.cell(row, 5, L["credits_gl_not_bank"] / 100)
        c.number_format = NUM; c.font = BOLD; c.border = TOP; row += 2

        # Debits in GL not in bank
        gl_deb = [(t.txn_date.strftime("%d/%m/%Y"), t.description[:60], abs(t.amount))
                  for t in r.open_book if t.amount < 0]
        wb_rec.cell(row, 2, "Debit in Ledger Not in Bank").font = BOLD
        row += 1
        for dt, desc, amt in gl_deb:
            wb_rec.cell(row, 3, dt).font = Font(name=F, size=9)
            wb_rec.cell(row, 4, desc).font = Font(name=F, size=9)
            c = wb_rec.cell(row, 5, amt / 100); c.number_format = NUM; c.font = Font(name=F, size=9)
            row += 1
        c = wb_rec.cell(row, 5, abs(L["debits_gl_not_bank"]) / 100)
        c.number_format = NUM; c.font = BOLD; c.border = TOP; row += 2

        # Difference
        diff_cell = wb_rec.cell(row, 4, "Difference")
        diff_cell.font = BOLD
        d = wb_rec.cell(row, 5, r.difference / 100)
        d.number_format = NUM; d.font = BOLD; d.border = DBL
        d.fill = GREEN if r.difference == 0 else RED
        row += 3

    # ------------------------------------------------------------ Symplus Import batch
    # Two rows per journal entry (DR leg + CR leg) — matches the Symplus "Loaded Data" import format.
    # Column order confirmed from the Symplus Loaded Data screen (Oct 2026).
    ws_sym = wb.create_sheet("Symplus Import")
    sym_headers = ["Book of Account", "Batch ID", "Batch Desc.", "Account", "Currency",
                   "Trans.Code", "Trans. Description", "Dr/Cr", "Exch.Rate",
                   "Amount", "Cost Center", "Reference", "Effective Date"]
    sym_widths  = [16, 22, 45, 16, 10, 11, 45, 7, 10, 16, 12, 22, 14]

    for j, h in enumerate(sym_headers, 1):
        c = ws_sym.cell(1, j, h)
        c.fill, c.font = HDR_FILL, HDR_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
    for j, w in enumerate(sym_widths, 1):
        ws_sym.column_dimensions[get_column_letter(j)].width = w

    sym_row = 2
    for r in results:
        a = r.account
        book = a.get("book_of_account", "GL08")
        tcode = a.get("trans_code", "000")
        batch_prefix = a.get("posting", {}).get("batch_prefix", "PAGERAILS")
        batch_id = f"{batch_prefix}-{r.period_end.strftime('%Y%m%d')}-{r.__dict__.get('run_id', '')[-6:]}"

        for j in r.journals:
            if j.get("status", "").startswith("HOLD"):
                continue                    # do not include holds in the import file
            narration = j["narration"][:60]
            eff_date = datetime.strptime(j["date"], "%Y-%m-%d").strftime("%d-%b-%Y").upper()
            amount = j["amount"]
            ref = batch_id

            # DR leg
            dr_row = [book, batch_id, narration, j["dr_gl"], a.get("currency", "NGN"),
                      tcode, narration, "D", 1, amount, "", ref, eff_date]
            for col, val in enumerate(dr_row, 1):
                c = ws_sym.cell(sym_row, col, val)
                c.font = BODY
                if col == 10:
                    c.number_format = NUM
            sym_row += 1

            # CR leg
            cr_row = [book, batch_id, narration, j["cr_gl"], a.get("currency", "NGN"),
                      tcode, narration, "C", 1, amount, "", ref, eff_date]
            for col, val in enumerate(cr_row, 1):
                c = ws_sym.cell(sym_row, col, val)
                c.font = BODY
                if col == 10:
                    c.number_format = NUM
            sym_row += 1

        # Separator row between accounts
        sym_row += 1

    ws_sym.freeze_panes = "A2"

    # ------------------------------------------------------------ Draft journals
    wj = wb.create_sheet("Draft Journals")
    jh = ["Entity", "Account", "Date", "Category", "Dr GL", "Cr GL", "Amount", "Bank lines", "Narration", "Status", "Bank UID"]
    jrows = [[j["entity"], j["account_id"], j["date"], j["category"], j["dr_gl"], j["cr_gl"], j["amount"],
              j.get("lines", 1), j["narration"], j["status"], j["uid"]] for r in results for j in r.journals]
    _table(wj, jh, jrows, [7, 14, 11, 22, 14, 14, 15, 9, 50, 34, 20], num_cols=("Amount",))

    # ------------------------------------------------------------ Ageing (formula pivot)
    wa = wb.create_sheet("Ageing")
    buckets = sorted({row[5] for row in orows if row[5]}, key=lambda b: int(b.strip(">").split("-")[0]))
    std = ["0-7", "8-30", "31-90", ">90"]
    buckets = std + [b for b in buckets if b not in std]
    ah = ["Account", "Side"] + [f"{b} days" for b in buckets] + ["Total"]
    arows = []
    OF = f"'Open Items'!$F$2:$F${n_open}"
    for r in results:
        for side in ("BANK", "BOOK"):
            i = len(arows) + 2
            row = [r.account["id"], side]
            for b in buckets:
                row.append(f'=SUMIFS({OG},{OA},$A{i},{OB},$B{i},{OF},"{b}")')
            row.append(f"=SUM(C{i}:{get_column_letter(2 + len(buckets))}{i})")
            arows.append(row)
    _table(wa, ah, arows, [15, 8] + [16] * (len(buckets) + 1), num_cols=tuple(ah[2:]))

    # ------------------------------------------------------------ Alerts
    wl = wb.create_sheet("Alerts")
    lh = ["Severity", "Account", "Code", "Message", "UID"]
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    lrows = sorted([[x["severity"], x["account_id"], x["code"], x["message"], x["uid"]] for r in results for x in r.alerts],
                   key=lambda x: (order.get(x[0], 9), x[1]))
    _table(wl, lh, lrows, [9, 15, 26, 100, 20])
    for i, row in enumerate(lrows, 2):
        wl.cell(i, 1).fill = RED if row[0] == "HIGH" else AMBER

    wb.move_sheet("Open Items", offset=len(wb.sheetnames))
    for sh in wb.worksheets:      # print-ready: landscape, one page wide
        sh.page_setup.orientation = "portrait" if sh.title.startswith("REC ") else "landscape"
        sh.page_setup.paperSize = sh.PAPERSIZE_A4
        sh.page_setup.fitToWidth, sh.page_setup.fitToHeight = 1, 0
        sh.sheet_properties.pageSetUpPr.fitToPage = True
    wb.save(path)
    return path
