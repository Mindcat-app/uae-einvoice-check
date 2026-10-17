"""UAE e-invoice data checks for invoice data: CSV or .xlsx (one row per invoice line), or PINT AE UBL XML.

Each check names the PINT AE v1.0.4 rule it mirrors (ibr-... or aligned-..., from the official Schematron;
the README links the source). Checks with an "mc-" id are our own
data-quality checks with no single Schematron rule. This is a pre-check on source data, not a
replacement for validating the final UBL XML, and not tax advice.

Usage: python3 -I check_uae.py <invoices.csv | .xlsx | .xml | folder of .xml> [options]
       python3 -I check_uae.py customers.csv --master customers   (or items.csv --master items)
Run with --help for the options. It only reads, except --report and --handoff, which write where you say.
Exit codes: 0 no gaps, 1 gaps found, 2 the file could not be checked.
"""
import argparse
import csv
import datetime
import io
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal, InvalidOperation

TRN = re.compile(r"^1[0-9]{12}03$")
TIN = re.compile(r"^1[0-9]{9}$")
EMIRATES = {"AUH", "DXB", "SHJ", "UAQ", "FUJ", "AJM", "RAK"}
INVOICE_TYPES, CREDIT_TYPES = {"380", "480"}, {"381", "81"}
OUT_OF_SCOPE_TYPES = {"480", "81"}
VAT_CATEGORIES = {"S", "Z", "E", "O", "AE", "N"}
CREDIT_REASONS = {"DL8.61.1.A", "DL8.61.1.B", "DL8.61.1.C", "DL8.61.1.D", "DL8.61.1.E", "VD"}
ITEM_KINDS = {"goods": "G", "g": "G", "service": "S", "services": "S", "s": "S", "both": "B", "b": "B"}
REQUIRED = ["invoice_number", "issue_date", "type_code", "currency", "seller_name", "buyer_name",
            "line_id", "item_name", "quantity", "unit_price", "line_net", "vat_category"]
NUMERIC = ["quantity", "unit_price", "base_quantity", "line_allowance", "line_charge", "line_net",
           "vat_rate", "line_vat", "line_net_aed", "exchange_rate", "invoice_total_net", "invoice_total_vat",
           "invoice_total_gross"]
# Every invoice-level field must be listed here: gaps on these are reported once per invoice (see dedupe).
HEADER = ["invoice_number", "issue_date", "type_code", "currency", "exchange_rate", "seller_name", "seller_trn",
          "seller_tin", "seller_emirate", "seller_country", "buyer_name", "buyer_trn", "buyer_emirate",
          "buyer_country", "preceding_invoice", "credit_reason", "invoice_total_net", "invoice_total_vat",
          "invoice_total_gross", "transaction_type", "seller_endpoint", "seller_endpoint_scheme", "buyer_endpoint",
          "buyer_endpoint_scheme"]
MASKED = ["seller_trn", "buyer_trn", "seller_tin", "trn", "tin", "seller_endpoint", "buyer_endpoint"]  # UAE endpoints hold the TIN
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
CODE_FIELDS = ["type_code", "currency", "seller_emirate", "seller_country", "buyer_emirate", "buyer_country", "credit_reason"]
UNIT = re.compile(r"^[A-Z0-9]{2,3}$")
TX = re.compile(r"^[01]{8}$")
# Endpoint scheme ids allowed by ibr-cl-25 (CEF EAS code list, PINT AE 1.0.4)
EAS = dict.fromkeys(("0002 0007 0009 0037 0060 0088 0096 0097 0106 0130 0135 0142 0151 0154 0158 0177 0183 0184 0188 0190 "
                     "0191 0192 0193 0195 0196 0198 0199 0200 0201 0202 0204 0208 0209 0210 0211 0212 0213 0215 0216 0218 "
                     "0221 0230 0235 0240 0242 0244 0245 0246 0248 9910 9913 9914 9915 9918 9919 9920 9922 9923 9924 9925 "
                     "9926 9927 9928 9929 9930 9931 9932 9933 9934 9935 9936 9937 9938 9939 9940 9941 9942 9943 9944 9945 "
                     "9946 9947 9948 9949 9950 9951 9952 9953 9957 9959").split())
SCENARIOS = [("credit note (381 or 81)", lambda c: any(c["type_code"].get(t) for t in CREDIT_TYPES)), ("zero-rated (Z)", lambda c: c["vat_category"].get("Z")),
             ("exempt (E)", lambda c: c["vat_category"].get("E")), ("reverse charge (AE)", lambda c: c["vat_category"].get("AE")),
             ("non-AED currency", lambda c: any(k not in ("AED", "(blank)") for k in c["currency"]))]
SHOWN = 50


def dec(v):
    """Strict decimal: ASCII digits only, finite. Returns None for empty or unreadable values."""
    s = (v or "").strip()
    if not s or not re.fullmatch(r"-?[0-9]+(\.[0-9]+)?", s):
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def inv(r):
    return (r.get("invoice_number") or "").strip() or f"(row {r['_row']})"


