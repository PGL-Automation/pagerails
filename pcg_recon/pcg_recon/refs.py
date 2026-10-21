"""Reference extraction from Nigerian bank narrations and ledger descriptions.

Strong tokens (used for exact matching in pass P1):
  NIP:<session id>   NIBSS Instant Payment session IDs (30 digits; 35-37 seen on Providus)
  CHQ:<number>       cheque numbers, zero-stripped
  REF:<code>         alphanumeric bank/ledger references (FT..., TRF..., PAM-SUB-000123 ...)
Weak tokens (similarity boost only):
  ACCT:<nuban>       10-digit NUBAN counterparty account numbers
"""
import re

_NIP = re.compile(r"(?<!\d)(\d{28,38})(?!\d)")   # NIBSS session IDs: 30 digits; some banks print 35-37
_CHQ = re.compile(r"\b(?:CHQ|CHEQUE|CHK|CLG\s*CHQ|CHQ\s*NO|CHEQUE\s*NO)[\s.:#-]*(?:NO[\s.:#-]*)?(\d{4,10})\b", re.I)
_NUBAN = re.compile(r"(?<!\d)(\d{10})(?!\d)")
_EXPLICIT = re.compile(r"\b(?:REF|REFERENCE|RRN|TXN\s*ID)[\s.:#-]*([A-Z0-9-/]{5,})\b", re.I)

_PERIOD = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC|Q[1-4]|FY|H[12])[-.]?\d{2,4}$")
# Words that look like codes but carry no identity
_NOISE = {"VAT", "EMTL", "SMS", "COT", "NIP", "TRF", "FT", "USSD", "POS", "ATM", "WEB"}


def extract_refs(*texts: str) -> set:
    out: set = set()
    for t in texts:
        if not t:
            continue
        s = str(t).upper()
        for m in _NIP.findall(s):
            out.add(f"NIP:{m}")
        for m in _CHQ.findall(s):
            out.add(f"CHQ:{int(m)}")
        for m in _EXPLICIT.findall(s):
            out.add(f"REF:{m.strip('-/')}")
        for tok in re.split(r"[\s/|,;:()]+", s):
            tok = tok.strip("-.#")
            if len(tok) < 6 or tok in _NOISE or tok.isdigit() or not re.search(r"\d", tok) \
                    or not re.search(r"[A-Z]", tok) or len(tok) > 32 or _PERIOD.match(tok):
                continue
            out.add(f"REF:{tok}")
        scrubbed = _NIP.sub(" ", s)
        for m in _NUBAN.findall(scrubbed):
            out.add(f"ACCT:{m}")
    return out


def strong(refs: set) -> set:
    return {r for r in refs if not r.startswith("ACCT:")}


_WS = re.compile(r"[^A-Z0-9 ]+")


def clean_text(s: str) -> str:
    s = _WS.sub(" ", (s or "").upper())
    s = re.sub(r"\d{6,}", " ", s)   # long numbers are noise for text similarity
    return re.sub(r"\s+", " ", s).strip()
