"""Saudi Arabia (ZATCA) e-invoice data pre-check for CSV exports (one row per invoice line).

Each check names the ZATCA rule it mirrors (BR-..., BR-KSA-..., from the E-Invoice XML Implementation
Standard v1.2 and the Data Dictionary of 2023-05-19). docs/ksa-rules.md lists every rule with its document
and section. Checks with a "csv-" id are about reading the file (numbers, dates, lines of one invoice that
disagree) and are not ZATCA rules.

This is a pre-check on source data. It does not build, sign, stamp, hash, send, report or clear invoices,
it does not create or verify QR codes, cryptographic stamps or invoice hashes, and it is not tax advice.
The final XML must still be validated with ZATCA's official tools (the SDK or the Fatoora portal).

Usage: python3 -I check_ksa.py invoices.csv [--all] [--mask] [--summary]   (--help lists the options)
Exit codes: 0 no gaps, 1 gaps found, 2 the file could not be checked.
"""
import argparse
import csv
import datetime
import json
import re
import sys
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

VAT_NO = re.compile(r"^3[0-9]{13}3$")  # BR-KSA-40 / BR-KSA-44
TYPE_CODES = {"388": "tax invoice", "386": "prepayment invoice", "383": "debit note", "381": "credit note"}
NOTE_TYPES = {"381", "383"}
TXN = re.compile(r"^0[12][01]{5}$")  # BR-KSA-06: NNPNESB
VAT_CATEGORIES = {"S", "Z", "E", "O"}
EXEMPTION_CODES = {  # XML Implementation Standard 11.2.4
    "E": {"VATEX-SA-29", "VATEX-SA-29-7", "VATEX-SA-30"},
    "Z": {"VATEX-SA-32", "VATEX-SA-33", "VATEX-SA-34-1", "VATEX-SA-34-2", "VATEX-SA-34-3", "VATEX-SA-34-4",
          "VATEX-SA-34-5", "VATEX-SA-35", "VATEX-SA-36", "VATEX-SA-EDU", "VATEX-SA-HEA", "VATEX-SA-MLTRY"},
    "O": {"VATEX-SA-OOS"},
}
CITIZEN_CODES = {"VATEX-SA-EDU", "VATEX-SA-HEA"}
SELLER_SCHEMES = {"CRN", "MOM", "MLS", "700", "SAG", "OTH"}  # BR-KSA-08
BUYER_SCHEMES = {"TIN", "CRN", "MOM", "MLS", "700", "SAG", "NAT", "GCC", "IQA", "PAS", "OTH"}  # BR-KSA-14
ALNUM = re.compile(r"^[A-Za-z0-9]+$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
TIME = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z?$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
COUNTRY = re.compile(r"^[A-Z]{2}$")
UUID_CHARS = re.compile(r"^[A-Za-z0-9-]+$")
DIGITS = re.compile(r"^[0-9]+$")
CENT = Decimal("0.01")

REQUIRED = [("invoice_number", "BR-02"), ("issue_date", "BR-03"), ("type_code", "BR-04"), ("currency", "BR-05"),
            ("seller_name", "BR-06"), ("issue_time", "BR-KSA-70"), ("transaction_code", "BR-KSA-06"),
            ("seller_vat", "BR-KSA-39"), ("line_id", "BR-21"), ("quantity", "BR-22"), ("line_net", "BR-24"),
            ("item_name", "BR-25"), ("unit_price", "BR-26"), ("vat_category", "BR-CO-04")]
SELLER_ADDRESS = ["seller_street", "seller_building_number", "seller_postal_code", "seller_city",
                  "seller_district", "seller_country"]
BUYER_SA_ADDRESS = ["buyer_street", "buyer_building_number", "buyer_postal_code", "buyer_city",
                    "buyer_district", "buyer_country"]
NUMERIC = ["quantity", "unit_price", "base_quantity", "line_allowance", "line_charge", "line_net", "vat_rate",
           "line_vat", "line_amount_with_vat", "invoice_total_net", "invoice_total_vat", "invoice_total_gross",
           "invoice_total_vat_sar"]
TWO_DECIMALS = {"line_net": "BR-DEC-23", "line_allowance": "BR-DEC-24", "line_charge": "BR-DEC-27",
                "line_vat": "BR-KSA-DEC-03", "line_amount_with_vat": "BR-KSA-DEC-04",
                "invoice_total_net": "BR-DEC-12", "invoice_total_vat": "BR-DEC-13",
                "invoice_total_gross": "BR-DEC-14", "invoice_total_vat_sar": "BR-DEC-15"}
MAX_CHARS = {"invoice_number": 127, "seller_name": 1000, "buyer_name": 1000, "seller_street": 1000,
             "buyer_street": 1000, "seller_city": 127, "buyer_city": 127, "seller_district": 127,
             "buyer_district": 127, "preceding_invoice": 5000, "note_reason": 1000, "line_id": 6,
             "item_name": 1000, "unit_code": 127}  # Data Dictionary column "maximum limit" (BR-KSA-F-06)
PHASE2 = ["uuid", "invoice_counter", "previous_invoice_hash"]
# Every invoice-level field must be listed here: gaps on these are reported once per invoice (see dedupe).
HEADER = ["invoice_number", "issue_date", "issue_time", "type_code", "transaction_code", "currency", "tax_currency",
          "supply_date", "supply_end_date", "seller_name", "seller_vat", "seller_id", "seller_id_scheme",
          "seller_street", "seller_building_number", "seller_postal_code", "seller_city", "seller_district",
          "seller_country", "buyer_name", "buyer_vat", "buyer_id", "buyer_id_scheme", "buyer_street",
          "buyer_building_number", "buyer_postal_code", "buyer_city", "buyer_district", "buyer_country",
          "preceding_invoice", "note_reason", "invoice_total_net", "invoice_total_vat", "invoice_total_gross",
          "invoice_total_vat_sar"] + PHASE2
CODE_FIELDS = ["type_code", "currency", "tax_currency", "seller_country", "buyer_country", "seller_id_scheme",
               "buyer_id_scheme"]
MASKED = ["seller_vat", "buyer_vat", "seller_id", "buyer_id"]
SCENARIOS = [("tax invoice (subtype 01)", lambda c: c["subtype"].get("01")),
             ("simplified invoice (subtype 02)", lambda c: c["subtype"].get("02")),
             ("credit note (381)", lambda c: c["type_code"].get("381")),
             ("debit note (383)", lambda c: c["type_code"].get("383")),
             ("zero-rated (Z)", lambda c: c["vat_category"].get("Z")),
             ("exempt (E)", lambda c: c["vat_category"].get("E")),
             ("not subject to VAT (O)", lambda c: c["vat_category"].get("O")),
             ("export (transaction code position 5)", lambda c: c["export"].get("yes")),
             ("non-SAR currency", lambda c: any(k not in ("SAR", "(blank)") for k in c["currency"]))]
NOT_CHECKED = ["QR code, cryptographic stamp and the value of the previous invoice hash (never generated or verified here)",
               "prepayment invoices and prepayment adjustment lines (BR-KSA-73 to BR-KSA-80)",
               "document-level allowances and charges", "payment means codes", "the final UBL XML"]
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


def places(v):
    s = (v or "").strip()
    return len(s.split(".", 1)[1]) if "." in s else 0


def day(v):
    """A real date written YYYY-MM-DD, or None."""
    s = (v or "").strip()
    if not DATE.match(s):
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def money(d):
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def inv(r):
    return (r.get("invoice_number") or "").strip() or f"(row {r['_row']})"


def flags(r):
    """The transaction code (KSA-2) split into its parts, or None when it is not valid."""
    t = (r.get("transaction_code") or "").strip()
    if not TXN.match(t):
        return None
    return {"subtype": t[:2], "third_party": t[2] == "1", "nominal": t[3] == "1", "export": t[4] == "1",
            "summary": t[5] == "1", "self_billed": t[6] == "1"}


def check_row(r, cols):
    gaps = []

    def gap(field, rule, fix):
        gaps.append({"invoice": inv(r), "line": r.get("line_id", ""),
                     "field": field, "value": r.get(field, ""), "rule": rule, "fix": fix})

    get = lambda f: (r.get(f) or "").strip()
    for f, rule in REQUIRED:
        if not get(f):
            gap(f, rule, f"{f} is empty")
    for f in NUMERIC:
        if get(f) and dec(get(f)) is None:
            gap(f, "csv-number-format", "Use a plain number with the digits 0-9 and a dot: no commas, % or currency signs")
        elif get(f) and dec(get(f)) < 0:
            gap(f, "BR-KSA-F-04", "Amounts and quantities must be positive; credit notes carry positive amounts too")
    for f, rule in TWO_DECIMALS.items():
        if dec(get(f)) is not None and places(get(f)) > 2:
            gap(f, rule, "Use at most 2 decimal places")
    for f, n in MAX_CHARS.items():
        if len(get(f)) > n:
            gap(f, "BR-KSA-F-06", f"At most {n} characters")

    # Dates and times
    for f in ("issue_date", "supply_date", "supply_end_date"):
        if get(f) and day(get(f)) is None:
            gap(f, "BR-KSA-F-01", "Use a real date written YYYY-MM-DD, such as 2026-10-01")
    issued, start, end = day(get("issue_date")), day(get("supply_date")), day(get("supply_end_date"))
    if issued and issued > datetime.date.today():
        gap("issue_date", "BR-KSA-04", "The issue date cannot be later than today")
    if get("issue_time") and not TIME.match(get("issue_time")):
        gap("issue_time", "BR-KSA-70", "Use hh:mm:ss (Saudi time) or hh:mm:ssZ (UTC), such as 14:30:00")
    if end and not get("supply_date"):
        gap("supply_date", "BR-KSA-35", "A supply end date needs a supply date")
    if start and end and end < start:
        gap("supply_end_date", "BR-KSA-36", "The supply end date cannot be before the supply date")

    # Invoice type and transaction code
    t, cur = get("type_code"), get("currency")
    if t and t not in TYPE_CODES:
        gap("type_code", "BR-KSA-05", "Use 388 (invoice), 386 (prepayment), 383 (debit note) or 381 (credit note)")
    fl = flags(r)
    if get("transaction_code") and not fl:
        gap("transaction_code", "BR-KSA-06",
            "Use 7 characters of 0 and 1 starting 01 (tax invoice) or 02 (simplified), such as 0100000. "
            "If Excel dropped the leading 0, format the column as text")
    sub = fl["subtype"] if fl else None
    if fl and fl["export"] and fl["self_billed"]:
        gap("transaction_code", "BR-KSA-07", "Export invoices cannot be self-billed (positions 5 and 7 both 1)")
    if sub == "02" and (fl["export"] or fl["self_billed"]):
        gap("transaction_code", "BR-KSA-31", "Simplified invoices can flag only third party, nominal or summary")
    if t == "388" and sub == "01" and not get("supply_date"):
        gap("supply_date", "BR-KSA-15", "Tax invoices (388, subtype 01) need the supply date")
    if sub == "02" and fl["summary"]:
        if not get("buyer_name"):
            gap("buyer_name", "BR-KSA-71", "Simplified summary invoices need the buyer name")
        for f in ("supply_date", "supply_end_date"):
            if not get(f):
                gap(f, "BR-KSA-72", "Simplified summary invoices need a supply date and a supply end date")
    if t in NOTE_TYPES:
        if not get("preceding_invoice"):
            gap("preceding_invoice", "BR-KSA-56", "Credit and debit notes need the number of the original invoice")
        if not get("note_reason"):
            gap("note_reason", "BR-KSA-17", "Credit and debit notes need the reason they were issued")

    # Currency
    if cur and not CURRENCY.match(cur):
        gap("currency", "BR-CL-04", "Use the 3-letter ISO 4217 code in capitals, such as SAR or USD")
    if get("tax_currency") and get("tax_currency") != "SAR":
        gap("tax_currency", "BR-KSA-EN16931-02", "The tax currency must be SAR")
    if cur and cur != "SAR" and not get("invoice_total_vat_sar"):
        gap("invoice_total_vat_sar", "BR-53", "Invoices in another currency need the total VAT in SAR")

    # Seller
    if get("seller_vat") and not VAT_NO.match(get("seller_vat")):
        gap("seller_vat", "BR-KSA-40", "VAT number must be 15 digits, starting and ending with 3")
    if not get("seller_id") or get("seller_id_scheme") not in SELLER_SCHEMES or not ALNUM.match(get("seller_id")):
        gap("seller_id", "BR-KSA-08", "Give one seller ID (letters and digits only) with scheme CRN, MOM, MLS, 700, SAG or OTH")
    for f in SELLER_ADDRESS:
        if not get(f):
            gap(f, "BR-KSA-09", "The seller address needs street, building number, postal code, city, district and country")
    if get("seller_building_number") and not re.fullmatch(r"[0-9]{4}", get("seller_building_number")):
        gap("seller_building_number", "BR-KSA-37", "The seller building number must be 4 digits")
    if get("seller_postal_code") and not re.fullmatch(r"[0-9]{5}", get("seller_postal_code")):
        gap("seller_postal_code", "BR-KSA-66", "The seller postal code must be 5 digits")
    for f in ("seller_country", "buyer_country"):
        if get(f) and not COUNTRY.match(get(f)):
            gap(f, "BR-CL-14", "Use the 2-letter ISO 3166-1 code in capitals, such as SA")

    # Buyer
    export = bool(fl and fl["export"])
    if sub == "01":
        if not get("buyer_name"):
            gap("buyer_name", "BR-KSA-42", "Tax invoices and their notes need the buyer name")
        for f in ("buyer_street", "buyer_city", "buyer_country"):
            if not get(f):
                gap(f, "BR-KSA-10", "Tax invoices and their notes need the buyer street, city and country")
        if not get("buyer_vat") and not get("buyer_id"):
            gap("buyer_id", "BR-KSA-81", "Tax invoices need the buyer VAT number or another buyer ID (such as CRN or NAT)")
    if get("buyer_country") == "SA":
        for f in BUYER_SA_ADDRESS:
            if not get(f):
                gap(f, "BR-KSA-63", "Saudi buyers need street, building number, postal code, city, district and country")
        if get("buyer_postal_code") and not re.fullmatch(r"[0-9]{5}", get("buyer_postal_code")):
            gap("buyer_postal_code", "BR-KSA-67", "A Saudi buyer's postal code must be 5 digits")
    if get("buyer_vat"):
        if export:
            gap("buyer_vat", "BR-KSA-46", "Export invoices must not carry a buyer VAT number")
        elif not VAT_NO.match(get("buyer_vat")):
            gap("buyer_vat", "BR-KSA-44", "Buyer VAT number must be 15 digits, starting and ending with 3")
    if get("buyer_id") and (get("buyer_id_scheme") not in BUYER_SCHEMES or not ALNUM.match(get("buyer_id"))):
        gap("buyer_id", "BR-KSA-14",
            "Buyer ID: letters and digits only, with scheme TIN, CRN, MOM, MLS, 700, SAG, NAT, GCC, IQA, PAS or OTH")

    # VAT category, rate and exemption reason
    cat, reason = get("vat_category"), get("exemption_reason")
    rate = dec(get("vat_rate"))
    if cat and cat not in VAT_CATEGORIES:
        gap("vat_category", "BR-KSA-18", "Use S, Z, E or O (capitals)")
    if rate is not None and (rate > 100 or places(get("vat_rate")) > 2):
        gap("vat_rate", "BR-KSA-DEC-02", "VAT rate is 0 to 100 with at most 2 decimals, without %")
    if cat in {"S", "Z", "E"} and not get("vat_rate"):
        gap("vat_rate", "BR-48", f"Category {cat} lines need a VAT rate")
    for c, rule in (("Z", "BR-Z-05"), ("E", "BR-E-05"), ("O", "BR-KSA-11")):
        if cat == c and rate not in (None, Decimal(0)):
            gap("vat_rate", rule, f"Category {c} lines have VAT rate 0")
    if cat == "S" and reason:
        gap("exemption_reason", "BR-S-10", "Standard-rated (S) lines must not carry an exemption reason")
    for c, rule in (("E", "BR-KSA-23"), ("Z", "BR-KSA-69"), ("O", "BR-KSA-24")):
        if cat == c and not reason:
            gap("exemption_reason", rule, f"Category {c} lines need a VATEX-SA exemption or exception reason code")
    if cat in EXEMPTION_CODES and reason and reason not in EXEMPTION_CODES[cat]:
        gap("exemption_reason", "BR-KSA-CL-04", f"Use a code listed for category {cat}: {', '.join(sorted(EXEMPTION_CODES[cat]))}")
    if reason in CITIZEN_CODES:
        if get("buyer_id_scheme") != "NAT" or not get("buyer_id"):
            gap("buyer_id", "BR-KSA-49", "VATEX-SA-EDU and VATEX-SA-HEA need the buyer's national ID (scheme NAT)")
        if sub == "02" and not get("buyer_name"):
            gap("buyer_name", "BR-KSA-25", "Simplified invoices with VATEX-SA-EDU or VATEX-SA-HEA need the buyer name")

    # Line VAT and line maths
    net, vat, with_vat = dec(get("line_net")), dec(get("line_vat")), dec(get("line_amount_with_vat"))
    if sub == "01" and not get("line_vat"):
        gap("line_vat", "BR-KSA-52", "Tax invoices and their notes need the VAT amount on every line")
    if None not in (net, vat, with_vat) and abs(net + vat - with_vat) > Decimal(0):
        gap("line_amount_with_vat", "BR-KSA-51", f"line_net + line_vat = {net + vat}, not {with_vat}")
    q, p = dec(get("quantity")), dec(get("unit_price"))
    base = dec(get("base_quantity")) if get("base_quantity") else Decimal(1)
    if base is not None and base <= 0:
        gap("base_quantity", "BR-KSA-EN16931-12", "Base quantity must be more than 0; leave it empty for 1")
    allow, charge = dec(get("line_allowance")) or Decimal(0), dec(get("line_charge")) or Decimal(0)
    if None not in (q, p, net, base) and base > 0:
        want = money(q * (p / base)) + charge - allow
        if abs(want - net) > CENT:
            gap("line_net", "BR-KSA-EN16931-11", f"quantity x price / base quantity + charges - allowances = {want:.2f}, not {net}")
    if charge > 0:
        if not get("line_charge_reason_code"):
            gap("line_charge_reason_code", "BR-KSA-20", "A line charge needs a reason code (UNTDID 7161)")
        if not get("line_charge_reason"):
            gap("line_charge_reason", "BR-KSA-22", "A line charge needs a reason in words")

    # Phase 2 (integration) fields: presence and simple shape only, when the file has the column
    if "uuid" in cols and (not get("uuid") or not UUID_CHARS.match(get("uuid"))):
        gap("uuid", "BR-KSA-03", "Each invoice needs a UUID of letters, digits and dashes")
    if "invoice_counter" in cols and not get("invoice_counter"):
        gap("invoice_counter", "BR-KSA-33", "Each invoice needs an invoice counter value")
    elif get("invoice_counter") and not DIGITS.match(get("invoice_counter")):
        gap("invoice_counter", "BR-KSA-34", "The invoice counter value has digits only")
    if "previous_invoice_hash" in cols and not get("previous_invoice_hash"):
        gap("previous_invoice_hash", "BR-KSA-61", "Each invoice needs the previous invoice hash (this check does not verify it)")
    return gaps


def norm(f, v):
    """A header value as compared across lines: trimmed, codes in capitals, numbers by value."""
    v = (v or "").strip()
    if f in CODE_FIELDS:
        return v.upper()
    return dec(v) if f in NUMERIC and dec(v) is not None else v


def check_invoices(rows):
    """Per-invoice checks: header fields that differ between lines, VAT breakdown, totals and warnings."""
    gaps, warnings, by_inv, uuids = [], [], defaultdict(list), defaultdict(dict)
    for r in rows:
        by_inv[inv(r)].append(r)
    for i, lines in by_inv.items():
        for f in HEADER:
            seen = {norm(f, r.get(f)): True for r in lines}
            if len(seen) > 1:
                gaps.append({"invoice": i, "line": "", "field": f, "value": " | ".join(str(k) or "(blank)" for k in seen),
                             "rule": "csv-header-mismatch", "fix": f"Lines of one invoice must agree on {f}"})
        r = lines[0]
        u = (r.get("uuid") or "").strip()
        if u:
            uuids[u][i] = True
        breakdown, vat_gaps = vat_breakdown(i, lines)
        gaps += vat_gaps + check_totals(i, r, lines, breakdown)
        fl = flags(r)
        net = sum_of(lines, "line_net")
        if (fl and fl["subtype"] == "02" and (r.get("buyer_vat") or "").strip()
                and (r.get("currency") or "").strip() == "SAR" and net is not None and net >= 1000):
            warnings.append({"invoice": i, "field": "transaction_code", "rule": "guideline-4.2.1",
                             "note": "Simplified invoice to a VAT-registered buyer for SAR 1,000 or more: the ZATCA "
                                     "guideline allows simplified B2B invoices only below SAR 1,000. Confirm the subtype"})
    for u, invs in uuids.items():
        if len(invs) > 1:
            for i in invs:
                gaps.append({"invoice": i, "line": "", "field": "uuid", "value": u, "rule": "BR-KSA-03",
                             "fix": "Each invoice needs its own UUID; this one is shared with another invoice"})
    return gaps, warnings


def sum_of(lines, f):
    """Sum of one column over lines, or None when any value is blank or unreadable."""
    vals = [dec(x.get(f)) for x in lines]
    return None if None in vals else sum(vals, Decimal(0))


def vat_breakdown(i, lines):
    """One VAT breakdown per category and rate (XML Implementation Standard 9.6): tax = taxable x rate / 100,
    rounded half up. The lines' VAT in each group must add up to it (each line is rounded, so allow 0.005 a line)."""
    groups = defaultdict(list)
    for x in lines:
        cat = (x.get("vat_category") or "").strip()
        rate = dec(x.get("vat_rate")) if (x.get("vat_rate") or "").strip() else Decimal(0)
        if cat in VAT_CATEGORIES and rate is not None:
            groups[(cat, rate)].append(x)
    breakdown, gaps = {}, []
    for (cat, rate), xs in groups.items():
        taxable = sum_of(xs, "line_net")
        if taxable is None:
            breakdown = None
            continue
        tax = money(taxable * rate / 100)
        if breakdown is not None:
            breakdown[(cat, rate)] = tax
        got = sum_of(xs, "line_vat")  # skipped when a line has no VAT amount (optional on simplified invoices)
        if got is not None and abs(got - tax) > max(CENT, Decimal("0.005") * len(xs)):
            rule = {"S": "BR-S-09", "Z": "BR-Z-09", "E": "BR-E-09", "O": "BR-O-09"}[cat]
            gaps.append({"invoice": i, "line": "", "field": "line_vat", "value": str(got), "rule": rule,
                         "fix": f"Category {cat} at {rate}%: taxable {taxable:.2f} x rate = VAT {tax}, but the lines add up to {got}"})
    return breakdown, gaps


def check_totals(i, r, lines, breakdown):
    """Optional invoice_total_* columns, compared with the lines and the VAT breakdown."""
    gaps = []
    net = sum_of(lines, "line_net")
    vat = None if not breakdown else sum(breakdown.values(), Decimal(0))
    got_net, got_vat, got_gross = (dec(r.get(f)) for f in ("invoice_total_net", "invoice_total_vat", "invoice_total_gross"))
    use_net = got_net if got_net is not None else net
    use_vat = got_vat if got_vat is not None else vat
    gross = None if None in (use_net, use_vat) else use_net + use_vat
    for f, got, want, rule in (("invoice_total_net", got_net, net, "BR-CO-13"),
                               ("invoice_total_vat", got_vat, vat, "BR-CO-14"),
                               ("invoice_total_gross", got_gross, gross, "BR-CO-15")):
        if None not in (got, want) and abs(got - want) > CENT:
            gaps.append({"invoice": i, "line": "", "field": f, "value": r.get(f, ""), "rule": rule,
                         "fix": f"Should be {want:.2f} from the lines and VAT breakdown, not {got}"})
    return gaps


def mask(v):
    v = str(v)
    if v == "(blank)":
        return v
    return "*" * max(len(v) - 4, 0) + v[-4:] if len(v) > 4 else "*" * len(v)


def summary(out):
    text = [f"Checked {out['lines']} lines in {out['invoices']} invoices ({out['file_encoding']}).",
            f"Invoices with gaps: {out['invoices_with_gaps']} of {out['invoices']}. Gaps: {out['gaps_total']}."]
    text += ["Top rules:"] if out["by_rule"] else []
    text += [f"  {b['rule']}: {b['gaps']} gap(s) in {b['invoices']} invoice(s)" for b in out["by_rule"][:10]]
    missing = out["coverage"]["not_in_sample"]
    text.append("Not in this sample: " + (", ".join(missing) if missing else "none of the common cases are missing"))
    if out["phase2_columns_missing"]:
        text.append("Phase 2 columns not in the file (not checked): " + ", ".join(out["phase2_columns_missing"]))
    text.append(f"Warnings (not gaps): {len(out['warnings'])}")
    text.append("Data pre-check only: validate the final XML with ZATCA's SDK or the Fatoora portal.")
    return "\n".join(text)


def collapse_missing(gaps, cols):
    """A column absent from the file gets one gap per rule, with "(all)" for the invoice, not one gap per invoice.
    Gaps on cells that are there but blank or wrong stay per invoice."""
    seen, out = {}, []
    for g in gaps:
        if g["field"] in cols:
            out.append(g)
        elif (g["field"], g["rule"]) not in seen:
            seen[(g["field"], g["rule"])] = True
            fix = "" if g["fix"] == f"{g['field']} is empty" else ". " + g["fix"]
            out.append({**g, "invoice": "(all)", "line": "", "value": "", "fix": "column missing from the file" + fix})
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
    c = {k: defaultdict(int) for k in ("type_code", "subtype", "vat_category", "currency", "export")}
    first = {}
    for r in rows:
        first.setdefault(inv(r), r)
        c["vat_category"][(r.get("vat_category") or "").strip() or "(blank)"] += 1
    for r in first.values():
        fl = flags(r)
        c["type_code"][(r.get("type_code") or "").strip() or "(blank)"] += 1
        c["subtype"][fl["subtype"] if fl else "(blank or invalid)"] += 1
        c["currency"][(r.get("currency") or "").strip().upper() or "(blank)"] += 1
        c["export"]["yes" if fl and fl["export"] else "no"] += 1
    return {"invoices_by_type_code": dict(c["type_code"]), "invoices_by_subtype": dict(c["subtype"]),
            "lines_by_vat_category": dict(c["vat_category"]), "invoices_by_currency": dict(c["currency"]),
            "not_in_sample": [n for n, has in SCENARIOS if not has(c)]}


def load(path):
    # cp1256 (Arabic Windows) decodes any bytes, so it is the last try; save other files as UTF-8.
    with open(path, "rb") as fh:
        utf16 = fh.read(2) in (b"\xff\xfe", b"\xfe\xff")
    for enc in ("utf-16",) if utf16 else ("utf-8-sig", "cp1256"):
        try:
            with open(path, newline="", encoding=enc) as fh:
                reader = csv.DictReader(fh)
                names = [k for k in ((n or "").strip().lower() for n in reader.fieldnames or []) if k]
                twice = sorted({k for k in names if names.count(k) > 1})
                if twice:
                    raise ValueError(f"these columns appear twice (headers ignore case and spaces): {', '.join(twice)}")
                rows = []
                for i, raw in enumerate(reader, start=2):
                    if not any(isinstance(v, str) and v.strip() for v in raw.values()):
                        continue  # a row of empty cells (",,,")
                    row = {k.strip().lower(): (v if isinstance(v, str) else "") for k, v in raw.items() if (k or "").strip()}
                    row["_row"] = i
                    rows.append(row)
                return rows, enc, names
        except UnicodeError:
            continue
    raise ValueError("could not read the file's text encoding")


def main(argv):
    ap = argparse.ArgumentParser(prog="check_ksa.py", allow_abbrev=False,
                                 description="Saudi (ZATCA) e-invoice data pre-check. Reads a CSV of invoice lines.")
    ap.add_argument("path", help="CSV of invoice lines")
    ap.add_argument("--all", action="store_true", help=f"list every gap, not only the first {SHOWN}")
    ap.add_argument("--mask", action="store_true", help="hide all but the last 4 characters of VAT numbers and other IDs")
    ap.add_argument("--summary", action="store_true", help="print a short text summary instead of JSON")
    a = ap.parse_args(argv[1:])
    try:
        rows, enc, cols = load(a.path)
    except (OSError, ValueError, csv.Error) as e:
        print(f"could not check {a.path}: {e}", file=sys.stderr)
        return 2
    if not rows:
        print(f"{a.path} has no invoice lines, so nothing was checked", file=sys.stderr)
        return 2
    inv_gaps, warnings = check_invoices(rows)
    gaps = dedupe([g for r in rows for g in check_row(r, cols)]) + inv_gaps
    invoices_by_rule = defaultdict(dict)
    for g in gaps:  # counted before collapse_missing, so "(all)" gaps still count every invoice they hit
        invoices_by_rule[g["rule"]][g["invoice"]] = True
    with_gaps = len({g["invoice"] for g in gaps})
    gaps = collapse_missing(gaps, cols)
    by_rule = defaultdict(int)
    for g in gaps:
        by_rule[g["rule"]] += 1
    invoices = {inv(r) for r in rows}
    shown = gaps if a.all else gaps[:SHOWN]
    if a.mask:
        shown = [{**g, "value": " | ".join(mask(x) for x in str(g["value"]).split(" | "))} if g["field"] in MASKED else g
                 for g in shown]
    out = {
        "file_encoding": enc, "lines": len(rows), "invoices": len(invoices),
        "invoices_with_gaps": with_gaps,
        "gaps_total": len(gaps), "gaps_shown": len(shown), "truncated": len(shown) < len(gaps),
        "by_rule": [{"rule": k, "gaps": v, "invoices": len(invoices_by_rule[k])}
                    for k, v in sorted(by_rule.items(), key=lambda kv: -kv[1])],
        "coverage": coverage(rows), "warnings": warnings,
        "phase2_columns_missing": [c for c in PHASE2 if c not in cols],
        "not_checked": NOT_CHECKED,
        "gaps": shown}
    print(summary(out) if a.summary else json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
