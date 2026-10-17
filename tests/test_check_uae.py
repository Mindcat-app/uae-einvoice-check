"""Run: python3 -I -m unittest discover -s tests (from the plugin root)."""
import contextlib
import csv
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine" / "check_uae.py"
SAMPLE = ROOT / "samples" / "uae-sample.csv"
_spec = importlib.util.spec_from_file_location("check_uae", ENGINE)
check_uae = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_uae)

CLEAN = {"invoice_number": "INV-1", "issue_date": "2026-10-01", "type_code": "380", "currency": "AED",
         "seller_trn": "100000000000003", "seller_name": "Seller LLC", "seller_country": "AE", "seller_emirate": "DXB",
         "buyer_name": "Buyer LLC", "buyer_trn": "100000000000103", "buyer_country": "AE", "buyer_emirate": "AUH",
         "line_id": "1", "item_name": "Day", "item_kind": "service", "sac_code": "998311", "unit_code": "DAY",
         "quantity": "2", "unit_price": "100", "line_net": "200", "vat_category": "S", "vat_rate": "5", "line_vat": "10"}


def call(path, args=()):
    """Runs the engine's main in-process. Returns (exit code, stdout text, stderr text)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = check_uae.main(["check_uae.py", str(path), *args])
    return code, out.getvalue(), err.getvalue()


def run(rows=None, text=None, data=None, args=()):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "invoices.csv"
        if data is not None:
            path.write_bytes(data)
        elif text is not None:
            path.write_text(text, encoding="utf-8")
        else:
            keys = list(dict.fromkeys(k for r in rows for k in r))
            with open(path, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=keys)
                w.writeheader()
                w.writerows(rows)
        code, out, _ = call(path, args)
    if "--summary" in args:
        return code, out
    return code, (json.loads(out) if out.strip() else None)


def rule_keys(items):
    return dict.fromkeys(g["rule"] for g in items)


def rules(**change):
    code, out = run([{**CLEAN, **change}])
    return rule_keys(out["gaps"]) if out else {f"exit-{code}": True}


def warns(rows):
    return rule_keys(run(rows)[1]["warnings"])


class CheckUae(unittest.TestCase):
    def test_clean_line_passes(self):
        self.assertEqual(rules(), {})
        self.assertEqual(run([CLEAN])[0], 0)

    def test_trn_format(self):
        self.assertIn("ibr-132-ae", rules(seller_trn="10000000000003"))
        self.assertIn("ibr-132-ae", rules(seller_trn="1" + "٠" * 12 + "03"))  # Arabic-Indic digits

    def test_unreadable_numbers_are_reported_not_skipped(self):
        r = rules(vat_rate="15%", unit_price="1,000", line_net="9,999")
        self.assertIn("mc-number-format", r)
        self.assertIn("ibr-190-ae", r)

    def test_nan_and_overflow_do_not_crash(self):
        self.assertIn("mc-number-format", rules(quantity="NaN"))
        self.assertIn("mc-number-format", rules(quantity="1E999999"))

    def test_bad_base_quantity_is_a_gap_not_a_crash(self):
        for bad in ("1x", "1,000"):
            r = rules(base_quantity=bad)
            self.assertIn("mc-number-format", r)
            self.assertNotIn("ibr-147-ae", r)

    def test_unexpected_error_exits_2(self):
        real = check_uae.check_row
        check_uae.check_row = lambda r: 1 / 0
        try:
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / "x.csv"
                path.write_text("invoice_number\nI1\n", encoding="utf-8")
                code, out, err = call(path)
        finally:
            check_uae.check_row = real
        self.assertEqual(code, 2)
        self.assertIn("unexpected error", err)

    def test_type_codes(self):
        self.assertIn("ibr-cl-01", rules(type_code="389"))
        self.assertIn("ibr-122-ae", rules(type_code="480"))
        self.assertIn("ibr-055-ae", rules(type_code="381", credit_reason="DL"))
        self.assertNotIn("ibr-055-ae", rules(type_code="381", preceding_invoice="INV-0", credit_reason="DL"))
        self.assertNotIn("ibr-055-ae", rules(type_code="381", credit_reason="VD"))

    def test_credit_note_reason_required(self):
        self.assertIn("ibr-158-ae", rules(type_code="381", preceding_invoice="INV-0"))
        self.assertIn("ibr-158-ae", rules(type_code="81", vat_category="Z", vat_rate="0", line_vat="0",
                                          preceding_invoice="INV-0"))
        self.assertNotIn("ibr-158-ae", rules(type_code="381", preceding_invoice="INV-0", credit_reason="VD"))
        self.assertNotIn("ibr-158-ae", rules())

    def test_discount_and_base_quantity(self):
        self.assertEqual(rules(line_allowance="20", line_net="180", line_vat="9"), {})
        self.assertEqual(rules(quantity="20", unit_price="100", base_quantity="10", line_net="200"), {})
        self.assertIn("mc-base-quantity", rules(base_quantity="0"))

    def test_categories(self):
        self.assertIn("ibr-167-ae", rules(vat_category="E", vat_rate="", line_vat=""))
        self.assertEqual(rules(vat_category="E", vat_rate="", line_vat="", exemption_reason="VATEX-AE-EXEMPT"), {})
        self.assertIn("aligned-ibrp-o-05", rules(vat_category="O", vat_rate="0", line_vat=""))
        self.assertEqual(rules(vat_category="O", vat_rate="", line_vat=""), {})
        self.assertIn("ibr-111-ae", rules(vat_category="N", vat_rate="0", line_vat="0"))
        self.assertIn("ibr-139-ae", rules(vat_category="s"))

    def test_reverse_charge(self):
        self.assertEqual(rules(vat_category="AE", vat_rate="0", line_vat="0"), {})
        self.assertIn("aligned-ibrp-ae-05", rules(vat_category="AE", vat_rate="5", line_vat="0"))
        self.assertIn("aligned-ibrp-ae-05", rules(vat_category="AE", vat_rate="", line_vat="0"))
        self.assertIn("mc-reverse-charge-vat", rules(vat_category="AE", vat_rate="0", line_vat="10"))
        self.assertIn("ibr-103-ae", rules(vat_category="AE", vat_rate="0", line_vat="0", buyer_trn=""))

    def test_foreign_buyer_not_held_to_uae_rules(self):
        self.assertEqual(rules(buyer_country="GB", buyer_trn="GB123456789", buyer_emirate="London"), {})

    def test_foreign_currency(self):
        r = rules(currency="USD")
        self.assertIn("ibr-159-ae", r)
        self.assertIn("ibr-104-ae", r)

    def test_fx_maths(self):
        usd = {"currency": "USD", "exchange_rate": "3.6725"}
        self.assertEqual(rules(**usd, line_net_aed="734.50"), {})
        self.assertIn("mc-fx-maths", rules(**usd, line_net_aed="700"))
        # a rate rounded to 4 places is not flagged on a large line
        self.assertEqual(rules(currency="USD", exchange_rate="3.6725", quantity="1000", unit_price="1000",
                               line_net="1000000", line_vat="50000", line_net_aed="3672530"), {})

    def test_issue_date(self):
        for bad in ("01/10/2026", "31/13/2026", "2026-02-30", "2026-1-5", "20261001"):
            self.assertIn("mc-issue-date", rules(issue_date=bad), bad)
        self.assertNotIn("mc-issue-date", rules(issue_date="2028-02-29"))

    def test_blank_domestic_buyer_trn_is_a_warning_not_a_gap(self):
        self.assertEqual(rules(buyer_trn=""), {})
        self.assertIn("mc-buyer-trn-missing", warns([{**CLEAN, "buyer_trn": ""}]))
        self.assertNotIn("mc-buyer-trn-missing", warns([CLEAN]))
        self.assertNotIn("mc-buyer-trn-missing", warns([{**CLEAN, "buyer_trn": "", "buyer_country": "GB"}]))
        self.assertEqual(run([{**CLEAN, "buyer_trn": ""}])[0], 0)

    def test_header_gaps_reported_once_per_invoice(self):
        lines = [{**CLEAN, "line_id": str(i), "seller_trn": "123"} for i in range(1, 4)]
        out = run(lines)[1]
        self.assertEqual([g["rule"] for g in out["gaps"]].count("ibr-132-ae"), 1)
        lines = [{**CLEAN, "line_id": str(i), "buyer_trn": ""} for i in range(1, 4)]
        self.assertEqual(run(lines)[1]["warnings_total"], 1)

    def test_header_mismatch(self):
        lines = [CLEAN, {**CLEAN, "line_id": "2", "buyer_emirate": "DXB"}]
        out = run(lines)[1]
        self.assertIn("mc-header-mismatch", rule_keys(out["gaps"]))
        self.assertNotIn("mc-header-mismatch", rule_keys(run([CLEAN, {**CLEAN, "line_id": "2"}])[1]["gaps"]))

    def test_duplicate_invoice_numbers(self):
        other = {**CLEAN, "seller_trn": "100000000000203", "seller_name": "Other LLC"}
        out = run([CLEAN, other])[1]
        r = rule_keys(out["gaps"])
        self.assertIn("mc-duplicate-invoice", r)
        self.assertNotIn("mc-header-mismatch", r)
        self.assertIn("mc-duplicate-invoice", rule_keys(run([CLEAN, {**CLEAN, "issue_date": "2026-10-09"}])[1]["gaps"]))

    def test_unit_code(self):
        self.assertIn("mc-unit-code", rules(unit_code=""))
        self.assertIn("mc-unit-code", rules(unit_code="each"))
        self.assertIn("mc-unit-code", rules(unit_code="ABCD"))
        self.assertEqual(rules(unit_code="C62"), {})
        no_column = {k: v for k, v in CLEAN.items() if k != "unit_code"}
        code, out = run([no_column, {**no_column, "invoice_number": "INV-2"}])
        self.assertEqual(code, 0)
        self.assertEqual([w["rule"] for w in out["warnings"]].count("mc-unit-code"), 1)

    def test_totals(self):
        two = [{**CLEAN, "invoice_total_net": "400", "invoice_total_vat": "20"},
               {**CLEAN, "line_id": "2", "invoice_total_net": "400", "invoice_total_vat": "20"}]
        self.assertEqual(run(two)[0], 0)
        bad = [{**g, "invoice_total_net": "450"} for g in two]
        self.assertIn("mc-totals", rule_keys(run(bad)[1]["gaps"]))
        self.assertIn("mc-number-format", rules(invoice_total_net="1,000"))

    def test_item_codes_use_official_rules(self):
        self.assertIn("ibr-184-ae", rules(item_kind="goods", sac_code="", hs_code=""))
        self.assertIn("ibr-185-ae", rules(sac_code=""))
        self.assertIn("ibr-186-ae", rules(item_kind="both", hs_code=""))
        self.assertEqual(rules(item_kind="both", hs_code="84713000"), {})

    def test_scenarios(self):
        s = run([CLEAN])[1]["scenarios"]
        self.assertEqual(s["invoices_by_type"], {"invoice": 1, "credit_note": 0, "other": 0})
        self.assertFalse(s["foreign_currency"])
        self.assertIn("credit notes (381 or 81)", s["not_in_sample"])
        self.assertIn("reverse-charge (AE) lines", s["not_in_sample"])
        s = run([{**CLEAN, "vat_category": "AE", "vat_rate": "0", "line_vat": "0"}])[1]["scenarios"]
        self.assertNotIn("reverse-charge (AE) lines", s["not_in_sample"])

    def test_summary_flag(self):
        code, text = run([{**CLEAN, "seller_trn": "1"}], args=("--summary",))
        self.assertEqual(code, 1)
        self.assertIn("ibr-132-ae", text)
        self.assertTrue(text.strip().endswith("(Dubai +971 4 266 2348)."))
        self.assertEqual(run([CLEAN], args=("--summary",))[0], 0)

    def test_mask_flag(self):
        code, out = run([{**CLEAN, "seller_trn": "10000000000099", "buyer_trn": ""}], args=("--mask",))
        g = [g for g in out["gaps"] if g["field"] == "seller_trn"][0]
        self.assertEqual(g["value"], "100*********99")
        self.assertNotIn("10000000000099", json.dumps(out))

    def test_encoding(self):
        utf8 = "invoice_number,buyer_name\nI1,Müller GmbH\n"
        self.assertEqual(run(data=utf8.encode("utf-8"))[1]["file_encoding"], "utf-8-sig")
        self.assertEqual(run(data=utf8.encode("latin-1"))[1]["file_encoding"], "latin-1")
        self.assertEqual(run(data="invoice_number,buyer_name\nI1,CAFÉ\n".encode("latin-1"))[1]["file_encoding"], "latin-1")
        arabic = "invoice_number,buyer_name\nI1,شركة المثال\n".encode("cp1256")
        self.assertEqual(run(data=arabic)[1]["file_encoding"], "cp1256")

    def test_duplicate_headers_fail_loudly(self):
        code, out = run(text="Invoice_Number,invoice_number\nI1,I2\n")
        self.assertEqual((code, out), (2, None))

    def test_empty_and_header_only_files_fail_loudly(self):
        self.assertEqual(run(text="")[0], 2)
        self.assertEqual(run(text="invoice_number,line_id\n")[0], 2)

    def test_headers_are_normalised(self):
        code, out = run(text="Invoice_Number , LINE_ID\nINV-1,1\n")
        self.assertNotIn("invoice_number", {g["field"]: 1 for g in out["gaps"]})

    def test_truncation_is_flagged(self):
        code, out = run([{**CLEAN, "invoice_number": f"I{i}", "seller_trn": "1"} for i in range(60)])
        self.assertTrue(out["truncated"])
        self.assertGreater(out["gaps_total"], out["gaps_shown"])

    def test_sample_file(self):
        code, text, _ = call(SAMPLE)
        out = json.loads(text)
        self.assertEqual((code, out["invoices"], out["invoices_with_gaps"]), (1, 4, 2))
        self.assertEqual(sorted(dict.fromkeys(g["invoice"] for g in out["gaps"])), ["INV-1002", "INV-1003"])


if __name__ == "__main__":
    unittest.main()
