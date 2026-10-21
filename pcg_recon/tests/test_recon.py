import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from pcg_recon.cli import main, parse_period
from pcg_recon.ingest.mt940 import read_mt940
from pcg_recon.matcher import Matcher
from pcg_recon.model import Txn, to_minor
from pcg_recon.refs import extract_refs
from pcg_recon.store import Store

ROOT = Path(__file__).resolve().parent.parent
RULES = yaml.safe_load((ROOT / "config/rules.yaml").read_text())


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    import sys
    sys.path.insert(0, str(ROOT / "samples"))
    from generate import write_all
    base = tmp_path_factory.mktemp("w")
    truth = write_all(base / "inputs")
    db, out = str(base / "recon.db"), str(base / "out")
    for per in ("2026-09", "2026-10"):
        rc = main(["--db", db, "run", "--inputs", str(base / "inputs"), "--period", per,
                   "--maker", "A. Preparer", "--out", out])
        assert rc == 0, f"run {per} returned {rc}"
    return base, truth, db, out


# ---------------------------------------------------------------- units
@pytest.mark.parametrize("raw,minor", [("1,234.50", 123450), ("(1,234.50)", -123450), ("1234,5", 123450),
                                       ("-50", -5000), ("₦2,000.00", 200000), ("", 0), (1234.505, 123451)])
def test_to_minor(raw, minor):
    assert to_minor(raw) == minor


def test_refs():
    r = extract_refs("NIP TRF FROM ADA/PAM-SUB-123456/000013260915123456789012345678", "CHQ 000154")
    assert "NIP:000013260915123456789012345678" in r
    assert "REF:PAM-SUB-123456" in r
    assert "CHQ:154" in r


def test_period_parse():
    assert parse_period("2026-09") == (date(2026, 9, 1), date(2026, 9, 30))
    assert parse_period("2026-09-29") == (date(2026, 9, 29), date(2026, 9, 29))


def test_mt940_reversal_marks(tmp_path):
    f = tmp_path / "x.sta"
    f.write_text(":20:X\n:25:1\n:60F:C260901NGN1000,00\n"
                 ":61:2609010901D100,00NTRFNONREF//A1\n:86:TRF OUT\n"
                 ":61:2609020902RD100,00NTRFNONREF//A2\n:86:REVERSAL TRF OUT\n"
                 ":62F:C260902NGN1000,00\n")
    t, m = read_mt940(f, "A")
    assert [x.amount for x in t] == [-10000, 10000]
    assert m.continuity_breaks == []


def _t(side, d, amt, desc="", ref=""):
    x = Txn(side=side, account_id="A", txn_date=date(2026, 9, d), amount=amt, description=desc, reference=ref)
    x.refs = extract_refs(desc, ref)
    return x


def test_ambiguous_aggregate_needs_review_then_decision_applies():
    bank = [_t("BANK", 10, 300_00, "TRF IN X"), _t("BANK", 10, 700_00, "TRF IN Y"),
            _t("BANK", 11, 400_00, "TRF IN Z"), _t("BANK", 11, 600_00, "TRF IN W")]
    book = [_t("BOOK", 10, 1000_00, "Receipt settlement")]
    m = Matcher(bank, book, RULES, 5)
    ms = m.run()
    assert ms and ms[0].status == "PROPOSED"          # 300+700 and 400+600 both fit
    ob, ok = m.open_items()
    assert len(ok) == 1                                # stays open in the statement until reviewed
    m2 = Matcher(bank, book, RULES, 5)
    ms2 = m2.run([{"action": "MANUAL", "bank_uids": [bank[2].uid, bank[3].uid], "book_uids": [book[0].uid],
                   "reviewer": "B"}])
    assert ms2[0].status == "APPROVED" and set(ms2[0].bank_uids) == {bank[2].uid, bank[3].uid}


def test_small_amount_needs_narration():
    m = Matcher([_t("BANK", 30, -300_00, "VAT ON SMS ALERT")], [_t("BOOK", 30, -300_00, "Office tea")], RULES, 5)
    assert m.run()[0].status == "PROPOSED"


# ---------------------------------------------------------------- end to end
def test_balances_equal_truth_and_reconcile(world):
    base, truth, db, out = world
    runs = Store(db).runs()
    assert len(runs) == 10
    for r in runs:
        t = truth[r["account_id"]][r["period_end"][:7]]
        assert r["bank_close"] == t["bank_close"], r["run_id"]
        assert r["book_close"] == t["book_close"], r["run_id"]
        assert r["difference"] == 0


def test_september_open_items_are_exactly_the_true_reconciling_items(world):
    base, truth, db, out = world
    o = pd.read_excel(Path(out) / "recon_pack_2026-09.xlsx", "Open Items")
    book = o[o.Side == "BOOK"]
    assert set(book.Category) == {"DEPOSIT_IN_TRANSIT", "UNPRESENTED_CHEQUE"}
    assert len(book) == 10                                      # 1 DIT + 1 cheque x 5 accounts
    unid = o[o.Category == "UNIDENTIFIED_RECEIPT"]
    assert set(unid.Account) == {"PAM-CLIENT-01", "PAM-MMF-CUST"}  # only the planted unknown credits


