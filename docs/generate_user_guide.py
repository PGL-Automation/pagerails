"""Generates the PageRails User Guide v1.1 as a formatted Word document."""
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from pathlib import Path
from datetime import datetime

OUT = Path(__file__).parent / "PageRails_User_Guide.docx"

# ── Colours ────────────────────────────────────────────────────────────────────
BLACK  = RGBColor(0x09, 0x09, 0x09)
DARK   = RGBColor(0x1F, 0x2A, 0x44)
GREY   = RGBColor(0x59, 0x59, 0x59)
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
GREEN  = RGBColor(0x06, 0x8A, 0x5E)
AMBER  = RGBColor(0x92, 0x63, 0x00)
BLUE   = RGBColor(0x1D, 0x4E, 0xD8)

doc = Document()
section = doc.sections[0]
section.page_width    = Inches(8.27)
section.page_height   = Inches(11.69)
section.left_margin   = Inches(1.0)
section.right_margin  = Inches(1.0)
section.top_margin    = Inches(1.0)
section.bottom_margin = Inches(1.0)

style = doc.styles["Normal"]
style.font.name      = "Calibri"
style.font.size      = Pt(10.5)
style.font.color.rgb = BLACK


def _set_font(run, bold=False, size=10.5, color=BLACK, italic=False):
    run.font.name    = "Calibri"
    run.font.size    = Pt(size)
    run.font.bold    = bold
    run.font.italic  = italic
    run.font.color.rgb = color


def _shade_cell(cell, hex_color: str):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  hex_color)
    tcPr.append(shd)


def heading(text, level=1, color=DARK):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(20 if level == 1 else 14)
    p.paragraph_format.space_after  = Pt(6)
    r = p.add_run(text)
    _set_font(r, bold=True, size={1: 16, 2: 13, 3: 11.5}.get(level, 11), color=color)
    return p