def check_row(r):
    gaps = []

    def gap(field, rule, fix):
        gaps.append({"invoice": inv(r), "line": r.get("line_id", ""),
                     "field": field, "value": r.get(field, ""), "rule": rule, "fix": fix})

    get = lambda f: (r.get(f) or "").strip()
    for f in REQUIRED:
        if not get(f):
            gap(f, "mc-missing", f"{f} is empty")
    for f in NUMERIC:
        if get(f) and dec(get(f)) is None:
            gap(f, "mc-number-format", "Use a plain number: digits and a dot, no commas, % or currency signs")

    t, cat, cur = get("type_code"), get("vat_category"), get("currency").upper()
    if get("issue_date"):
        try:
            datetime.date.fromisoformat(get("issue_date") if DATE.match(get("issue_date")) else "")
        except ValueError:
            gap("issue_date", "mc-date-format", "Use a real date written YYYY-MM-DD, such as 2026-10-01")
    if t and t not in INVOICE_TYPES | CREDIT_TYPES:
        gap("type_code", "ibr-cl-01", "Invoice type must be 380 or 480; credit note 381 or 81")
    if t in CREDIT_TYPES and not get("preceding_invoice") and get("credit_reason") != "VD":
        gap("preceding_invoice", "ibr-055-ae", "Credit notes need the original invoice number")
    if t == "381" and not get("credit_reason"):  # the official ibr-158-ae test checks 381 only, not 81
        gap("credit_reason", "ibr-158-ae", "Credit notes (381) need a credit note reason code, such as DL8.61.1.A or VD")
    if get("credit_reason") and get("credit_reason") not in CREDIT_REASONS:
        gap("credit_reason", "ibr-001-ae", "Use DL8.61.1.A, DL8.61.1.B, DL8.61.1.C, DL8.61.1.D, DL8.61.1.E or VD (capitals)")
    if t in OUT_OF_SCOPE_TYPES and cat and cat not in {"E", "O", "Z"}:
        gap("vat_category", "ibr-122-ae", "Type 480 and 81 lines can only be E, O or Z")

    # Transaction type flags (BTAE-02): 8 positions of 0 or 1
    tx = get("transaction_type")
    if not TX.match(tx):
        gap("transaction_type", "ibr-154-ae", "Give 8 flags of 0 or 1, such as 00000000; format the column as text")
    elif t in OUT_OF_SCOPE_TYPES and "1" in tx[1:4]:
        gap("transaction_type", "ibr-157-ae", "Types 480 and 81 cannot be deemed supply, margin scheme or summary (positions 2-4)")

    # Peppol electronic addresses
    for who, need, scheme_rule in (("seller", "ibr-081", "ibr-062"), ("buyer", "ibr-080", "ibr-063")):
        scheme = get(f"{who}_endpoint_scheme")
        if not get(f"{who}_endpoint"):
            gap(f"{who}_endpoint", need, f"The {who} needs an electronic address (endpoint id)")
        elif not scheme:
            gap(f"{who}_endpoint_scheme", scheme_rule, "Give the endpoint scheme, 0235 for the UAE")
        elif scheme not in EAS:
            gap(f"{who}_endpoint_scheme", "ibr-cl-25", "Use a scheme id from the Peppol EAS list, 0235 for the UAE (format the column as text)")

    # Seller identifiers
    trn, tin = get("seller_trn"), get("seller_tin")
    if t not in OUT_OF_SCOPE_TYPES and not trn:
        gap("seller_trn", "ibr-134-ae", "Seller TRN is required except on type 480 and 81")
    if not trn and not tin:
        gap("seller_tin", "ibr-177-ae", "Give the seller TRN or TIN")
    if trn and not TRN.match(trn):
        gap("seller_trn", "ibr-132-ae", "TRN must be 15 digits, start with 1 and end with 03")
    if tin and not TIN.match(tin):
        gap("seller_tin", "ibr-148-ae", "TIN must be 10 digits starting with 1")
    if get("seller_country").upper() in ("", "AE") and get("seller_emirate") not in EMIRATES:
        gap("seller_emirate", "ibr-128-ae", "Use AUH, DXB, SHJ, UAQ, FUJ, AJM or RAK (capitals)")

    party_gaps(get, gap, "buyer_trn", "buyer_emirate", "buyer_country", need_emirate=False)

    # VAT category rules
    rate, vat, net = dec(get("vat_rate")), dec(get("line_vat")), dec(get("line_net"))
    if cat and cat not in VAT_CATEGORIES:
        gap("vat_category", "ibr-139-ae", "Use S, Z, E, O, AE or N (capitals)")
    if cat == "S":
        if rate != 5:
            gap("vat_rate", "ibr-190-ae", "Standard-rated (S) lines must be 5")
        if get("exemption_reason"):
            gap("exemption_reason", "aligned-ibrp-s-10", "Standard-rated lines must not carry an exemption reason")
    if cat == "Z" and rate != 0:
        gap("vat_rate", "mc-zero-rate", "Zero-rated (Z) lines must have rate 0")
    if cat in {"E", "O"} and get("vat_rate"):
        gap("vat_rate", f"aligned-ibrp-{cat.lower()}-05", f"Category {cat} lines must not carry a VAT rate")
    if cat == "E" and not get("exemption_reason"):
        gap("exemption_reason", "ibr-167-ae", "Exempt (E) lines need an exemption reason code")
    if cat == "N" and (rate is None or rate == 0):
        gap("vat_rate", "ibr-111-ae", "Category N lines need a rate above zero")
    if cat == "AE":
        if not get("vat_rate"):
            gap("vat_rate", "aligned-ibrp-ae-05-ae", "Reverse-charge (AE) lines need a VAT rate (the rate the buyer accounts for)")
        if not get("buyer_trn"):
            gap("buyer_trn", "ibr-103-ae", "Reverse-charge (AE) lines need the buyer's TRN")
        if vat not in (None, Decimal(0)):
            gap("line_vat", "mc-reverse-charge-vat", "Reverse-charge lines carry 0 VAT; the buyer accounts for it")
    margin = TX.match(tx) and tx[2] == "1"  # VAT is on the margin
    if cat in {"S", "Z", "N"} and None not in (net, rate, vat) and not margin and not (r.get("_xml") and cur != "AED") and abs(net * rate / 100 - vat) > Decimal("0.01"):
        gap("line_vat", "mc-vat-maths", f"net x rate = {net * rate / 100:.2f}, not {vat}")

    # Line maths: qty x (price / base qty) + charges - allowances
    q, p = dec(get("quantity")), dec(get("unit_price"))
    base = dec(get("base_quantity")) if get("base_quantity") else Decimal(1)
    if base is not None and base <= 0:
        gap("base_quantity", "mc-base-quantity", "Base quantity must be more than 0; leave it empty for 1")
    allow = dec(get("line_allowance")) if get("line_allowance") else Decimal(0)
    charge = dec(get("line_charge")) if get("line_charge") else Decimal(0)
    if None not in (q, p, net, base, allow, charge) and base != 0:  # unreadable numbers are reported once, above
        want = q * (p / base) + charge - allow
        if abs(want - net) > Decimal("0.01"):
            gap("line_net", "ibr-147-ae", f"quantity x price / base quantity + charges - allowances = {want:.2f}, not {net}")

    # Currency
    if cur and cur != "AED" and not get("exchange_rate"):
        gap("exchange_rate", "ibr-159-ae", "Non-AED invoices need the exchange rate to AED")
    if r.get("_xml"):
        if cat and cat != "E" and not (get("line_vat") and r.get("_payable")):
            gap("line_vat", "ibr-104-ae", "Lines need the VAT amount (BTAE-08) and amount payable (BTAE-10) in AED")
    elif cur and cur != "AED":
        if cat != "E" and not get("line_net_aed"):
            gap("line_net_aed", "ibr-104-ae", "Non-AED invoices need each line's amount in AED")
        fx, aed = dec(get("exchange_rate")), dec(get("line_net_aed"))
        if None not in (net, fx, aed) and abs(net * fx - aed) > Decimal("0.01"):
            gap("line_net_aed", "mc-aed-maths", f"line_net x exchange_rate (AED per 1 {cur}) = {net * fx:.2f}, not {aed}")

    item_gaps(get, gap)
    return gaps


