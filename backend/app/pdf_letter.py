"""
pdf_letter.py — PageRails bank instruction letter generator.

Public API
----------
generate_letter(request: dict, account: dict) -> str
    Returns a complete, self-contained HTML string optimised for A4 printing.

amount_in_words(kobo: int) -> str
    Converts an integer kobo amount to English words.
    e.g.  12_050_000_kobo → "One Hundred and Twenty Thousand, Five Hundred Naira Only"

Signatory images
----------------
Looks for signature files at:
    /opt/pagerails/signatures/signatory_1.{jpg,png}
    /opt/pagerails/signatures/signatory_2.{jpg,png}
Gracefully skips if not present.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Amount-in-words
# ---------------------------------------------------------------------------

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_thousand(n: int) -> str:
    if n == 0:
        return ""
    if n < 20:
        return _ONES[n]
    if n < 100:
        t = _TENS[n // 10]
        o = _ONES[n % 10]
        return t + (" " + o if o else "")
    h = _ONES[n // 100] + " Hundred"
    remainder = n % 100
    if remainder:
        return h + " and " + _below_thousand(remainder)
    return h


def _number_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    parts: list[str] = []
    billions = n // 1_000_000_000
    millions = (n % 1_000_000_000) // 1_000_000
    thousands = (n % 1_000_000) // 1_000
    remainder = n % 1_000

    if billions:
        parts.append(_below_thousand(billions) + " Billion")
    if millions:
        parts.append(_below_thousand(millions) + " Million")
    if thousands:
        parts.append(_below_thousand(thousands) + " Thousand")
    if remainder:
        if parts:
            parts.append("and " + _below_thousand(remainder))
        else:
            parts.append(_below_thousand(remainder))

    return ", ".join(parts)


def amount_in_words(kobo: int) -> str:
    """
    Convert a kobo integer to English currency words.

    Parameters
    ----------
    kobo : int
        Amount in kobo (100 kobo = 1 NGN).

    Returns
    -------
    str
        e.g. "Twelve Million, Five Hundred Thousand Naira Only"
        or   "Twelve Million, Five Hundred Thousand Naira and Fifty Kobo Only"
    """
    naira = kobo // 100
    k_rem = kobo % 100

    naira_words = _number_to_words(naira) + " Naira"
    if k_rem:
        return naira_words + " and " + _number_to_words(k_rem) + " Kobo Only"
    return naira_words + " Only"


# ---------------------------------------------------------------------------
# Signature loader
# ---------------------------------------------------------------------------

_SIG_DIR = Path(os.getenv("PAGERAILS_SIGNATURE_DIR", "/opt/pagerails/signatures"))


def _load_signature_b64(role: str) -> tuple[str, str] | None:
    """
    Try to load a signature image for *role* (e.g. 'signatory_1').

    Returns (data_uri_src, mime_type) or None if file not found.
    """
    for ext, mime in [("jpg", "image/jpeg"), ("png", "image/png")]:
        path = _SIG_DIR / f"{role}.{ext}"
        if path.exists():
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{data}", mime
    return None


# ---------------------------------------------------------------------------
# Entity helpers
# ---------------------------------------------------------------------------

_ENTITY_NAMES: dict[str, str] = {
    "PAM": "Page Asset Management Limited",
    "PCL": "Page Capital Limited",
}


def _entity_name(entity_code: str) -> str:
    return _ENTITY_NAMES.get(entity_code.upper(), entity_code)


def _format_date(dt: datetime | str | None = None) -> str:
    """Return a date string in '19 October 2026' format."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.strftime("%-d %B %Y")


def _fmt_amount(kobo: int) -> str:
    """Format kobo as '₦1,234,567.00'."""
    naira = kobo / 100
    return f"₦{naira:,.2f}"


# ---------------------------------------------------------------------------
# HTML generation helpers
# ---------------------------------------------------------------------------