def body(text, space_after=6, color=BLACK, italic=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    r = p.add_run(text)
    _set_font(r, color=color, italic=italic)
    return p


def bullet(text, sub=False):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.left_indent = Inches(0.55 if sub else 0.3)
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(text)
    _set_font(r, size=10 if sub else 10.5)
    return p


def note_box(text, bg_hex="FFF8E7", label="Note", label_color=AMBER):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent  = Inches(0.3)
    p.paragraph_format.right_indent = Inches(0.3)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(8)
    lr = p.add_run(f"{label}:  ")
    _set_font(lr, bold=True, size=10, color=label_color)
    tr = p.add_run(text)
    _set_font(tr, size=10, color=GREY, italic=True)


def table(headers, rows, col_widths=None):
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    hdr = t.rows[0]
    for j, h in enumerate(headers):
        c = hdr.cells[j]
        _shade_cell(c, "1F2A44")
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = c.paragraphs[0]
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after  = Pt(4)
        r = p.add_run(h)
        _set_font(r, bold=True, size=9.5, color=WHITE)
    for i, row_data in enumerate(rows):
        row = t.rows[i + 1]
        fill = "F9F9F9" if i % 2 == 0 else "FFFFFF"
        for j, val in enumerate(row_data):
            c = row.cells[j]
            _shade_cell(c, fill)
            c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = c.paragraphs[0]
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after  = Pt(3)
            r = p.add_run(str(val))
            _set_font(r, size=9.5)
    if col_widths:
        for j, w in enumerate(col_widths):
            for row in t.rows:
                row.cells[j].width = Inches(w)
    doc.add_paragraph()
    return t


def divider():
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(4)
    pPr  = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    b    = OxmlElement("w:bottom")
    b.set(qn("w:val"),   "single")
    b.set(qn("w:sz"),    "4")
    b.set(qn("w:space"), "1")
    b.set(qn("w:color"), "E5E5E5")
    pBdr.append(b)
    pPr.append(pBdr)


def page_break():
    doc.add_page_break()


# ══════════════════════════════════════════════════════════════════════════════
# COVER PAGE
# ══════════════════════════════════════════════════════════════════════════════

for _ in range(4):
    doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
_set_font(p.add_run("PageRails"), bold=True, size=40, color=DARK)

p2 = doc.add_paragraph()
p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
_set_font(p2.add_run("Financial Operations Platform"), size=16, color=GREY)

doc.add_paragraph()

p3 = doc.add_paragraph()
p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
_set_font(p3.add_run("User Guide  —  Version 1.1"), bold=True, size=20, color=DARK)

doc.add_paragraph()

p4 = doc.add_paragraph()
p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
_set_font(p4.add_run("Page Capital Group  ·  Confidential"), size=11, color=GREY)

p5 = doc.add_paragraph()
p5.alignment = WD_ALIGN_PARAGRAPH.CENTER
_set_font(p5.add_run(datetime.now().strftime("%B %Y")), size=11, color=GREY)

page_break()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — WHAT IS PAGERAILS?
# ══════════════════════════════════════════════════════════════════════════════

heading("1.  What is PageRails?")
body(
    "PageRails is the daily bank reconciliation and financial operations platform "
    "for Page Asset Management Limited and Page Capital Limited. It automatically "
    "compares your Providus bank statement against your Symplus accounting records "
    "every day, finds the differences between the two, and prepares the journal "
    "entries your finance team needs to post in Symplus to close those differences."
)
body(
    "The system is designed around a simple principle: the machines do the "
    "repetitive work (pulling data, matching transactions, drafting journals), "
    "and humans do the things only humans should do (reviewing, approving, signing off)."
)

heading("Can the system run end-to-end with only human input at the approval stage?", level=2)
body(
    "Yes — and this is the intended operating model. Once the Providus Bank API "
    "and the Symplus GL API are fully connected, the entire pipeline from data "
    "collection through to journal preparation runs automatically every evening "
    "with no manual steps. The only human touches required are:"
)
bullet("Reviewing and approving the draft journals (Maker — typically 5–10 minutes)")
bullet("Signing off the completed reconciliation (Checker — typically 2–5 minutes)")
body(
    "These two steps are not just procedural — they are a compliance requirement. "
    "Client-money reconciliations must have maker-checker sign-off under SEC and "
    "CBN regulations. PageRails enforces this and records it permanently in its "
    "tamper-evident audit log."
)
note_box(
    "The Providus Bank API and the Symplus posting API are pending activation. "
    "Until they are live, the bank statement and GL are uploaded manually (Files page → "
    "Data Feeds page) and journals are posted via a CSV file loaded into Symplus. "
    "The workflow is identical — only the data collection step changes.",
    label="Current status"
)

divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — THE DAILY FLOW
# ══════════════════════════════════════════════════════════════════════════════

heading("2.  The Daily Reconciliation Flow")
body(
    "The Providus Client Account (NUBAN ****2286) is reconciled daily. "
    "The full cycle — from pulling the data to the checker's sign-off — "
    "is designed to be completed within the same business day."
)

table(
    ["Time", "Who", "What happens", "Automated?"],
    [
        ["8:30 PM", "System",              "GL entries for today pulled from Symplus",                              "Yes (when Symplus API is live)"],
        ["9:00 PM", "System",              "Today's bank statement pulled from Providus",                           "Yes (when Providus API is live)"],
        ["9:05 PM", "System",              "Reconciliation runs automatically — matches transactions, drafts journals", "Yes — fully automatic"],
        ["9:30 PM", "Finance Officer\n(Maker)",  "Logs in, reads Balance Rec, approves journals",                "Human — compliance requirement"],
        ["9:45 PM", "Finance Officer\n(Maker)",  "Downloads Symplus import CSV, loads into Symplus, posts",      "Human — until Symplus API is live"],
        ["Next AM",  "Finance Manager\n(Checker)", "Reviews and signs off the completed reconciliation",         "Human — compliance requirement"],
    ],
    col_widths=[0.9, 1.3, 2.8, 1.4],
)

note_box(
    "For operating accounts (PAM-OPS-01, PCL-OPS-01) reconciled monthly, "
    "the same steps apply at month-end rather than daily.",
    label="Monthly accounts"
)

divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — WHO DOES WHAT
# ══════════════════════════════════════════════════════════════════════════════

heading("3.  Who Does What — Roles and Permissions")
body("Every person in the system is assigned a role by the Admin. "
     "Your role controls what you can see and do.")

table(
    ["Role", "Who this is", "What they can do"],
    [
        ["Maker",   "Finance Officer",        "Upload files, trigger runs, review results, approve journals, post to Symplus"],
        ["Checker", "Finance Manager",         "Review the maker's work and provide formal sign-off. Cannot sign off their own runs."],
        ["Viewer",  "Management / Auditors",   "Read-only — can view all reports and the audit log, cannot change anything"],
        ["Admin",   "IT Lead / Administrator", "Add and manage users, assign permissions, configure system settings"],
    ],
    col_widths=[1.0, 1.6, 3.8],
)

note_box(
    "Maker-checker separation is enforced automatically. A maker cannot sign off "
    "their own reconciliation — the system will block it. This is a built-in "
    "compliance control and cannot be bypassed."
)

divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — GETTING STARTED
# ══════════════════════════════════════════════════════════════════════════════

heading("4.  Getting Started")

heading("4.1  Logging In", level=2)
body("Open your browser and go to the PageRails URL. "
     "Enter your work email and password. If it is your first time, "
     "your admin provides your login details.")

heading("4.2  Navigation", level=2)
body("The left sidebar has eight pages. Here is what each one is for:")

table(
    ["Page", "What it is for"],
    [
        ["Dashboard",    "Overview — are all accounts reconciled? Any unresolved issues?"],
        ["Runs",         "Full history of every reconciliation run. Click any row to open it."],
        ["Review Queue", "Uncertain matches that need a human decision (Approve or Reject)"],
        ["Accounts",     "List of all bank accounts configured in the system"],
        ["Data Feeds",   "Pull bank statements and GL from Symplus manually or check auto-schedule status"],
        ["Files",        "Upload bank statements and GL exports by drag-and-drop"],
        ["Audit Log",    "Permanent tamper-evident record of every action"],
        ["Settings",     "Admin only — add users, assign permissions"],
    ],
    col_widths=[1.4, 5.0],
)

divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — END-TO-END STEPS
# ══════════════════════════════════════════════════════════════════════════════

heading("5.  The Five Steps — End to End")
body("A daily reconciliation follows these five steps. Steps 1 and 2 will be "
     "fully automatic once the APIs are connected. Steps 3, 4, and 5 always "
     "require a human.")

# ── Step 1 ──────────────────────────────────────────────────────────────────

heading("Step 1 — Get the Data into the System", level=2)

body("The system needs two inputs for each account:")
table(
    ["Input", "What it is", "How it arrives today", "How it will arrive (automated)"],
    [
        ["Bank Statement",
         "Every transaction on the Providus account — debits, credits, charges",
         "Downloaded from Providus internet banking and uploaded on the Files page",
         "Automatically at 9:00 PM via Providus Bank API (pending API credentials)"],
        ["GL Export (Symplus)",
         "The accounting entries posted against the bank account GL in Symplus",
         "Exported by the Symplus admin and placed in the watch directory",
         "Automatically at 8:30 PM via Symplus GL API (pending Neulogic access)"],
    ],
    col_widths=[1.2, 2.0, 1.9, 1.3],
)

heading("To upload files manually:", level=3)
bullet("Click Files in the sidebar.")
bullet("Select the account and period.")
bullet("Drag and drop both files. A green tick confirms receipt.")

heading("To trigger an auto-fetch manually:", level=3)
bullet("Click Data Feeds in the sidebar.")
bullet("Select the account.")
bullet("Choose the date range (today's date for a daily run).")
bullet("Click Fetch now under Bank Statement or Fetch GL from Symplus.")
body("The Data Feeds page also shows the automatic schedule status — "
     "whether the nightly 9 PM fetch is configured and when it next runs.")

# ── Step 2 ──────────────────────────────────────────────────────────────────

heading("Step 2 — Run the Reconciliation", level=2)
body("Once the files are in the system, trigger the reconciliation:")
bullet("Go to the Dashboard or Runs page.")
bullet("Click New Run.")
bullet("Select the account, the date (today), and enter your name as the Maker.")
bullet("Click Run. Results appear within seconds.")

note_box(
    "When auto_fetch is enabled in the configuration, Step 2 also runs automatically "
    "at 9:05 PM — five minutes after the bank statement arrives. No manual trigger needed.",
    label="Fully automated"
)

# ── Step 3 ──────────────────────────────────────────────────────────────────

heading("Step 3 — Review the Results (Maker)", level=2)
body("Click the run in the Runs list to open it. It has five tabs:")

table(
    ["Tab", "What it shows", "What you do"],
    [
        ["Overview",       "Bank balance, GL balance, reconciling difference",
         "Check the difference. If zero — fully reconciled. If not — read the next tab."],
        ["Balance Rec",    "The formal reconciliation statement: credits in bank not in GL, debits in bank not in GL, difference",
         "Read and confirm you understand each category. This is the document you file."],
        ["Review Queue",   "Transactions the system matched but is not 100% certain about",
         "For each item: click Approve if the match is correct, Reject if it is not. Use A/R keys to move fast."],
        ["Draft Journals", "Proposed Symplus journal entries to record timing items",
         "Read each journal. Click Approve on the ones that look correct. Leave HOLD items for investigation."],
        ["Posting",        "Download the Symplus import file and trigger posting",
         "See Step 4."],
    ],
    col_widths=[1.1, 2.5, 2.8],
)

note_box(
    "The Review Queue and Draft Journals tabs are where the bulk of human review "
    "happens. On a well-configured account, the Review Queue will have fewer than "
    "10 items and the Draft Journals will be straightforward. The system handles "
    "the other 1,200+ transactions automatically."
)

# ── Step 4 ──────────────────────────────────────────────────────────────────

heading("Step 4 — Post the Journals to Symplus (Maker)", level=2)
body("After approving journals in Step 3, go to the Posting tab and follow three steps:")

table(
    ["#", "Action", "How"],
    [
        ["1", "Confirm approvals",
         "The tab shows how many journals are approved and how many are still on HOLD."],
        ["2", "Download the CSV",
         "Click Download CSV. You get a file already formatted for Symplus — two rows per entry (debit leg and credit leg), dates in DD-MON-YYYY format."],
        ["3", "Load into Symplus",
         "Open Symplus. Go to General Ledger → Loaded Data → Import. Upload the CSV. Review the entries on screen. Click Post."],
    ],
    col_widths=[0.4, 1.6, 4.4],
)

note_box(
    "Once Neulogic provides the Symplus REST API posting endpoint, the Download CSV "
    "step disappears. You simply click Post in PageRails and Symplus is updated directly.",
    label="Coming soon"
)

# ── Step 5 ──────────────────────────────────────────────────────────────────

heading("Step 5 — Sign Off (Checker)", level=2)
body("A different person from the maker logs in, opens the same run, reads the "
     "Balance Rec tab, and clicks Sign off. They enter their name and confirm.")
bullet("If there is still an unexplained difference, the system requires a note explaining why.")
bullet("The sign-off is permanently recorded with date, time, and a cryptographic fingerprint.")
bullet("The sign-off cannot be deleted or altered — this is your compliance record.")

divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — THE DATA FEEDS PAGE
# ══════════════════════════════════════════════════════════════════════════════

heading("6.  The Data Feeds Page")
body("The Data Feeds page is the control centre for getting data into PageRails. "
     "Click Data Feeds in the left sidebar.")

body("It has four sections:")

heading("The daily flow diagram", level=2)
body("A visual strip across the top shows the full daily cycle — from GL fetch at "
     "8:30 PM to checker sign-off the next morning. Green steps are automated; "
     "blue steps require a human.")

heading("Account selector", level=2)
body("Choose which account you want to fetch data for. Each account has its own "
     "bank statement and GL feed configured.")

heading("Fetch cards", level=2)
body("Two side-by-side cards:")
bullet("Fetch Bank Statement — set the date range and click Fetch now. The system pulls the "
       "statement from Providus (via API when configured) or from the email inbox.")
bullet("Fetch GL from Symplus — pulls ledger entries from Symplus for the selected dates. "
       "Currently uses watch-folder mode (Symplus admin drops the file in a directory).")

heading("Automatic Schedule", level=2)
body("Shows the nightly scheduled jobs — when they next run and what trigger is set. "
     "When auto_fetch is enabled for an account, three jobs appear here:")
bullet("GL fetch at 8:30 PM (Africa/Lagos time)")
bullet("Bank statement fetch at 9:00 PM")
bullet("Automatic reconciliation run at 9:05 PM")
body("If no jobs are shown, the automatic schedule is not yet enabled. "
     "Your IT admin enables it per account once the API credentials are configured.")

heading("Connection Status", level=2)
body("Shows the current state of each external connection:")
table(
    ["Connection", "Current status", "What is needed to automate it"],
    [
        ["Providus Bank API",    "Pending",         "Providus RM to enable the Account Statement API; IT to configure credentials"],
        ["Symplus GL Export",    "Active (manual)",  "Symplus admin drops the export file; Symplus API pending from Neulogic"],
        ["Symplus Posting API",  "Pending",          "Neulogic to provide the REST posting endpoint and credentials"],
    ],
    col_widths=[1.8, 1.4, 3.2],
)

divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — THE AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════

heading("7.  The Audit Log")
body("Click Audit Log in the sidebar to see a permanent record of every action "
     "taken in the system — every run, every approval, every sign-off.")
body("The log is tamper-evident. Each entry is linked to the one before it using "
     "a cryptographic hash. If anyone altered a past record, the chain would break "
     "and the system would flag it. Click Verify Chain at any time to confirm integrity.")
body("This is the record you present to Internal Audit, SEC, or CBN when they "
     "ask for the reconciliation trail.")

divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — MANAGING USERS (ADMIN)
# ══════════════════════════════════════════════════════════════════════════════

heading("8.  Managing Users  (Admin only)")
body("Go to Settings → Add user. Enter the person's name, email, and password. "
     "Select their role and tick the specific permissions they need.")

table(
    ["Permission", "What it allows"],
    [
        ["Trigger reconciliation run",  "Start a new run"],
        ["Upload files",                "Upload files on the Files page"],
        ["Fetch bank statement (auto)", "Trigger a pull from Providus API"],
        ["Fetch GL from ledger (auto)", "Trigger a pull from Symplus"],
        ["Approve / reject matches",    "Make decisions in the Review Queue"],
        ["Sign off a completed run",    "Checker sign-off"],
        ["Approve draft journals",      "Approve journal entries on the Draft Journals tab"],
        ["Post journals to ledger",     "Execute the Symplus posting"],
        ["View audit log",              "Access the tamper-evident trail"],
        ["Manage users",                "Add, edit, and deactivate user accounts (Admin)"],
        ["Manage connectors",           "Configure API credentials (Admin)"],
    ],
    col_widths=[2.8, 3.6],
)

divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — GLOSSARY
# ══════════════════════════════════════════════════════════════════════════════

heading("9.  Glossary")
table(
    ["Term", "Plain English meaning"],
    [
        ["Reconciliation",     "Proving that the bank and the books record the same money"],
        ["Bank statement",     "Providus's official record of every transaction through the account"],
        ["GL / General Ledger","The Symplus accounting records — what finance has posted as journal entries"],
        ["Timing item",        "A transaction in the bank but not yet posted in Symplus (or vice versa) due to a processing delay"],
        ["Credit balance",     "The Symplus GL shows the client account as a negative number — normal, it means the fund owes that amount to clients (a liability)"],
        ["Open item",          "A transaction the system could not match between bank and GL"],
        ["Draft journal",      "A proposed accounting entry to record a bank transaction in Symplus"],
        ["Maker",              "The person who prepares the reconciliation"],
        ["Checker",            "The person who independently reviews and signs off"],
        ["Audit log",          "Permanent, tamper-proof record of every system action"],
        ["Auto-match",         "A match made with ≥90% confidence — no human review needed"],
        ["Proposed match",     "A match the system is less certain about — human must approve or reject"],
        ["HOLD",               "A journal that needs investigation before posting (usually an unidentified client-money credit)"],
        ["Symplus Import CSV", "The file downloaded from the Posting tab — upload this into Symplus → GL → Loaded Data → Import"],
        ["Data Feeds page",    "The page in PageRails where you trigger manual fetches and check the auto-schedule status"],
    ],
    col_widths=[1.8, 4.6],
)

divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — COMMON QUESTIONS
# ══════════════════════════════════════════════════════════════════════════════

heading("10.  Common Questions")

heading("Where are the buttons to fetch the bank statement and GL?", level=2)
body("Click Data Feeds in the left sidebar. You will see two cards side by side — "
     "one for the bank statement, one for the GL. Select the account, choose the "
     "date range (today for a daily run), and click Fetch now.")

heading("The reconciling difference is not zero — is something wrong?", level=2)
body("Not necessarily. For the Providus Client Account, a non-zero difference "
     "almost always means timing items — transactions on the bank statement not "
     "yet posted in Symplus. Look at the Balance Rec tab. The 'Debit in Bank Not in "
     "Ledger' section will list every such item, including any investment placements "
     "or time deposits. Once those are posted in Symplus and the system is re-run, "
     "the difference should reach zero.")

heading("Does the system run daily by itself?", level=2)
body("It is designed to, yes. The nightly schedule (8:30 PM GL, 9:00 PM statement, "
     "9:05 PM run) fires automatically once enabled. Currently it is off because the "
     "Providus API credentials are not yet configured. Once your Providus RM enables "
     "the API, your IT admin adds the credentials to the system, turns on the schedule, "
     "and from that point the system runs every night without anyone touching it — "
     "until the finance officer logs in to review and approve.")

heading("The system flagged something as HOLD — what do I do?", level=2)
body("A HOLD item is an unidentified credit into the client-money account. You must "
     "identify which client the money belongs to before posting. Check the bank "
     "narration for the sender's name. Once identified, post the correct entry in "
     "Symplus manually and re-run.")

heading("I uploaded the wrong file — how do I fix it?", level=2)
body("Upload the correct file on the Files page (same account, same period), "
     "then trigger a new run. Old runs stay in the history for audit purposes but "
     "do not affect the new run.")

heading("Where is the final document I can file as the reconciliation record?", level=2)
body("Click Download Pack on any run. This gives you the full Excel file with: "
     "Summary, Balance Rec statement, Matches, Review Queue, Draft Journals, "
     "Open Items, and the Symplus Import batch. This is the document you file "
     "as the permanent record for that period.")

divider()


# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════

doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
_set_font(p.add_run(
    f"PageRails v1.1  ·  Page Capital Group  ·  {datetime.now().strftime('%B %Y')}  ·  Confidential"
), size=9, color=GREY, italic=True)


# ── Save ───────────────────────────────────────────────────────────────────────
OUT.parent.mkdir(exist_ok=True)
doc.save(str(OUT))
print(f"✓  Written: {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")