def test_october_clears_carried_items(world):
    base, truth, db, out = world
    f = Path(out) / "recon_pack_2026-10.xlsx"
    o = pd.read_excel(f, "Open Items")
    carried = o[o["Carried from"].notna()]
    assert set(carried.Category) == {"UNIDENTIFIED_RECEIPT"}   # only the unknown client credits remain
    assert (o.Side == "BOOK").sum() == 0
    m = pd.read_excel(f, "Matches")
    assert (m.Status == "PROPOSED").sum() == 0
    a = pd.read_excel(f, "Alerts")
    aml = a[a.Code == "AML_UNIDENTIFIED_RECEIPT"]
    assert set(aml.Account) == {"PAM-CLIENT-01", "PAM-MMF-CUST"}


def test_missing_statement_line_is_caught(world, tmp_path):
    base, truth, db, out = world
    inp = tmp_path / "inputs"
    shutil.copytree(base / "inputs", inp)
    f = inp / "PAM-OPS-01" / "bank_2026-09.csv"
    lines = f.read_text().splitlines()
    del lines[12]                                               # silently lose one statement row
    f.write_text("\n".join(lines) + "\n")
    main(["--db", str(tmp_path / "r.db"), "run", "--inputs", str(inp), "--period", "2026-09",
          "--maker", "A", "--out", str(tmp_path / "o"), "--accounts", "PAM-OPS-01"])
    a = pd.read_excel(tmp_path / "o" / "recon_pack_2026-09.xlsx", "Alerts")
    assert "STATEMENT_CONTINUITY" in set(a.Code)


def test_maker_checker_and_audit_chain(world):
    base, truth, db, out = world
    s = Store(db)
    rid = s.runs()[0]["run_id"]
    with pytest.raises(PermissionError):
        s.signoff(rid, "a. preparer")
    s.signoff(rid, "B. Reviewer")
    ok, n = s.verify_audit_chain()
    assert ok and n >= 11


# ---------------------------------------------------------------- Providus-derived cases
S1 = "000023260916151700001229881536"


def test_providus_multi_leg_reversal_and_short_reversal():
    bank = [_t("BANK", 16, -104_556_712_33, f"OUTWARD TRANSFER (N) 1198060 TO STANBIC| X/{S1}"),
            _t("BANK", 16, -50_00, f"COMMISSION 1198060 TO STANBIC| X/{S1}"),
            _t("BANK", 16, -50_00, f"STAMP DUTY 1198060 TO STANBIC| X/{S1}"),
            _t("BANK", 16, -3_75, f"VAT 1198060 TO STANBIC| X/{S1}"),
            _t("BANK", 16, 104_556_712_30, f"REVERSAL OF ENTRY {S1}/TO STANBIC| X"),
            _t("BANK", 16, 53_75, f"REVERSAL OF ENTRY {S1}/TO STANBIC| X"),
            _t("BANK", 16, 50_00, f"REVERSAL OF ENTRY {S1}/TO STANBIC| X")]
    m = Matcher(bank, [], RULES, 3)
    m.p0_reversals()
    auto = [x for x in m.matches if x.status == "AUTO"]
    prop = [x for x in m.matches if x.status == "PROPOSED"]
    assert any("2 legs reversed as one credit" in x.note for x in auto)
    assert len(prop) == 1 and prop[0].difference == -3            # bank refunded 3 kobo short
    assert not m.open_bank


def test_anchored_codes_beat_narration_words():
    from pcg_recon.reconcile import classify
    t = _t("BANK", 3, -9_000_000_00, "OUTWARD TRANSFER (N) To WEMA BANK /X/REFUND OF PENAL CHARGE FEE")
    assert classify(t, RULES)[0] == "UNIDENTIFIED_PAYMENT"          # not REVERSAL, not BANK_CHARGES
    assert classify(_t("BANK", 3, -50_00, "STAMP DUTY 308591 TRZL-TO KEYSTONE| Y|Monthly interest"), RULES)[0] == "EMTL_STAMP_DUTY"
    assert classify(_t("BANK", 3, -5_000_000_00, "ADD A TIME DEPOSIT BY PRODUCT FROM HEAD OFFICE"), RULES)[0] == "TIME_DEPOSIT_PLACED"


def test_monthly_charge_sweep_clears_many_lines_with_one_journal():
    bank = [_t("BANK", d, -50_00, f"STAMP DUTY {d} TO ACCESS| CLIENT {d}") for d in range(1, 29)]
    book = [_t("BOOK", 30, -1_400_00, "Stamp duty on transfers September 2026")]
    for x in bank + book:
        x.origin_period = "2026-09-30"
    m = Matcher(bank, book, RULES, 3, current_period="2026-09-30")
    ms = m.run()
    assert len(ms) == 1 and ms[0].rule == "P5_CHARGE_SWEEP" and ms[0].status == "AUTO" and len(ms[0].bank_uids) == 28