def party_gaps(get, gap, trn, emirate, country, need_emirate):
    """Buyer or customer: UAE rules apply only when the country is AE (blank is read as AE)."""
    if get(country).upper() not in ("", "AE"):
        return
    if get(trn) and not TRN.match(get(trn)):
        gap(trn, "ibr-132-ae", "TRN must be 15 digits, start with 1 and end with 03")
    if (need_emirate or get(emirate)) and get(emirate) not in EMIRATES:
        gap(emirate, "ibr-128-ae", "Use AUH, DXB, SHJ, UAQ, FUJ, AJM or RAK (capitals)")


def item_gaps(get, gap):
    """Unit of measure and item codes, for invoice lines and for an item list."""
    if not get("unit_code"):
        gap("unit_code", "ibr-023", "Every line needs a unit code (UN/ECE Rec 20), such as EA, HUR, DAY, MON or KGM")
    elif not UNIT.match(get("unit_code")):
        gap("unit_code", "ibr-cl-23", "Use a UN/ECE Rec 20 unit code in capitals, such as EA, HUR, DAY, MON or KGM")

    # Item codes
    kind = ITEM_KINDS.get(get("item_kind").lower())
    if get("item_kind") and not kind:
        gap("item_kind", "mc-item-kind", "Use goods, service or both")
    if kind == "G" and not get("hs_code"):
        gap("hs_code", "ibr-184-ae", "Goods need an HS code")
    if kind == "S" and not get("sac_code"):
        gap("sac_code", "ibr-185-ae", "Services need a SAC code")
    for f, name in (("hs_code", "an HS code"), ("sac_code", "a SAC code")):
        if kind == "B" and not get(f):
            gap(f, "ibr-186-ae", f"Items that are both goods and services need {name}")


