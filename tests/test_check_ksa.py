"""Run: python3 -I -m unittest discover -s tests (from the plugin root)."""
import csv
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine" / "check_ksa.py"
SELLER = {"seller_name": "Seller Co", "seller_vat": "300000000000003", "seller_id": "1010010000", "seller_id_scheme": "CRN",
          "seller_street": "King Fahd Road", "seller_building_number": "1234", "seller_postal_code": "12345",
          "seller_city": "Riyadh", "seller_district": "Al Olaya", "seller_country": "SA"}
BUYER = {"buyer_name": "Buyer Co", "buyer_vat": "311111111111113", "buyer_street": "Prince Sultan Street",
         "buyer_building_number": "2345", "buyer_postal_code": "23456", "buyer_city": "Jeddah",
         "buyer_district": "Al Rawdah", "buyer_country": "SA"}
CLEAN = {"invoice_number": "INV-1", "issue_date": "2026-10-01", "issue_time": "09:15:00", "type_code": "388",
         "transaction_code": "0100000", "currency": "SAR", "supply_date": "2026-10-01", **SELLER, **BUYER,
         "line_id": "1", "item_name": "Day", "quantity": "2", "unit_code": "DAY", "unit_price": "100",
         "line_net": "200", "vat_category": "S", "vat_rate": "15", "line_vat": "30"}
SIMPLIFIED = {**{k: v for k, v in CLEAN.items() if not k.startswith("buyer_")}, "transaction_code": "0200000"}
EXPORT = {**CLEAN, "transaction_code": "0100100", "buyer_vat": "", "buyer_id": "C123", "buyer_id_scheme": "OTH",
          "buyer_country": "GB", "buyer_building_number": "", "buyer_postal_code": "", "buyer_district": "",
          "vat_category": "Z", "vat_rate": "0", "line_vat": "0", "exemption_reason": "VATEX-SA-32"}
NOTE = {**CLEAN, "type_code": "381", "preceding_invoice": "INV-0", "note_reason": "Goods returned"}


def run(rows=None, text=None, args=()):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as fh:
        if text is not None:
            fh.write(text)
        else:
            keys = sorted({k: 1 for r in rows for k in r})
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    p = subprocess.run([sys.executable, "-I", str(ENGINE), fh.name, *args], capture_output=True, text=True)
    out = p.stdout if "--summary" in args else (json.loads(p.stdout) if p.stdout.strip() else None)
    return p.returncode, out


def rules_of(rows):
    code, out = run(rows, args=("--all",))
    return sorted({g["rule"]: 1 for g in out["gaps"]}) if out else [f"exit-{code}"]


def rules(base=CLEAN, **change):
    return rules_of([{**base, **change}])