_INLINE_CSS = """
    @page {
        size: A4;
        margin: 20mm 18mm 20mm 18mm;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 10.5pt;
        color: #1a1a1a;
        background: #fff;
    }
    .page {
        width: 100%;
        max-width: 794px;          /* A4 width at 96 dpi */
        margin: 0 auto;
        padding: 24px 32px 32px 32px;
    }
    /* ── Header ── */
    .header {
        border-bottom: 2.5px solid #0d2d6e;
        padding-bottom: 10px;
        margin-bottom: 16px;
    }
    .company-name {
        font-size: 15pt;
        font-weight: 700;
        color: #0d2d6e;
        letter-spacing: 0.02em;
    }
    .letter-title {
        font-size: 13pt;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #0d2d6e;
        margin: 14px 0 4px 0;
        text-align: center;
    }
    .instruction-ref {
        font-size: 15pt;
        font-weight: 800;
        text-align: center;
        color: #0d2d6e;
        background: #edf2fb;
        border: 1.5px solid #0d2d6e;
        border-radius: 4px;
        padding: 6px 16px;
        margin: 8px auto 18px auto;
        display: inline-block;
        letter-spacing: 0.05em;
    }
    .ref-block { text-align: center; }
    /* ── Meta rows ── */
    .meta-row {
        display: flex;
        gap: 32px;
        margin-bottom: 6px;
        font-size: 10pt;
    }
    .meta-label { color: #666; width: 80px; flex-shrink: 0; }
    .meta-value { font-weight: 600; }
    /* ── Body text ── */
    .body-text {
        margin: 14px 0 12px 0;
        line-height: 1.6;
    }
    /* ── Beneficiary table ── */
    table.ben-table {
        width: 100%;
        border-collapse: collapse;
        margin: 10px 0 14px 0;
        font-size: 9.5pt;
    }
    table.ben-table th {
        background: #0d2d6e;
        color: #fff;
        font-weight: 600;
        padding: 6px 8px;
        text-align: left;
        border: 1px solid #0d2d6e;
    }
    table.ben-table td {
        padding: 6px 8px;
        border: 1px solid #c8d3e8;
        vertical-align: top;
    }
    table.ben-table tr:nth-child(even) td { background: #f5f7fc; }
    .amount-cell { text-align: right; white-space: nowrap; font-weight: 600; }
    /* ── Amount in words ── */
    .amount-words {
        font-style: italic;
        font-size: 9.5pt;
        color: #333;
        margin-bottom: 14px;
    }
    /* ── Narration box ── */
    .narration-box {
        border: 1.5px solid #0d2d6e;
        border-radius: 4px;
        padding: 10px 14px;
        margin: 10px 0 20px 0;
        background: #fffbe6;
    }
    .narration-label {
        font-weight: 700;
        font-size: 9pt;
        color: #0d2d6e;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 4px;
    }
    .narration-ref {
        font-weight: 700;
        color: #b55000;
        font-size: 10.5pt;
    }
    /* ── Signatory blocks ── */
    .signatories {
        display: flex;
        gap: 40px;
        margin-top: 28px;
        page-break-inside: avoid;
    }
    .signatory-block {
        flex: 1;
        border-top: 1.5px solid #0d2d6e;
        padding-top: 8px;
    }
    .sig-img {
        height: 48px;
        margin-bottom: 4px;
        display: block;
    }
    .sig-line {
        border-top: 1px solid #333;
        margin: 28px 0 4px 0;
    }
    .sig-label {
        font-size: 8.5pt;
        color: #555;
        margin-bottom: 2px;
    }
    .sig-name { font-weight: 600; font-size: 10pt; }
    .sig-date-line { margin-top: 12px; }
    /* ── Footer ── */
    .footer {
        border-top: 1px solid #c8d3e8;
        margin-top: 32px;
        padding-top: 8px;
        font-size: 8pt;
        color: #888;
        display: flex;
        justify-content: space-between;
    }
    @media print {
        body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        .page { padding: 0; }
        .signatories { page-break-inside: avoid; }
    }
"""