MASTER = {"customers": ["customer_name", "country"], "items": ["item_name", "item_kind", "unit_code", "vat_category"]}


def check_master(r, kind):
    """One customer or item record, with the same rule functions as invoice lines."""
    gaps = []
    get = lambda f: (r.get(f) or "").strip()
    label = get("customer_name" if kind == "customers" else "item_name") or f"(row {r['_row']})"

    def gap(field, rule, fix):
        gaps.append({"record": label, "line": "", "field": field, "value": r.get(field, ""), "rule": rule, "fix": fix})

    for f in MASTER[kind]:
        if not get(f):
            gap(f, "mc-missing", f"{f} is empty")
    if kind == "customers":
        party_gaps(get, gap, "trn", "emirate", "country", need_emirate=True)
        if get("tin") and not TIN.match(get("tin")):
            gap("tin", "mc-tin-format", "TIN must be 10 digits starting with 1")
    else:
        item_gaps(get, gap)
        if get("vat_category") and get("vat_category") not in VAT_CATEGORIES:
            gap("vat_category", "ibr-139-ae", "Use S, Z, E, O, AE or N (capitals)")
    return gaps


def norm(f, v):
    """A header value as compared across lines: trimmed, codes in capitals, numbers by value."""
    v = (v or "").strip()
    if f in CODE_FIELDS:
        return v.upper()
    return dec(v) if f in NUMERIC and dec(v) is not None else v


def fill_headers(rows):
    """Many exports fill invoice-level columns on the first line only: copy them to blank cells on later lines."""
    first = {}
    for r in rows:
        if not (r.get("invoice_number") or "").strip():
            continue
        top = first.setdefault((inv(r), r.get("_file")), r)
        for f in HEADER:
            if not (r.get(f) or "").strip() and (top.get(f) or "").strip():
                r[f] = top[f]
    return rows


def check_invoices(rows):
    """Per-invoice checks: header fields that differ between lines, and warnings that are not gaps."""
    gaps, warnings, by_inv, files = [], [], defaultdict(list), defaultdict(dict)
    for r in rows:
        by_inv[(inv(r), r.get("_file"))].append(r)
        files[inv(r)][r.get("_file")] = True
    for i, found in files.items():
        if len(found) > 1:  # XML: one invoice number in several files
            gaps.append({"invoice": i, "line": "", "field": "invoice_number", "value": " | ".join(found), "rule": "mc-header-mismatch",
                         "fix": "Each invoice needs its own number; this one is used in more than one file"})
    for (i, _), lines in by_inv.items():
        for f in HEADER:
            seen = {norm(f, r.get(f)): True for r in lines}
            if len(seen) > 1:
                gaps.append({"invoice": i, "line": "", "field": f, "value": " | ".join(str(k) or "(blank)" for k in seen),
                             "rule": "mc-header-mismatch", "fix": f"Lines of one invoice must agree on {f}"})
        r = lines[0]
        gaps += check_totals(i, r, lines)
        if ((r.get("buyer_country") or "").strip().upper() in ("", "AE") and not (r.get("buyer_trn") or "").strip()
                and any((x.get("vat_category") or "").strip() == "S" for x in lines)):
            warnings.append({"invoice": i, "field": "buyer_trn", "rule": "mc-buyer-trn-blank",
                             "note": "UAE buyer with no TRN on a standard-rated invoice: fine for a consumer, a gap for a VAT-registered business"})
    return gaps, warnings


def check_totals(i, r, lines):
    """Optional invoice_total_* columns: compare with the sums of the lines; skipped when a line amount is unknown."""
    gaps = []
    nets = [dec(x.get("line_net")) for x in lines]
    vats = [Decimal(0) if not (x.get("line_vat") or "").strip() and (x.get("vat_category") or "").strip() in ("E", "O")
            else dec(x.get("line_vat")) for x in lines]  # a blank VAT only counts as 0 on E and O lines
    net = None if None in nets else sum(nets)
    vat = None if None in vats else sum(vats)
    gross = None if None in (net, vat) else net + vat
    for f, want, rule in (("invoice_total_net", net, "mc-total-net"), ("invoice_total_vat", vat, "mc-total-vat"),
                          ("invoice_total_gross", gross, "mc-total-gross")):
        got = dec(r.get(f))
        if None not in (got, want) and abs(got - want) > Decimal("0.01"):
            gaps.append({"invoice": i, "line": "", "field": f, "value": r.get(f, ""), "rule": rule,
                         "fix": f"The lines add up to {want:.2f}, not {got}"})
    return gaps


