"""Excel and UBL XML inputs. Run: python3 -I -m unittest discover -s tests (from the plugin root)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine" / "check_uae.py"
SAMPLE = ROOT / "samples" / "uae-sample.csv"


def check(path, *args):
    p = subprocess.run([sys.executable, "-I", str(ENGINE), str(path), *args], capture_output=True, text=True)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip().startswith("{") else p.stdout + p.stderr)


def col(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def write_xlsx(path, table, numbers=()):
    """A minimal .xlsx: strings go to shared strings, columns named in `numbers` are stored as numbers."""
    shared, rows = [], []
    for i, values in enumerate(table, start=1):
        cells = []
        for j, v in enumerate(values):
            ref = f"{col(j)}{i}"
            if i > 1 and table[0][j] in numbers and v != "":
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            elif v != "":
                shared.append(v)
                cells.append(f'<c r="{ref}" t="s"><v>{len(shared) - 1}</v></c>')
        rows.append(f'<row r="{i}">{"".join(cells)}</row>')
    ns = 'xmlns="urn:test:main" xmlns:r="urn:test:rel"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns}><sheets><sheet name="Invoices" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="urn:test:pr"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData>{"".join(rows)}</sheetData></worksheet>')


UBL = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:CustomizationID>urn:peppol:pint:billing-1@ae-1</cbc:CustomizationID>
 <cbc:ProfileExecutionID>{tx}</cbc:ProfileExecutionID>
 <cbc:ID>{number}</cbc:ID><cbc:IssueDate>2026-10-01</cbc:IssueDate><cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
 <cbc:DocumentCurrencyCode>AED</cbc:DocumentCurrencyCode>
 <cac:AccountingSupplierParty><cac:Party>
  <cbc:EndpointID schemeID="0235">1000000000</cbc:EndpointID>
  <cac:PostalAddress><cbc:CountrySubentity>{emirate}</cbc:CountrySubentity><cac:Country><cbc:IdentificationCode>AE</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
  <cac:PartyTaxScheme><cbc:CompanyID>{trn}</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
  <cac:PartyLegalEntity><cbc:RegistrationName>Seller LLC</cbc:RegistrationName></cac:PartyLegalEntity>
 </cac:Party></cac:AccountingSupplierParty>
 <cac:AccountingCustomerParty><cac:Party>
  <cbc:EndpointID schemeID="0235">1000000001</cbc:EndpointID>
  <cac:PostalAddress><cbc:CountrySubentity>AUH</cbc:CountrySubentity><cac:Country><cbc:IdentificationCode>AE</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
  <cac:PartyTaxScheme><cbc:CompanyID>100000000000103</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
  <cac:PartyLegalEntity><cbc:RegistrationName>Buyer LLC</cbc:RegistrationName></cac:PartyLegalEntity>
 </cac:Party></cac:AccountingCustomerParty>
 <cac:LegalMonetaryTotal><cbc:LineExtensionAmount currencyID="AED">200</cbc:LineExtensionAmount></cac:LegalMonetaryTotal>
 <cac:InvoiceLine>
  <cbc:ID>1</cbc:ID><cbc:InvoicedQuantity unitCode="{unit}">2</cbc:InvoicedQuantity>
  <cbc:LineExtensionAmount currencyID="AED">200</cbc:LineExtensionAmount>
  <cac:Item><cbc:Name>Consulting day</cbc:Name>
   <cac:CommodityClassification><cbc:CommodityCode>S</cbc:CommodityCode></cac:CommodityClassification>
   <cac:AdditionalItemIdentification><cbc:ID>998311</cbc:ID></cac:AdditionalItemIdentification>
   <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>5</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory>
  </cac:Item>
  <cac:Price><cbc:PriceAmount currencyID="AED">100</cbc:PriceAmount></cac:Price>
  <cac:ItemPriceExtension><cbc:Amount currencyID="AED">210</cbc:Amount><cac:TaxTotal><cbc:TaxAmount currencyID="AED">10</cbc:TaxAmount></cac:TaxTotal></cac:ItemPriceExtension>
 </cac:InvoiceLine>
</Invoice>
"""


def ubl(**change):
    return UBL.format(**{"tx": "00000000", "number": "INV-1", "emirate": "DXB", "trn": "100000000000003", "unit": "DAY", **change})


class Inputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_xlsx_matches_csv(self):
        import csv
        with open(SAMPLE, encoding="utf-8", newline="") as fh:
            table = list(csv.reader(fh))
        numbers = ("quantity", "unit_price", "line_net", "vat_rate", "line_vat", "line_allowance")
        path = os.path.join(self.tmp, "invoices.xlsx")
        write_xlsx(path, table, numbers)
        code, out = check(path)
        code_csv, out_csv = check(SAMPLE)
        self.assertEqual(code, code_csv)
        self.assertEqual(out["file_encoding"], "xlsx")
        strip = lambda o: [(g["invoice"], g["field"], g["rule"]) for g in o["gaps"]]
        self.assertEqual(strip(out), strip(out_csv))

    def test_xlsx_date_serial_and_text_kept(self):
        import csv
        with open(SAMPLE, encoding="utf-8", newline="") as fh:
            table = list(csv.reader(fh))[:2]
        table[1][table[0].index("issue_date")] = "46296"  # 2026-10-01 as an Excel date
        path = os.path.join(self.tmp, "dates.xlsx")
        write_xlsx(path, table, ("issue_date",))
        code, out = check(path)
        self.assertEqual(code, 0, out)

    def test_bad_xlsx_exits_2(self):
        path = os.path.join(self.tmp, "broken.xlsx")
        Path(path).write_bytes(b"not a zip")
        self.assertEqual(check(path)[0], 2)

    def test_ubl_clean(self):
        path = os.path.join(self.tmp, "inv.xml")
        Path(path).write_text(ubl(), encoding="utf-8")
        code, out = check(path)
        self.assertEqual((code, out["gaps"]), (0, []), out)

    def test_ubl_folder_and_gaps(self):
        Path(self.tmp, "a.xml").write_text(ubl(emirate="Dubai", trn="1234", unit="day"), encoding="utf-8")
        Path(self.tmp, "b.xml").write_text(ubl(number="INV-2", tx="0"), encoding="utf-8")
        Path(self.tmp, "c.xml").write_text(ubl(number="INV-2"), encoding="utf-8")
        code, out = check(self.tmp)
        found = sorted((g["invoice"], g["rule"]) for g in out["gaps"])
        self.assertEqual(found, [("INV-1", "ibr-128-ae"), ("INV-1", "ibr-132-ae"), ("INV-1", "ibr-cl-23"),
                                 ("INV-2", "ibr-154-ae"), ("INV-2", "mc-header-mismatch")])

    def test_unreadable_xml_exits_2(self):
        path = os.path.join(self.tmp, "bad.xml")
        Path(path).write_text("<Invoice>", encoding="utf-8")
        self.assertEqual(check(path)[0], 2)

    @unittest.skipUnless(os.environ.get("PINT_AE_EXAMPLES"), "set PINT_AE_EXAMPLES to the example folder from resources.zip")
    def test_official_examples(self):
        code, out = check(os.environ["PINT_AE_EXAMPLES"], "--all")
        self.assertEqual([g["rule"] for g in out["gaps"] if g["rule"] != "mc-header-mismatch"], [])


if __name__ == "__main__":
    unittest.main()
