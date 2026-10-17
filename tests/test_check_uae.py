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
         "transaction_type": "00000000", "seller_endpoint_scheme": "0235", "seller_endpoint": "1000000000",
         "buyer_endpoint_scheme": "0235", "buyer_endpoint": "1000000001",
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

    def test_invoice_totals(self):
        two = [CLEAN, {**CLEAN, "line_id": "2"}]
        ok = {"invoice_total_net": "400", "invoice_total_vat": "20", "invoice_total_gross": "420"}
        self.assertEqual(run([{**r, **ok} for r in two])[0], 0)
        bad = {"invoice_total_net": "399", "invoice_total_vat": "21", "invoice_total_gross": "421"}
        code, out = run([{**r, **bad} for r in two])
        self.assertEqual(sorted(g["rule"] for g in out["gaps"]), ["mc-total-gross", "mc-total-net", "mc-total-vat"])
        self.assertEqual(run(two)[0], 0)  # no total columns, no check

    def test_mask(self):
        code, out = run([CLEAN, {**CLEAN, "line_id": "2", "seller_trn": "12345678901203"}], args=["--mask"])
        values = [g["value"] for g in out["gaps"] if g["field"] == "seller_trn"]
        self.assertTrue(values)
        self.assertFalse(any("123456789" in v for v in values))
        code, out = run([{**CLEAN, "seller_trn": "10000000002003"}], args=["--mask"])
        self.assertIn("**********2003", [g["value"] for g in out["gaps"]])

    def test_summary(self):
        p = subprocess.run([sys.executable, "-I", str(ENGINE), str(ROOT / "samples" / "uae-sample.csv"), "--summary"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("Invoices with gaps: 2 of 4", p.stdout)
        self.assertIn("ibr-132-ae", p.stdout)
        self.assertEqual(p.stdout.strip().splitlines()[-1], "Help getting ready: mindcat.ai/contact")

    def test_totals_with_blank_line_vat(self):
        totals = {"invoice_total_net": "200", "invoice_total_vat": "10", "invoice_total_gross": "210"}
        self.assertEqual(rules(line_vat="", **totals), [])  # unknown line VAT: no total check, not a false gap
        exempt = {**CLEAN, "line_id": "2", "vat_category": "E", "vat_rate": "", "line_vat": "", "exemption_reason": "VATEX-AE-EXEMPT"}
        both = {**totals, "invoice_total_net": "400", "invoice_total_gross": "410"}
        code, out = run([{**CLEAN, **both}, {**exempt, **both}])
        self.assertEqual(code, 0, out)

    def test_header_cells_filled_on_first_line_only(self):
        blank = {f: "" for f in ("issue_date", "type_code", "currency", "seller_name", "seller_trn", "seller_country",
                                 "seller_emirate", "buyer_name", "buyer_trn", "transaction_type", "seller_endpoint",
                                 "seller_endpoint_scheme", "buyer_endpoint", "buyer_endpoint_scheme")}
        code, out = run([CLEAN, {**CLEAN, "line_id": "2", **blank}])
        self.assertEqual((code, out["gaps"]), (0, []))

    def test_bad_allowance_is_one_gap(self):
        self.assertEqual(rules(line_allowance="2O", line_net="180", line_vat="9"), ["mc-number-format"])

    def test_western_and_arabic_windows_files(self):
        header = ",".join(CLEAN) + "\n"
        for name, enc in (("Muñoz García", "cp1252"), ("شركة النور", "cp1256")):
            data = (header + ",".join({**CLEAN, "buyer_name": name}.values()) + "\n").encode(enc)
            with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as fh:
                fh.write(data)
            p = subprocess.run([sys.executable, "-I", str(ENGINE), fh.name], capture_output=True, text=True)
            self.assertEqual((p.returncode, json.loads(p.stdout)["file_encoding"]), (0, enc))
        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as fh:
            fh.write(b"\xef\xbb\xbf" + (header + ",".join(CLEAN.values()) + "\n").encode("utf-8"))
        p = subprocess.run([sys.executable, "-I", str(ENGINE), fh.name], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)

    def test_transaction_type(self):
        self.assertIn("ibr-154-ae", rules(transaction_type=""))
        self.assertIn("ibr-154-ae", rules(transaction_type="0"))  # Excel turned 00000000 into a number
        self.assertIn("ibr-154-ae", rules(transaction_type="0000000X"))
        out_of_scope = {"type_code": "480", "vat_category": "O", "vat_rate": "", "line_vat": "", "seller_trn": ""}
        self.assertIn("ibr-157-ae", rules(transaction_type="01000000", **out_of_scope))
        self.assertNotIn("ibr-157-ae", rules(transaction_type="00000001", **out_of_scope))

    def test_endpoints(self):
        self.assertIn("ibr-081", rules(seller_endpoint=""))
        self.assertIn("ibr-080", rules(buyer_endpoint=""))
        self.assertIn("ibr-062", rules(seller_endpoint_scheme=""))
        self.assertIn("ibr-063", rules(buyer_endpoint_scheme=""))
        self.assertIn("ibr-cl-25", rules(buyer_endpoint_scheme="235"))

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

    def test_missing_column_reported_once_per_file(self):
        absent = ("transaction_type", "seller_endpoint", "buyer_endpoint")
        base = {k: v for k, v in CLEAN.items() if k not in absent}
        code, out = run([{**base, "invoice_number": f"I{i}"} for i in range(5)])
        self.assertEqual(code, 1)
        self.assertEqual(sorted((g["invoice"], g["field"], g["rule"]) for g in out["gaps"]),
                         [("(all)", "buyer_endpoint", "ibr-080"), ("(all)", "seller_endpoint", "ibr-081"),
                          ("(all)", "transaction_type", "ibr-154-ae")])
        self.assertTrue(all(g["fix"].startswith("column missing from the file") for g in out["gaps"]))
        self.assertEqual({(b["gaps"], b["invoices"]) for b in out["by_rule"]}, {(1, 5)})
        self.assertEqual(out["invoices_with_gaps"], 5)
        # A blank cell in a column the file has is still reported per invoice
        code, out = run([{**CLEAN, "invoice_number": f"I{i}", "transaction_type": ""} for i in range(5)])
        self.assertEqual(sorted(g["invoice"] for g in out["gaps"]), [f"I{i}" for i in range(5)])

    def test_mask_hides_endpoint_ids(self):
        code, out = run([CLEAN, {**CLEAN, "line_id": "2", "seller_endpoint": "1234567890"}], args=("--mask",))
        self.assertIn("seller_endpoint", [g["field"] for g in out["gaps"]])
        self.assertNotIn("1234567890", json.dumps(out))

    def test_utf16_file(self):
        keys = list(CLEAN)
        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as fh:
            fh.write((",".join(keys) + "\n" + ",".join(CLEAN[k] for k in keys) + "\n").encode("utf-16"))
        p = subprocess.run([sys.executable, "-I", str(ENGINE), fh.name], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)["file_encoding"]), (0, "utf-16"))

    def test_rows_of_empty_cells_are_skipped(self):
        keys = list(CLEAN)
        text = ",".join(keys) + "\n" + ",".join(CLEAN[k] for k in keys) + "\n" + "," * (len(keys) - 1) + "\n,, \n"
        code, out = run(text=text)
        self.assertEqual((code, out["lines"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