def mask(v):
    v = str(v)
    if v == "(blank)":
        return v
    return "*" * max(len(v) - 4, 0) + v[-4:] if len(v) > 4 else "*" * len(v)


def summary(out):
    unit = "records" if "master" in out else "invoices"
    head = f"{out[unit]} {out['master']} records" if "master" in out else f"{out['lines']} lines in {out['invoices']} invoices"
    text = [f"Checked {head} ({out['file_encoding']}).",
            f"{unit.capitalize()} with gaps: {out[unit + '_with_gaps']} of {out[unit]}. Gaps: {out['gaps_total']}."]
    text += ["Top rules:"] if out["by_rule"] else []
    text += [f"  {b['rule']}: {b['gaps']} gap(s) in {b[unit]} {unit[:-1]}(s)" for b in out["by_rule"][:10]]
    if "coverage" in out:
        missing = out["coverage"]["not_in_sample"]
        text.append("Not in this sample: " + (", ".join(missing) if missing else "none of the common cases are missing"))
        text.append(f"Warnings (not gaps): {len(out['warnings'])}")
    text.append("Help getting ready: mindcat.ai/contact")
    return "\n".join(text)


def collapse_missing(gaps, cols):
    """A column absent from the file gets one gap per rule, with "(all)" for the invoice, not one gap per invoice.
    Gaps on cells that are there but blank or wrong stay per invoice. XML (cols None) has no columns."""
    if cols is None:
        return gaps
    seen, out = {}, []
    for g in gaps:
        if g["field"] in cols:
            out.append(g)
        elif (g["field"], g["rule"]) not in seen:
            seen[(g["field"], g["rule"])] = True
            fix = "" if g["fix"] == f"{g['field']} is empty" else ". " + g["fix"]
            who = "record" if "record" in g else "invoice"
            out.append({**g, who: "(all)", "line": "", "value": "", "fix": "column missing from the file" + fix})
    return out


def dedupe(gaps):
    """Report a header-field gap once per invoice, not once per line."""
    seen, out = {}, []
    for g in gaps:
        if g["field"] in HEADER:
            key = (g["invoice"], g["field"], g["rule"])
            if key in seen:
                continue
            seen[key] = True
            g = {**g, "line": ""}
        out.append(g)
    return out


def coverage(rows):
    c = {"type_code": defaultdict(int), "vat_category": defaultdict(int), "currency": defaultdict(int)}
    first = {}
    for r in rows:
        first.setdefault(inv(r), r)
        c["vat_category"][(r.get("vat_category") or "").strip() or "(blank)"] += 1
    for r in first.values():
        c["type_code"][(r.get("type_code") or "").strip() or "(blank)"] += 1
        c["currency"][(r.get("currency") or "").strip().upper() or "(blank)"] += 1
    return {"invoices_by_type_code": dict(c["type_code"]), "lines_by_vat_category": dict(c["vat_category"]),
            "invoices_by_currency": dict(c["currency"]), "not_in_sample": [n for n, has in SCENARIOS if not has(c)]}


def to_rows(header, records):
    """Header cells and (row number, values) pairs to row dicts. Headers ignore case and spaces; blank ones are dropped."""
    names = [(n or "").strip().lower() for n in header]
    filled = [k for k in names if k]
    twice = sorted({k for k in filled if filled.count(k) > 1})
    if twice:
        raise ValueError(f"these columns appear twice (headers ignore case and spaces): {', '.join(twice)}")
    rows = []
    for n, values in records:
        row = {k: (values[j] if j < len(values) else "") for j, k in enumerate(names) if k}
        row["_row"] = n
        rows.append(row)
    return rows