class Clean(unittest.TestCase):
    def test_clean_rows_pass(self):
        self.assertEqual(rules(), [])
        self.assertEqual(rules(SIMPLIFIED), [])
        self.assertEqual(rules(SIMPLIFIED, line_vat=""), [])  # line VAT is optional on simplified invoices
        self.assertEqual(rules(EXPORT), [])
        self.assertEqual(rules(NOTE), [])
        self.assertEqual(rules(NOTE, type_code="383"), [])

    def test_sample_file(self):
        code, out = run(text=(ROOT / "samples" / "ksa-sample.csv").read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertEqual(out["invoices"], 6)
        self.assertEqual(out["invoices_with_gaps"], 3)
        self.assertEqual(out["coverage"]["not_in_sample"], [])
        self.assertEqual(out["phase2_columns_missing"], ["uuid", "invoice_counter", "previous_invoice_hash"])


class Required(unittest.TestCase):
    def test_required_fields(self):
        for field, rule in (("invoice_number", "BR-02"), ("issue_date", "BR-03"), ("type_code", "BR-04"),
                            ("currency", "BR-05"), ("seller_name", "BR-06"), ("line_id", "BR-21"),
                            ("quantity", "BR-22"), ("line_net", "BR-24"), ("item_name", "BR-25"),
                            ("unit_price", "BR-26"), ("vat_category", "BR-CO-04"), ("issue_time", "BR-KSA-70"),
                            ("transaction_code", "BR-KSA-06"), ("seller_vat", "BR-KSA-39")):
            with self.subTest(field=field):
                self.assertIn(rule, rules(**{field: ""}))
                self.assertNotIn(rule, rules())


class Formats(unittest.TestCase):
    def test_number_format(self):
        self.assertIn("csv-number-format", rules(unit_price="1,000"))
        self.assertIn("csv-number-format", rules(vat_rate="15%"))
        self.assertIn("csv-number-format", rules(quantity="NaN"))
        self.assertIn("csv-number-format", rules(quantity="1E999999"))
        self.assertIn("csv-number-format", rules(line_net="٢٠٠"))  # Arabic-Indic digits

    def test_amounts_positive(self):
        self.assertIn("BR-KSA-F-04", rules(NOTE, quantity="-2", line_net="-200", line_vat="-30"))
        self.assertNotIn("BR-KSA-F-04", rules(NOTE))

    def test_two_decimals(self):
        for field, rule, value in (("line_net", "BR-DEC-23", "200.001"), ("line_allowance", "BR-DEC-24", "0.001"),
                                   ("line_charge", "BR-DEC-27", "0.001"), ("line_vat", "BR-KSA-DEC-03", "30.001"),
                                   ("line_amount_with_vat", "BR-KSA-DEC-04", "230.001"),
                                   ("invoice_total_net", "BR-DEC-12", "200.001"),
                                   ("invoice_total_vat", "BR-DEC-13", "30.001"),
                                   ("invoice_total_gross", "BR-DEC-14", "230.001"),
                                   ("invoice_total_vat_sar", "BR-DEC-15", "30.001")):
            with self.subTest(field=field):
                self.assertIn(rule, rules(**{field: value}))
        self.assertEqual(rules(line_amount_with_vat="230.00", invoice_total_net="200.00", invoice_total_vat="30.00",
                               invoice_total_gross="230.00"), [])

    def test_character_limits(self):
        self.assertIn("BR-KSA-F-06", rules(invoice_number="X" * 128))
        self.assertIn("BR-KSA-F-06", rules(line_id="1234567"))
        self.assertNotIn("BR-KSA-F-06", rules(invoice_number="X" * 127, line_id="999999"))


class Dates(unittest.TestCase):
    def test_date_format(self):
        self.assertIn("BR-KSA-F-01", rules(issue_date="01/10/2026"))
        self.assertIn("BR-KSA-F-01", rules(supply_date="2026-02-30"))
        self.assertIn("BR-KSA-F-01", rules(supply_end_date="2026-10"))

    def test_issue_date_not_in_future(self):
        self.assertIn("BR-KSA-04", rules(issue_date="2999-01-01", supply_date="2999-01-01"))
        self.assertNotIn("BR-KSA-04", rules())

    def test_issue_time(self):
        self.assertIn("BR-KSA-70", rules(issue_time="9:15"))
        self.assertIn("BR-KSA-70", rules(issue_time="24:00:00"))
        self.assertNotIn("BR-KSA-70", rules(issue_time="06:15:00Z"))

    def test_supply_period(self):
        self.assertIn("BR-KSA-35", rules(supply_date="", supply_end_date="2026-10-31"))
        self.assertIn("BR-KSA-36", rules(supply_end_date="2026-09-30"))
        self.assertEqual(rules(supply_end_date="2026-10-31"), [])


class TypesAndTransactionCodes(unittest.TestCase):
    def test_type_code(self):
        self.assertIn("BR-KSA-05", rules(type_code="380"))
        self.assertNotIn("BR-KSA-05", rules(type_code="386"))

    def test_transaction_code_shape(self):
        self.assertIn("BR-KSA-06", rules(transaction_code="100000"))  # Excel dropped the leading zero
        self.assertIn("BR-KSA-06", rules(transaction_code="0300000"))
        self.assertIn("BR-KSA-06", rules(transaction_code="0100200"))

    def test_export_not_self_billed(self):
        self.assertIn("BR-KSA-07", rules(EXPORT, transaction_code="0100101"))
        self.assertNotIn("BR-KSA-07", rules(transaction_code="0100001"))

    def test_simplified_flags(self):
        self.assertIn("BR-KSA-31", rules(SIMPLIFIED, transaction_code="0200100"))
        self.assertIn("BR-KSA-31", rules(SIMPLIFIED, transaction_code="0200001"))
        self.assertEqual(rules(SIMPLIFIED, transaction_code="0211000"), [])

    def test_supply_date_on_tax_invoice(self):
        self.assertIn("BR-KSA-15", rules(supply_date=""))
        self.assertNotIn("BR-KSA-15", rules(SIMPLIFIED, supply_date=""))
        self.assertNotIn("BR-KSA-15", rules(NOTE, supply_date=""))

    def test_simplified_summary(self):
        r = rules(SIMPLIFIED, transaction_code="0200010")
        self.assertIn("BR-KSA-71", r)
        self.assertIn("BR-KSA-72", r)
        self.assertEqual(rules(SIMPLIFIED, transaction_code="0200010", buyer_name="Buyer",
                               supply_end_date="2026-10-31"), [])

    def test_credit_and_debit_notes(self):
        for t in ("381", "383"):
            with self.subTest(type_code=t):
                self.assertIn("BR-KSA-56", rules(NOTE, type_code=t, preceding_invoice=""))
                self.assertIn("BR-KSA-17", rules(NOTE, type_code=t, note_reason=""))
        self.assertNotIn("BR-KSA-56", rules(preceding_invoice=""))


class Currency(unittest.TestCase):
    def test_currency_code(self):
        self.assertIn("BR-CL-04", rules(currency="sar"))
        self.assertIn("BR-CL-04", rules(currency="Riyal"))

    def test_tax_currency(self):
        self.assertIn("BR-KSA-EN16931-02", rules(tax_currency="USD"))
        self.assertEqual(rules(tax_currency="SAR"), [])

    def test_total_vat_in_sar(self):
        self.assertIn("BR-53", rules(currency="USD"))
        self.assertEqual(rules(currency="USD", invoice_total_vat_sar="112.50"), [])


class Seller(unittest.TestCase):
    def test_vat_number(self):
        for bad in ("30000000000003", "300000000000004", "100000000000003", "3" + "٠" * 13 + "3"):
            with self.subTest(vat=bad):
                self.assertIn("BR-KSA-40", rules(seller_vat=bad))

    def test_seller_id(self):
        self.assertIn("BR-KSA-08", rules(seller_id=""))
        self.assertIn("BR-KSA-08", rules(seller_id_scheme="NAT"))
        self.assertIn("BR-KSA-08", rules(seller_id="1010-01"))
        self.assertNotIn("BR-KSA-08", rules(seller_id_scheme="700"))

    def test_address(self):
        for f in ("seller_street", "seller_building_number", "seller_postal_code", "seller_city", "seller_district",
                  "seller_country"):
            with self.subTest(field=f):
                self.assertIn("BR-KSA-09", rules(**{f: ""}))
        self.assertIn("BR-KSA-37", rules(seller_building_number="123"))
        self.assertIn("BR-KSA-37", rules(seller_building_number="12A4"))
        self.assertIn("BR-KSA-66", rules(seller_postal_code="1234"))
        self.assertIn("BR-CL-14", rules(seller_country="Saudi Arabia"))


class Buyer(unittest.TestCase):
    def test_tax_invoice_buyer(self):
        self.assertIn("BR-KSA-42", rules(buyer_name=""))
        self.assertNotIn("BR-KSA-42", rules(SIMPLIFIED))
        no_sa = {"buyer_country": "AE", "buyer_building_number": "", "buyer_postal_code": "", "buyer_district": ""}
        for f in ("buyer_street", "buyer_city"):
            with self.subTest(field=f):
                self.assertIn("BR-KSA-10", rules(**no_sa, **{f: ""}))
        self.assertIn("BR-KSA-10", rules(buyer_country="", buyer_building_number="", buyer_postal_code="", buyer_district=""))
        self.assertEqual(rules(**no_sa), [])

    def test_buyer_id_when_no_vat_number(self):
        self.assertIn("BR-KSA-81", rules(buyer_vat=""))
        self.assertEqual(rules(buyer_vat="", buyer_id="1012345678", buyer_id_scheme="CRN"), [])
        self.assertNotIn("BR-KSA-81", rules(SIMPLIFIED))

    def test_saudi_buyer_address(self):
        for f in ("buyer_building_number", "buyer_postal_code", "buyer_district"):
            with self.subTest(field=f):
                self.assertIn("BR-KSA-63", rules(**{f: ""}))
        self.assertIn("BR-KSA-67", rules(buyer_postal_code="2345"))
        self.assertNotIn("BR-KSA-63", rules(buyer_country="AE", buyer_district=""))

    def test_buyer_vat(self):
        self.assertIn("BR-KSA-44", rules(buyer_vat="111111111111113"))
        self.assertIn("BR-KSA-46", rules(EXPORT, buyer_vat="311111111111113"))
        self.assertNotIn("BR-KSA-44", rules(EXPORT, buyer_vat="GB123"))

    def test_buyer_id_scheme(self):
        self.assertIn("BR-KSA-14", rules(buyer_id="12345", buyer_id_scheme="XYZ"))
        self.assertIn("BR-KSA-14", rules(buyer_id="12-345", buyer_id_scheme="CRN"))
        self.assertEqual(rules(buyer_id="P1234567", buyer_id_scheme="PAS"), [])


class Vat(unittest.TestCase):
    def test_categories(self):
        self.assertIn("BR-KSA-18", rules(vat_category="AE"))
        self.assertIn("BR-KSA-18", rules(vat_category="s"))

    def test_rate_range(self):
        self.assertIn("BR-KSA-DEC-02", rules(vat_rate="150", line_vat="300"))
        self.assertIn("BR-KSA-DEC-02", rules(vat_rate="15.001"))
        self.assertNotIn("BR-KSA-DEC-02", rules(vat_rate="15.00"))

    def test_rate_needed(self):
        self.assertIn("BR-48", rules(vat_rate=""))
        self.assertIn("BR-48", rules(EXPORT, vat_rate=""))
        self.assertNotIn("BR-48", rules(vat_category="O", vat_rate="", line_vat="0", exemption_reason="VATEX-SA-OOS"))

    def test_zero_rates(self):
        self.assertIn("BR-Z-05", rules(EXPORT, vat_rate="5"))
        self.assertIn("BR-E-05", rules(vat_category="E", vat_rate="15", exemption_reason="VATEX-SA-29"))
        self.assertIn("BR-KSA-11", rules(vat_category="O", vat_rate="15", exemption_reason="VATEX-SA-OOS"))
        self.assertEqual(rules(vat_category="E", vat_rate="0", line_vat="0", exemption_reason="VATEX-SA-29-7"), [])

    def test_exemption_reasons(self):
        self.assertIn("BR-S-10", rules(exemption_reason="VATEX-SA-29"))
        self.assertIn("BR-KSA-23", rules(vat_category="E", vat_rate="0", line_vat="0"))
        self.assertIn("BR-KSA-69", rules(EXPORT, exemption_reason=""))
        self.assertIn("BR-KSA-24", rules(vat_category="O", vat_rate="", line_vat="0"))
        self.assertIn("BR-KSA-CL-04", rules(EXPORT, exemption_reason="VATEX-SA-29"))
        self.assertIn("BR-KSA-CL-04", rules(vat_category="E", vat_rate="0", line_vat="0", exemption_reason="vatex-sa-30"))

    def test_citizen_education_and_health(self):
        z = {"vat_category": "Z", "vat_rate": "0", "line_vat": "0", "exemption_reason": "VATEX-SA-EDU"}
        self.assertIn("BR-KSA-49", rules(**z))
        self.assertIn("BR-KSA-49", rules(**z, buyer_id="1234567890", buyer_id_scheme="IQA"))
        self.assertEqual(rules(**z, buyer_id="1234567890", buyer_id_scheme="NAT"), [])
        simple = {**z, "exemption_reason": "VATEX-SA-HEA", "buyer_id": "1234567890", "buyer_id_scheme": "NAT"}
        self.assertIn("BR-KSA-25", rules(SIMPLIFIED, **simple))
        self.assertEqual(rules(SIMPLIFIED, **simple, buyer_name="Patient"), [])

    def test_line_vat_on_tax_invoices(self):
        self.assertIn("BR-KSA-52", rules(line_vat=""))
        self.assertNotIn("BR-KSA-52", rules(SIMPLIFIED, line_vat=""))

    def test_line_amount_with_vat(self):
        self.assertIn("BR-KSA-51", rules(line_amount_with_vat="229"))
        self.assertEqual(rules(line_amount_with_vat="230"), [])

    def test_vat_breakdown(self):
        self.assertIn("BR-S-09", rules(line_vat="10"))
        self.assertIn("BR-Z-09", rules(EXPORT, line_vat="5"))
        self.assertIn("BR-E-09", rules(vat_category="E", vat_rate="0", line_vat="5", exemption_reason="VATEX-SA-30"))
        self.assertIn("BR-O-09", rules(vat_category="O", vat_rate="", line_vat="5", exemption_reason="VATEX-SA-OOS"))
        # Two lines of 0.03 at 15%: each line rounds to 0.00, the breakdown to 0.01; within rounding.
        two = [{**CLEAN, "line_id": str(n), "quantity": "1", "unit_price": "0.03", "line_net": "0.03", "line_vat": "0.00"}
               for n in (1, 2)]
        self.assertEqual(rules_of(two), [])
        self.assertIn("BR-S-09", rules_of([{**two[0], "line_vat": "0.05"}, two[1]]))


class LineMaths(unittest.TestCase):
    def test_line_net(self):
        self.assertIn("BR-KSA-EN16931-11", rules(line_net="250", line_vat="37.50"))
        self.assertEqual(rules(line_allowance="20", line_net="180", line_vat="27"), [])
        self.assertEqual(rules(quantity="20", base_quantity="10", line_net="200"), [])

    def test_base_quantity(self):
        self.assertIn("BR-KSA-EN16931-12", rules(base_quantity="0"))

    def test_line_charge_reasons(self):
        charged = {"line_charge": "10", "line_net": "210", "line_vat": "31.50"}
        r = rules(**charged)
        self.assertIn("BR-KSA-20", r)
        self.assertIn("BR-KSA-22", r)
        self.assertEqual(rules(**charged, line_charge_reason_code="FC", line_charge_reason="Freight"), [])


class Totals(unittest.TestCase):
    def test_totals(self):
        self.assertIn("BR-CO-13", rules(invoice_total_net="300"))
        self.assertIn("BR-CO-14", rules(invoice_total_vat="40"))
        self.assertIn("BR-CO-15", rules(invoice_total_gross="250"))
        self.assertEqual(rules(invoice_total_net="200", invoice_total_vat="30", invoice_total_gross="230"), [])

    def test_breakdown_rounds_once_per_group(self):
        lines = [{**CLEAN, "line_id": str(n), "quantity": "1", "unit_price": "0.03", "line_net": "0.03",
                  "line_vat": "0.00", "invoice_total_vat": "0.01"} for n in (1, 2)]
        self.assertEqual(rules_of(lines), [])


class Phase2(unittest.TestCase):
    P2 = {"uuid": "3cf5ee18-ee25-44ea-a444-2c37ba7f28be", "invoice_counter": "46531",
          "previous_invoice_hash": "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="}

    def test_present(self):
        self.assertEqual(rules(**self.P2), [])

    def test_missing_or_malformed(self):
        self.assertIn("BR-KSA-03", rules(**{**self.P2, "uuid": ""}))
        self.assertIn("BR-KSA-03", rules(**{**self.P2, "uuid": "3cf5ee18_ee25"}))
        self.assertIn("BR-KSA-33", rules(**{**self.P2, "invoice_counter": ""}))
        self.assertIn("BR-KSA-34", rules(**{**self.P2, "invoice_counter": "A12"}))
        self.assertIn("BR-KSA-61", rules(**{**self.P2, "previous_invoice_hash": ""}))

    def test_uuid_unique(self):
        two = [{**CLEAN, **self.P2}, {**CLEAN, **self.P2, "invoice_number": "INV-2"}]
        self.assertIn("BR-KSA-03", rules_of(two))

    def test_skipped_when_columns_absent(self):
        code, out = run([CLEAN])
        self.assertEqual(code, 0)
        self.assertEqual(out["phase2_columns_missing"], ["uuid", "invoice_counter", "previous_invoice_hash"])


class Output(unittest.TestCase):
    def test_header_mismatch_reported_once(self):
        rows = [CLEAN, {**CLEAN, "line_id": "2", "seller_vat": "300000000000013"}]
        code, out = run(rows)
        hits = [g for g in out["gaps"] if g["rule"] == "csv-header-mismatch"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["field"], "seller_vat")

    def test_header_gap_once_per_invoice(self):
        rows = [{**CLEAN, "seller_vat": "123"}, {**CLEAN, "line_id": "2", "seller_vat": "123"}]
        code, out = run(rows)
        self.assertEqual(sum(1 for g in out["gaps"] if g["rule"] == "BR-KSA-40"), 1)

    def test_by_rule_and_coverage(self):
        code, out = run([CLEAN, {**SIMPLIFIED, "invoice_number": "INV-2", "seller_vat": "1"}])
        self.assertEqual(code, 1)
        self.assertEqual(out["by_rule"], [{"rule": "BR-KSA-40", "gaps": 1, "invoices": 1}])
        self.assertEqual(out["coverage"]["invoices_by_subtype"], {"01": 1, "02": 1})
        self.assertIn("credit note (381)", out["coverage"]["not_in_sample"])

    def test_warning_simplified_b2b_over_1000(self):
        row = {**SIMPLIFIED, "buyer_vat": "311111111111113", "quantity": "10", "line_net": "1000", "line_vat": "150"}
        code, out = run([row])
        self.assertEqual(code, 0)
        self.assertEqual([w["rule"] for w in out["warnings"]], ["guideline-4.2.1"])
        code, out = run([{**row, "quantity": "9", "line_net": "900", "line_vat": "135"}])
        self.assertEqual(out["warnings"], [])

    def test_mask(self):
        code, out = run([{**CLEAN, "seller_vat": "300000000000004"}], args=("--mask",))
        self.assertEqual(out["gaps"][0]["value"], "***********0004")

    def test_truncation_and_all(self):
        rows = [{**CLEAN, "invoice_number": f"INV-{n}", "seller_vat": "1"} for n in range(60)]
        code, out = run(rows)
        self.assertTrue(out["truncated"])
        self.assertEqual(out["gaps_shown"], 50)
        code, out = run(rows, args=("--all",))
        self.assertFalse(out["truncated"])

    def test_summary(self):
        code, text = run([CLEAN], args=("--summary",))
        self.assertEqual(code, 0)
        self.assertIn("Checked 1 lines in 1 invoices", text)
        self.assertIn("Fatoora portal", text)

    def test_headers_ignore_case_and_cp1256(self):
        keys = list(CLEAN)
        text = ",".join(k.upper() + " " for k in keys) + "\n" + ",".join(CLEAN[k] for k in keys) + "\n"
        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as fh:
            fh.write(text.replace("Buyer Co", "شركة").encode("cp1256"))
        p = subprocess.run([sys.executable, "-I", str(ENGINE), fh.name], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["file_encoding"], "cp1256")


class Exit2(unittest.TestCase):
    def test_unreadable_inputs(self):
        self.assertEqual(run(text="")[0], 2)
        self.assertEqual(run(text="invoice_number,Invoice_Number\nA,B\n")[0], 2)
        self.assertEqual(run(text=",".join(CLEAN) + "\n")[0], 2)
        p = subprocess.run([sys.executable, "-I", str(ENGINE)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        p = subprocess.run([sys.executable, "-I", str(ENGINE), "/nonexistent/file.csv"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)


class Hygiene(unittest.TestCase):
    def test_every_rule_in_the_engine_is_tested_and_documented(self):
        src = ENGINE.read_text(encoding="utf-8")
        tests = Path(__file__).read_text(encoding="utf-8")
        doc = (ROOT / "docs" / "ksa-rules.md").read_text(encoding="utf-8")
        ids = {m: 1 for m in re.findall(r'"((?:BR|csv|guideline)-[A-Za-z0-9.-]+)"', src)}
        ids.update({f"BR-{c}-09": 1 for c in "SZEO"})  # built from a dict in vat_breakdown
        for rule in ids:
            with self.subTest(rule=rule):
                self.assertIn(f'"{rule}"', tests)
                self.assertIn(f"`{rule}`", doc)

    def test_engine_has_no_network_or_urls(self):
        src = ENGINE.read_text(encoding="utf-8")
        for word in ("http", "socket", "urllib", "requests", "set" + "("):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
