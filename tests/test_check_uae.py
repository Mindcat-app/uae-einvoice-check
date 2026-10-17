"""Run: python3 -I -m unittest discover -s tests (from the plugin root)."""
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine" / "check_uae.py"
CLEAN = {"invoice_number": "INV-1", "issue_date": "2026-10-01", "type_code": "380", "currency": "AED",
         "seller_trn": "100000000000003", "seller_name": "Seller LLC", "seller_country": "AE", "seller_emirate": "DXB",
         "buyer_name": "Buyer LLC", "buyer_trn": "100000000000103", "buyer_country": "AE", "buyer_emirate": "AUH",
         "line_id": "1", "item_name": "Day", "item_kind": "service", "sac_code": "998311", "quantity": "2", "unit_code": "DAY",
         "unit_price": "100", "line_net": "200", "vat_category": "S", "vat_rate": "5", "line_vat": "10"}


def run(rows=None, text=None, args=()):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as fh:
        if text is not None:
            fh.write(text)
        else:
            keys = sorted({k for r in rows for k in r})
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    p = subprocess.run([sys.executable, "-I", str(ENGINE), fh.name, *args], capture_output=True, text=True)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None)


def rules(**change):
    code, out = run([{**CLEAN, **change}])
    return sorted({g["rule"]: 1 for g in out["gaps"]}) if out else [f"exit-{code}"]