def decode(data):
    """UTF-16 when it starts with its byte order mark, then UTF-8. Otherwise Arabic Windows (cp1256) when the text
    has Arabic words, else Western Windows (cp1252)."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16"
    data = data[3:] if data.startswith(b"\xef\xbb\xbf") else data
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    arabic = data.decode("cp1256")  # decodes any bytes
    if re.search("[\u0621-\u064a]{2,}", arabic):
        return arabic, "cp1256"
    try:
        return data.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        return arabic, "cp1256"


def load_csv(path):
    with open(path, "rb") as fh:
        content, enc = decode(fh.read())
    lines = [(n, x) for n, x in enumerate(csv.reader(io.StringIO(content, newline="")), start=1) if any(c.strip() for c in x)]
    return (to_rows(lines[0][1], lines[1:]) if lines else []), enc  # rows of empty cells (",,,") are skipped


def local(el):
    return el.tag.rsplit("}", 1)[-1]


def col_index(ref):
    n = 0
    for ch in re.match(r"[A-Z]*", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def load_xlsx(path):
    """First sheet of an .xlsx file. Cell text is kept as Excel stored it; issue_date serial numbers become dates."""
    with zipfile.ZipFile(path) as z:
        book = ET.fromstring(z.read("xl/workbook.xml"))
        sheet = next(e for e in book.iter() if local(e) == "sheet")
        rid = next(v for k, v in sheet.attrib.items() if k.endswith("}id"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(e.get("Target") for e in rels.iter() if e.get("Id") == rid)
        target = target.lstrip("/") if target.startswith("/") else "xl/" + target
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
                parts = [si] + [r for r in si if local(r) == "r"]
                shared.append("".join(t.text or "" for p in parts for t in p if local(t) == "t"))
        records = []
        for row in (e for e in ET.fromstring(z.read(target)).iter() if local(e) == "row"):
            values = {}
            for c in (e for e in row if local(e) == "c"):  # a cell with no "r" follows the one before it
                kind, v = c.get("t"), next((e.text or "" for e in c if local(e) == "v"), "")
                if kind == "s":
                    v = shared[int(v)]
                elif kind == "inlineStr":
                    v = "".join(t.text or "" for t in c.iter() if local(t) == "t")
                values[col_index(c.get("r")) if c.get("r") else max(values, default=-1) + 1] = v
            if any(values.values()):
                records.append((int(row.get("r", len(records) + 1)), [values.get(j, "") for j in range(max(values) + 1)]))
    if not records:
        return [], "xlsx"
    rows = to_rows(records[0][1], records[1:])
    for r in rows:
        if re.fullmatch(r"[0-9]{5}(\.0+)?", r.get("issue_date", "")):
            r["issue_date"] = str(datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(r["issue_date"]))))
    return rows, "xlsx"


def at(el, path):
    """First element down a slash path of local names (namespaces ignored), or None."""
    for name in path.split("/"):
        if el is None:
            return None
        el = next((c for c in el if local(c) == name), None)
    return el


def text(el, path, attr=None):
    el = at(el, path) if path else el
    if el is None:
        return ""
    return (el.get(attr, "") if attr else el.text or "").strip()


def party(p, who):
    """Party fields from a UBL cac:Party."""
    schemes = [x for x in (p if p is not None else []) if local(x) == "PartyTaxScheme"]
    vat = [text(x, "CompanyID") for x in schemes if text(x, "TaxScheme/ID").upper() == "VAT"]
    other = [text(x, "CompanyID") for x in schemes if text(x, "TaxScheme/ID").upper() != "VAT"]
    out = {f"{who}_name": text(p, "PartyLegalEntity/RegistrationName") or text(p, "PartyName/Name"),
           f"{who}_trn": vat[0] if vat else "", f"{who}_country": text(p, "PostalAddress/Country/IdentificationCode"),
           f"{who}_emirate": text(p, "PostalAddress/CountrySubentity"), f"{who}_endpoint": text(p, "EndpointID"),
           f"{who}_endpoint_scheme": text(p, "EndpointID", "schemeID")}
    if who == "seller":
        out["seller_tin"] = other[0] if other else ""
    return out


def load_xml(path):
    """PINT AE UBL invoices or credit notes (one file, or every .xml in a folder) as rows of the CSV shape."""
    files = sorted(os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith(".xml")) if os.path.isdir(path) else [path]
    rows = []
    for f in files:
        try:
            doc = ET.parse(f).getroot()
        except ET.ParseError as e:
            raise ValueError(f"{os.path.basename(f)} is not readable XML ({e})")
        credit = local(doc) == "CreditNote"
        head = {"invoice_number": text(doc, "ID"), "issue_date": text(doc, "IssueDate"),
                "type_code": text(doc, "CreditNoteTypeCode" if credit else "InvoiceTypeCode"),
                "currency": text(doc, "DocumentCurrencyCode"), "exchange_rate": text(doc, "TaxExchangeRate/CalculationRate"),
                "transaction_type": text(doc, "ProfileExecutionID"),
                "preceding_invoice": text(doc, "BillingReference/InvoiceDocumentReference/ID"),
                "credit_reason": text(doc, "DiscrepancyResponse/ResponseCode"),
                "invoice_total_net": text(doc, "LegalMonetaryTotal/LineExtensionAmount"),
                **party(at(doc, "AccountingSupplierParty/Party"), "seller"),
                **party(at(doc, "AccountingCustomerParty/Party"), "buyer")}
        for n, line in enumerate((x for x in doc if local(x) in ("InvoiceLine", "CreditNoteLine")), start=1):
            qty = at(line, "CreditedQuantity" if credit else "InvoicedQuantity")
            ac = [x for x in line if local(x) == "AllowanceCharge"]
            amounts = lambda charge: [dec(text(x, "Amount")) for x in ac if text(x, "ChargeIndicator").lower() == str(charge).lower()]
            allow, charge = amounts(False), amounts(True)
            kind = text(line, "Item/CommodityClassification/CommodityCode")
            rows.append({**head, "_row": f"{os.path.basename(f)} line {n}", "_xml": True, "_file": os.path.basename(f), "_payable": text(line, "ItemPriceExtension/Amount"),
                         "line_id": text(line, "ID"), "item_name": text(line, "Item/Name"), "item_kind": kind,
                         "hs_code": text(line, "Item/CommodityClassification/ItemClassificationCode"),
                         "sac_code": text(line, "Item/AdditionalItemIdentification/ID"),
                         "quantity": text(qty, ""), "unit_code": text(qty, "", "unitCode"),
                         "unit_price": text(line, "Price/PriceAmount"), "base_quantity": text(line, "Price/BaseQuantity"),
                         "line_allowance": "" if None in allow else str(sum(allow)) if allow else "",
                         "line_charge": "" if None in charge else str(sum(charge)) if charge else "",
                         "line_net": text(line, "LineExtensionAmount"), "line_net_aed": "",
                         "vat_category": text(line, "Item/ClassifiedTaxCategory/ID"),
                         "vat_rate": text(line, "Item/ClassifiedTaxCategory/Percent"),
                         "exemption_reason": text(line, "Item/ClassifiedTaxCategory/TaxExemptionReasonCode"),
                         "line_vat": text(line, "ItemPriceExtension/TaxTotal/TaxAmount")})
    return rows, "xml"


def load(path):
    if os.path.isdir(path) or path.lower().endswith(".xml"):
        return load_xml(path)
    if path.lower().endswith(".xlsx"):
        try:
            return load_xlsx(path)
        except (zipfile.BadZipFile, KeyError, StopIteration, ET.ParseError, IndexError) as e:
            raise ValueError(f"could not read the Excel file ({type(e).__name__}); save it again as .xlsx or CSV")
    return load_csv(path)


FIELD_MAP = [
    ("invoice_number", "ibt-001", "Invoice number"), ("issue_date", "ibt-002", "Issue date, YYYY-MM-DD"),
    ("type_code", "ibt-003", "380, 480, 381 or 81"), ("currency", "ibt-005", "Invoice currency"),
    ("exchange_rate", "BTAE-04", "AED per 1 unit of the invoice currency"), ("transaction_type", "BTAE-02", "8 flags of 0 or 1"),
    ("seller_name", "ibt-027", ""), ("seller_trn", "ibt-031", "VAT TRN"), ("seller_tin", "ibt-032", "TIN when there is no TRN"),
    ("seller_endpoint", "ibt-034", "Peppol electronic address"), ("seller_endpoint_scheme", "ibt-034-1", "0235 in the UAE"),
    ("seller_emirate", "ibt-039", "AUH, DXB, SHJ, UAQ, FUJ, AJM or RAK"), ("seller_country", "ibt-040", ""),
    ("buyer_name", "ibt-044", ""), ("buyer_trn", "ibt-048", "Buyer VAT TRN"),
    ("buyer_endpoint", "ibt-049", "Peppol electronic address"), ("buyer_endpoint_scheme", "ibt-049-1", "0235 in the UAE"),
    ("buyer_emirate", "ibt-054", ""), ("buyer_country", "ibt-055", ""),
    ("preceding_invoice", "ibt-025", "Credit notes"), ("credit_reason", "BTAE-03", "Credit notes"),
    ("line_id", "ibt-126", ""), ("quantity", "ibt-129", ""), ("unit_code", "ibt-130", "UN/ECE Rec 20"),
    ("line_net", "ibt-131", ""), ("line_allowance", "ibt-136", ""), ("line_charge", "ibt-141", ""),
    ("unit_price", "ibt-146", "Net price"), ("base_quantity", "ibt-149", ""),
    ("vat_category", "ibt-151", ""), ("vat_rate", "ibt-152", ""), ("item_name", "ibt-153", ""),
    ("hs_code", "ibt-158", "Item classification (HS)"), ("item_kind", "BTAE-13", "Goods, services or both"),
    ("sac_code", "BTAE-17", "Service accounting code"), ("exemption_reason", "ibt-186", "Exempt lines"),
    ("line_vat", "BTAE-08", "VAT line amount in AED"),
    ("line_net_aed", "BTAE-10 (input)", "Line net in AED; your provider derives the amount payable in AED from it"),
    ("invoice_total_net", "ibt-106", "Optional"), ("invoice_total_vat", "ibt-110", "Optional"),
    ("invoice_total_gross", "ibt-112", "Optional")]


def write_report(path, gaps):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["invoice", "line", "field", "value", "rule", "fix", "owner", "status"])
        for g in gaps:
            w.writerow([g.get("invoice", g.get("record", "")), g["line"], g["field"], g["value"], g["rule"], g["fix"], "", ""])


def write_handoff(folder, out):
    """Markdown for the chosen provider: field map, gap counts and coverage. No names, numbers or amounts."""
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "field-map.md"), "w", encoding="utf-8") as fh:
        fh.write("# Field map: our columns to PINT AE\n\n| Column | PINT AE | Note |\n| --- | --- | --- |\n")
        fh.writelines(f"| `{c}` | {i} | {n} |\n" for c, i, n in FIELD_MAP)
    c = out["coverage"]
    lines = ["# E-invoicing readiness: data check", "",
             f"Checked {out['lines']} lines in {out['invoices']} invoices; {out['invoices_with_gaps']} have gaps "
             f"({out['gaps_total']} in all). This checks source data, not the final XML.", "",
             "| Rule | Field | Gaps | Invoices |", "| --- | --- | --- | --- |"]
    lines += [f"| {b['rule']} | {', '.join(b['fields'])} | {b['gaps']} | {b['invoices']} |" for b in out["by_rule"]]
    lines += ["", "## Sample coverage", "", f"- Invoices by type: {c['invoices_by_type_code']}",
              f"- Lines by VAT category: {c['lines_by_vat_category']}", f"- Invoices by currency: {c['invoices_by_currency']}",
              f"- Not in the sample: {', '.join(c['not_in_sample']) or 'none of the common cases'}",
              f"- Warnings to confirm (not gaps): {len(out['warnings'])}", ""]
    with open(os.path.join(folder, "readiness.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main(argv):
    ap = argparse.ArgumentParser(prog="check_uae.py", allow_abbrev=False,
                                 description="UAE e-invoice (PINT AE) data checks. Reads CSV, .xlsx or UBL XML.")
    ap.add_argument("path", help="CSV, .xlsx, .xml or a folder of .xml files")
    ap.add_argument("--all", action="store_true", help=f"list every gap, not only the first {SHOWN}")
    ap.add_argument("--mask", action="store_true", help="hide all but the last 4 characters of TRNs, TINs and endpoint ids")
    ap.add_argument("--summary", action="store_true", help="print a short text summary instead of JSON")
    ap.add_argument("--master", choices=list(MASTER), help="check a customer or item list instead of invoices")
    ap.add_argument("--report", metavar="GAPS.CSV", help="also write every gap to this CSV, one row per gap")
    ap.add_argument("--handoff", metavar="FOLDER", help="also write a field map and gap summary for your provider")
    a = ap.parse_args(argv[1:])
    if a.report and os.path.realpath(a.report) == os.path.realpath(a.path):
        print("--report must name a new file, not the file being checked", file=sys.stderr)
        return 2
    try:
        rows, enc = load(a.path)
    except (OSError, ValueError, csv.Error) as e:
        print(f"could not check {a.path}: {e}", file=sys.stderr)
        return 2
    if a.master and enc == "xml":
        print("--master reads a CSV or .xlsx list of customers or items, not invoice XML", file=sys.stderr)
        return 2
    if not rows:
        print(f"{a.path} has no rows, so nothing was checked", file=sys.stderr)
        return 2
    if a.master:
        gaps, warnings = [g for r in rows for g in check_master(r, a.master)], []
    else:
        inv_gaps, warnings = check_invoices(fill_headers(rows))
        gaps = dedupe([g for r in rows for g in check_row(r)]) + inv_gaps
    who = lambda g: g.get("invoice", g.get("record"))
    invoices_by_rule, fields_by_rule = defaultdict(dict), defaultdict(dict)
    for g in gaps:  # counted before collapse_missing, so "(all)" gaps still count every invoice they hit
        invoices_by_rule[g["rule"]][who(g)] = True
        fields_by_rule[g["rule"]][g["field"]] = True
    with_gaps = len({who(g) for g in gaps})
    gaps = collapse_missing(gaps, None if enc == "xml" else rows[0])
    by_rule = defaultdict(int)
    for g in gaps:
        by_rule[g["rule"]] += 1
    if a.mask:
        gaps = [{**g, "value": " | ".join(mask(x) for x in str(g["value"]).split(" | "))} if g["field"] in MASKED else g
                for g in gaps]
    shown = gaps if a.all else gaps[:SHOWN]
    unit = "records" if a.master else "invoices"
    out = {"file_encoding": enc, "lines": len(rows), unit: len(rows) if a.master else len({inv(r) for r in rows}),
           f"{unit}_with_gaps": with_gaps,
           "gaps_total": len(gaps), "gaps_shown": len(shown), "truncated": len(shown) < len(gaps),
           "by_rule": [{"rule": k, "gaps": v, unit: len(invoices_by_rule[k]), "fields": list(fields_by_rule[k])}
                       for k, v in sorted(by_rule.items(), key=lambda kv: -kv[1])]}
    if a.master:
        out = {"master": a.master, **out}
    else:
        out.update({"coverage": coverage(rows), "warnings": warnings})
    out["gaps"] = shown
    try:
        if a.report:
            write_report(a.report, gaps)
        if a.handoff and not a.master:
            write_handoff(a.handoff, out)
    except OSError as e:
        print(f"could not write the report: {e}", file=sys.stderr)
        return 2
    print(summary(out) if a.summary else json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
