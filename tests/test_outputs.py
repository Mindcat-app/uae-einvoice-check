"""Master-data lists, --report, --handoff and option handling. Run: python3 -I -m unittest discover -s tests."""
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine" / "check_uae.py"
SAMPLE = ROOT / "samples" / "uae-sample.csv"


def run(*args):
    p = subprocess.run([sys.executable, "-I", str(ENGINE), *map(str, args)], capture_output=True, text=True)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip().startswith("{") else p.stdout + p.stderr)


def write_csv(folder, name, rows):
    path = os.path.join(folder, name)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path


class Outputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_customers(self):
        good = {"customer_name": "Buyer LLC", "trn": "100000000000103", "tin": "1000000001", "country": "AE", "emirate": "AUH"}
        path = write_csv(self.tmp, "customers.csv", [
            good, {**good, "customer_name": "Bad", "trn": "123", "tin": "99", "emirate": "Abu Dhabi"},
            {**good, "customer_name": "Overseas", "country": "GB", "trn": "GB123", "emirate": ""},
            {**good, "customer_name": "No emirate", "emirate": ""}])
        code, out = run(path, "--master", "customers", "--mask")
        self.assertEqual(code, 1)
        self.assertEqual((out["master"], out["records"], out["records_with_gaps"]), ("customers", 4, 2))
        self.assertEqual(sorted((g["record"], g["rule"]) for g in out["gaps"]),
                         [("Bad", "ibr-128-ae"), ("Bad", "ibr-132-ae"), ("Bad", "mc-tin-format"), ("No emirate", "ibr-128-ae")])
        self.assertNotIn("123", [g["value"] for g in out["gaps"] if g["field"] == "trn"])

    def test_items(self):
        good = {"item_name": "Consulting day", "item_kind": "service", "sac_code": "998311", "hs_code": "",
                "unit_code": "DAY", "vat_category": "S"}
        path = write_csv(self.tmp, "items.csv", [good, {**good, "item_name": "Laptop", "item_kind": "goods", "unit_code": "pcs",
                                                        "vat_category": "s"}])
        code, out = run(path, "--master", "items", "--summary")
        self.assertEqual(code, 1)
        self.assertIn("1 of 2", out)
        code, out = run(path, "--master", "items")
        self.assertEqual(sorted(g["rule"] for g in out["gaps"]), ["ibr-139-ae", "ibr-184-ae", "ibr-cl-23"])

    def test_report_holds_every_gap(self):
        with open(SAMPLE, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        big = [{**rows[1], "invoice_number": f"I{i}"} for i in range(40)]
        report = os.path.join(self.tmp, "gaps.csv")
        code, out = run(write_csv(self.tmp, "big.csv", big), "--report", report, "--mask")
        self.assertTrue(out["truncated"])
        with open(report, encoding="utf-8-sig", newline="") as fh:
            written = list(csv.DictReader(fh))
        self.assertEqual(len(written), out["gaps_total"])
        self.assertEqual(list(written[0])[:6], ["invoice", "line", "field", "value", "rule", "fix"])
        self.assertFalse(any(r["value"] == "10000000000003" for r in written))

    def test_handoff_has_no_customer_data(self):
        folder = os.path.join(self.tmp, "handoff")
        code, out = run(SAMPLE, "--handoff", folder)
        self.assertEqual(code, 1)
        text = "".join(Path(folder, f).read_text(encoding="utf-8") for f in ("field-map.md", "readiness.md"))
        self.assertIn("ibt-031", text)
        self.assertIn("ibr-132-ae", text)
        for private in ("Buyer One", "INV-1002", "10000000000003", "4100"):
            self.assertNotIn(private, text)

    def test_unknown_option_fails(self):
        self.assertEqual(run(SAMPLE, "--masked")[0], 2)
        self.assertEqual(run(SAMPLE, "--ma")[0], 2)  # no abbreviations


if __name__ == "__main__":
    unittest.main()