class CheckUae(unittest.TestCase):
    def test_clean_line_passes(self):
        self.assertEqual(rules(), [])

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

    def test_type_codes(self):
        self.assertIn("ibr-cl-01", rules(type_code="389"))
        self.assertIn("ibr-122-ae", rules(type_code="480"))
        self.assertIn("ibr-055-ae", rules(type_code="381"))
        self.assertNotIn("ibr-055-ae", rules(type_code="381", preceding_invoice="INV-0"))
        self.assertIn("ibr-158-ae", rules(type_code="381", preceding_invoice="INV-0"))
        self.assertEqual(rules(type_code="381", preceding_invoice="INV-0", credit_reason="DL8.61.1.A"), [])
        self.assertIn("ibr-001-ae", rules(type_code="381", preceding_invoice="INV-0", credit_reason="refund"))

    def test_discount_and_base_quantity(self):
        self.assertEqual(rules(line_allowance="20", line_net="180", line_vat="9"), [])
        self.assertEqual(rules(quantity="20", unit_price="100", base_quantity="10", line_net="200"), [])
        self.assertIn("mc-base-quantity", rules(base_quantity="0"))

    def test_categories(self):
        self.assertIn("ibr-167-ae", rules(vat_category="E", vat_rate="", line_vat=""))
        self.assertEqual(rules(vat_category="E", vat_rate="", line_vat="", exemption_reason="VATEX-AE-EXEMPT"), [])
        self.assertIn("aligned-ibrp-o-05", rules(vat_category="O", vat_rate="0", line_vat=""))
        self.assertEqual(rules(vat_category="O", vat_rate="", line_vat=""), [])
        self.assertIn("ibr-111-ae", rules(vat_category="N", vat_rate="0", line_vat="0"))
        self.assertIn("ibr-139-ae", rules(vat_category="s"))

    def test_reverse_charge(self):
        # PINT AE 1.0.4: aligned-ibrp-ae-05-ae only requires a line rate; the official AE example uses 5.
        self.assertEqual(rules(vat_category="AE", vat_rate="5", line_vat="0"), [])
        self.assertIn("ibr-103-ae", rules(vat_category="AE", vat_rate="5", line_vat="0", buyer_trn=""))
        self.assertIn("aligned-ibrp-ae-05-ae", rules(vat_category="AE", vat_rate="", line_vat="0"))

    def test_foreign_buyer_not_held_to_uae_rules(self):
        self.assertEqual(rules(buyer_country="GB", buyer_trn="GB123456789", buyer_emirate="London"), [])

    def test_foreign_currency(self):
        r = rules(currency="USD")
        self.assertIn("ibr-159-ae", r)
        self.assertIn("ibr-104-ae", r)
        self.assertEqual(rules(currency="USD", exchange_rate="3.6725", line_net_aed="734.50"), [])
        self.assertIn("mc-aed-maths", rules(currency="USD", exchange_rate="3.6725", line_net_aed="200"))

    def test_issue_date(self):
        for bad in ("01/10/2026", "2026-02-30", "2026-1-5", "20261001"):
            self.assertIn("mc-date-format", rules(issue_date=bad))

    def test_unit_code(self):
        self.assertIn("ibr-023", rules(unit_code=""))
        self.assertIn("ibr-cl-23", rules(unit_code="day"))
        self.assertIn("ibr-cl-23", rules(unit_code="hours"))
        self.assertEqual(rules(unit_code="HUR"), [])

    def test_item_codes(self):
        self.assertIn("ibr-184-ae", rules(item_kind="goods", sac_code=""))
        self.assertIn("ibr-185-ae", rules(sac_code=""))
        self.assertIn("ibr-186-ae", rules(item_kind="both"))

    def test_bad_base_quantity_is_reported_not_crashed(self):
        code, out = run([{**CLEAN, "base_quantity": "1x"}])
        self.assertEqual(code, 1)
        self.assertIn("mc-number-format", [g["rule"] for g in out["gaps"]])

    def test_header_gaps_once_per_invoice(self):
        code, out = run([{**CLEAN, "line_id": str(i), "seller_trn": "1"} for i in range(1, 11)])
        self.assertEqual([g["rule"] for g in out["gaps"]].count("ibr-132-ae"), 1)

    def test_lines_that_disagree_on_header(self):
        code, out = run([CLEAN, {**CLEAN, "line_id": "2", "currency": "USD", "exchange_rate": "3.6725", "line_net_aed": "734.50"}])
        self.assertIn(("currency", "mc-header-mismatch"), [(g["field"], g["rule"]) for g in out["gaps"]])
        # Two different invoices that share one number
        code, out = run([CLEAN, {**CLEAN, "seller_name": "Other LLC", "issue_date": "2026-10-05"}])
        self.assertEqual(sorted(g["field"] for g in out["gaps"] if g["rule"] == "mc-header-mismatch"), ["issue_date", "seller_name"])
        # Same value written differently is not a mismatch
        usd = {**CLEAN, "currency": "USD", "exchange_rate": "3.6725", "line_net_aed": "734.50"}
        code, out = run([usd, {**usd, "line_id": "2", "currency": "usd", "exchange_rate": "3.67250"}])
        self.assertEqual(code, 0)

    def test_coverage_and_warnings(self):
        code, out = run([CLEAN, {**CLEAN, "invoice_number": "INV-2", "buyer_trn": ""}])
        self.assertEqual(code, 0)
        c = out["coverage"]
        self.assertEqual((c["invoices_by_type_code"], c["lines_by_vat_category"], c["invoices_by_currency"]),
                         ({"380": 2}, {"S": 2}, {"AED": 2}))
        self.assertEqual(c["not_in_sample"], ["credit note (381 or 81)", "zero-rated (Z)", "exempt (E)", "reverse charge (AE)", "non-AED currency"])
        self.assertEqual([(w["invoice"], w["rule"]) for w in out["warnings"]], [("INV-2", "mc-buyer-trn-blank")])

    def test_empty_and_header_only_files_fail_loudly(self):
        self.assertEqual(run(text="")[0], 2)
        self.assertEqual(run(text="invoice_number,line_id\n")[0], 2)

    def test_duplicate_headers_fail_loudly(self):
        self.assertEqual(run(text="Invoice_Number,invoice_number\nINV-1,INV-2\n")[0], 2)

    def test_blank_header_cells_are_ignored(self):
        keys = list(CLEAN)
        text = ",".join(keys) + ",,\n" + ",".join(CLEAN[k] for k in keys) + ",,\n"
        self.assertEqual(run(text=text)[0], 0)

    def test_coverage_credit_and_blank_currency(self):
        code, out = run([{**CLEAN, "currency": ""}, {**CLEAN, "invoice_number": "CN-1", "type_code": "81",
                                                     "vat_category": "Z", "vat_rate": "0", "line_vat": "0", "preceding_invoice": "INV-1"}])
        missing = out["coverage"]["not_in_sample"]
        self.assertIn("non-AED currency", missing)
        self.assertNotIn("credit note (381 or 81)", missing)

    def test_headers_are_normalised(self):
        code, out = run(text="Invoice_Number , LINE_ID\nINV-1,1\n")
        self.assertNotIn("invoice_number", {g["field"] for g in out["gaps"]})

    def test_truncation_is_flagged(self):
        code, out = run([{**CLEAN, "invoice_number": f"I{i}", "seller_trn": "1"} for i in range(60)])
        self.assertTrue(out["truncated"])
        self.assertGreater(out["gaps_total"], out["gaps_shown"])

    def test_sample_file(self):
        p = subprocess.run([sys.executable, "-I", str(ENGINE), str(ROOT / "samples" / "uae-sample.csv")], capture_output=True, text=True)
        out = json.loads(p.stdout)
        self.assertEqual((out["invoices"], out["invoices_with_gaps"]), (4, 2))


if __name__ == "__main__":
    unittest.main()