def generate_letter(request: dict[str, Any], account: dict[str, Any]) -> str:
    """
    Generate a print-optimised A4 HTML bank instruction letter.

    Parameters
    ----------
    request : dict
        Fields used:
            instruction_id   str    — e.g. "PAM-APR-2026-000001"
            entity           str    — "PAM" | "PCL"
            beneficiary_name str
            beneficiary_bank str
            beneficiary_account str
            amount_kobo      int    — amount in kobo
            purpose          str    — free-text purpose / narration
            raised_by        str    — name of submitter (for footer)
            created_at       str|datetime  (ISO format, optional)

    account : dict
        Fields used:
            bank_name        str   — paying bank (e.g. "Providus Bank")
            account_name     str   — paying account name
            account_number   str   — paying account number

    Returns
    -------
    str  — complete HTML document (all CSS inline, no external dependencies).
    """
    instr_id    = request.get("instruction_id", "DRAFT")
    entity_code = request.get("entity", "PAM").upper()
    company     = _entity_name(entity_code)
    created_raw = request.get("created_at")
    letter_date = _format_date(created_raw)

    bank_name    = account.get("bank_name", "")
    acct_name    = account.get("account_name", "")
    acct_number  = account.get("account_number", "")

    ben_name     = request.get("beneficiary_name", "")
    ben_bank     = request.get("beneficiary_bank", "")
    ben_account  = request.get("beneficiary_account", "")
    amount_kobo  = int(request.get("amount_kobo", 0))
    purpose      = request.get("purpose", "")

    amount_fmt   = _fmt_amount(amount_kobo)
    amount_words = amount_in_words(amount_kobo)

    # Signatory images
    def _sig_img_tag(role: str) -> str:
        result = _load_signature_b64(role)
        if result:
            src, _ = result
            return f'<img class="sig-img" src="{src}" alt="{role} signature" />'
        return ""  # graceful skip

    sig1_img = _sig_img_tag("signatory_1")
    sig2_img = _sig_img_tag("signatory_2")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Bank Instruction Letter — {instr_id}</title>
<style>
{_INLINE_CSS}
</style>
</head>
<body>
<div class="page">

  <!-- ── Header ── -->
  <div class="header">
    <div class="company-name">{company}</div>
  </div>

  <div class="letter-title">Bank Instruction Letter</div>

  <div class="ref-block">
    <span class="instruction-ref">{instr_id}</span>
  </div>

  <!-- ── Meta ── -->
  <div class="meta-row">
    <span class="meta-label">Date:</span>
    <span class="meta-value">{letter_date}</span>
  </div>
  <div class="meta-row">
    <span class="meta-label">To:</span>
    <span class="meta-value">{bank_name}</span>
  </div>
  <div class="meta-row">
    <span class="meta-label">From:</span>
    <span class="meta-value">{acct_name}</span>
  </div>

  <!-- ── Body ── -->
  <p class="body-text">
    Please debit account <strong>{acct_number}</strong> and effect
    the following payment:
  </p>

  <!-- ── Beneficiary table ── -->
  <table class="ben-table">
    <thead>
      <tr>
        <th>Beneficiary Name</th>
        <th>Bank</th>
        <th>Account Number</th>
        <th style="text-align:right;">Amount</th>
        <th>Purpose</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>{ben_name}</td>
        <td>{ben_bank}</td>
        <td>{ben_account}</td>
        <td class="amount-cell">{amount_fmt}</td>
        <td>{purpose}</td>
      </tr>
    </tbody>
  </table>

  <p class="amount-words">
    Amount in Words: <em>{amount_words}</em>
  </p>

  <!-- ── Narration box ── -->
  <div class="narration-box">
    <div class="narration-label">Bank Narration Instruction</div>
    <p>
      The instruction reference <span class="narration-ref">{instr_id}</span>
      <strong>must appear in the bank narration / payment reference</strong>
      field for reconciliation purposes.  Any payment submitted without this
      reference will be flagged as an exception.
    </p>
  </div>

  <!-- ── Signatories ── -->
  <div class="signatories">

    <div class="signatory-block">
      {sig1_img}
      <div class="sig-line"></div>
      <div class="sig-label">Authorised Signatory</div>
      <div class="sig-name">Name: _______________________________</div>
      <div class="sig-date-line">
        <span class="sig-label">Date: _______________________________</span>
      </div>
    </div>

    <div class="signatory-block">
      {sig2_img}
      <div class="sig-line"></div>
      <div class="sig-label">Authorised Signatory</div>
      <div class="sig-name">Name: _______________________________</div>
      <div class="sig-date-line">
        <span class="sig-label">Date: _______________________________</span>
      </div>
    </div>

  </div>

  <!-- ── Footer ── -->
  <div class="footer">
    <span>{company}</span>
    <span>Ref: {instr_id}</span>
    <span>Generated: {letter_date}</span>
  </div>

</div>
</body>
</html>"""

    return html
