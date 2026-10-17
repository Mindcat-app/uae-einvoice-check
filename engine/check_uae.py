"""UAE e-invoice data checks for CSV exports (one row per invoice line).

Each check names the PINT AE v1.0.4 rule it mirrors (ibr-... or aligned-..., from the official Schematron;
the README links the source). Checks with an "mc-" id are our own
data-quality checks with no single Schematron rule. This is a pre-check on source data, not a
replacement for validating the final UBL XML, and not tax advice.

Usage: python3 -I check_uae.py invoices.csv [--all]
Exit codes: 0 no gaps, 1 gaps found, 2 the file could not be checked.
"""
import csv
import datetime
import json
import re
import sys
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
           "vat_rate", "line_vat", "line_net_aed", "exchange_rate"]
# Every invoice-level field must be listed here: gaps on these are reported once per invoice (see dedupe).
HEADER = ["invoice_number", "issue_date", "type_code", "currency", "exchange_rate", "seller_name", "seller_trn",
          "seller_tin", "seller_emirate", "seller_country", "buyer_name", "buyer_trn", "buyer_emirate",
          "buyer_country", "preceding_invoice", "credit_reason"]
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
CODE_FIELDS = ["type_code", "currency", "seller_emirate", "seller_country", "buyer_emirate", "buyer_country", "credit_reason"]
UNIT = re.compile(r"^[A-Z0-9]{2,3}$")
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

    # Buyer: UAE rules apply only when the buyer is in the UAE (blank country is read as AE)
    if get("buyer_country").upper() in ("", "AE"):
        if get("buyer_trn") and not TRN.match(get("buyer_trn")):
            gap("buyer_trn", "ibr-132-ae", "Buyer TRN must be 15 digits, start with 1 and end with 03")
        if get("buyer_emirate") and get("buyer_emirate") not in EMIRATES:
            gap("buyer_emirate", "ibr-128-ae", "Use AUH, DXB, SHJ, UAQ, FUJ, AJM or RAK (capitals)")

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
    if cat in {"S", "Z", "N"} and None not in (net, rate, vat) and abs(net * rate / 100 - vat) > Decimal("0.01"):
        gap("line_vat", "mc-vat-maths", f"net x rate = {net * rate / 100:.2f}, not {vat}")

    # Line maths: qty x (price / base qty) + charges - allowances
    q, p = dec(get("quantity")), dec(get("unit_price"))
    base = dec(get("base_quantity")) if get("base_quantity") else Decimal(1)
    if base is not None and base <= 0:
        gap("base_quantity", "mc-base-quantity", "Base quantity must be more than 0; leave it empty for 1")
    allow, charge = dec(get("line_allowance")) or Decimal(0), dec(get("line_charge")) or Decimal(0)
    if None not in (q, p, net, base) and base != 0:
        want = q * (p / base) + charge - allow
        if abs(want - net) > Decimal("0.01"):
            gap("line_net", "ibr-147-ae", f"quantity x price / base quantity + charges - allowances = {want:.2f}, not {net}")

    # Currency
    if cur and cur != "AED":
        if not get("exchange_rate"):
            gap("exchange_rate", "ibr-159-ae", "Non-AED invoices need the exchange rate to AED")
        if cat != "E" and not get("line_net_aed"):
            gap("line_net_aed", "ibr-104-ae", "Non-AED invoices need each line's amount in AED")
        fx, aed = dec(get("exchange_rate")), dec(get("line_net_aed"))
        if None not in (net, fx, aed) and abs(net * fx - aed) > Decimal("0.01"):
            gap("line_net_aed", "mc-aed-maths", f"line_net x exchange_rate (AED per 1 {cur}) = {net * fx:.2f}, not {aed}")

    # Unit of measure (UN/ECE Rec 20)
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
    return gaps


def norm(f, v):
    """A header value as compared across lines: trimmed, codes in capitals, numbers by value."""
    v = (v or "").strip()
    if f in CODE_FIELDS:
        return v.upper()
    return dec(v) if f in NUMERIC and dec(v) is not None else v


def check_invoices(rows):
    """Per-invoice checks: header fields that differ between lines, and warnings that are not gaps."""
    gaps, warnings, by_inv = [], [], defaultdict(list)
    for r in rows:
        by_inv[inv(r)].append(r)
    for i, lines in by_inv.items():
        for f in HEADER:
            seen = {norm(f, r.get(f)): True for r in lines}
            if len(seen) > 1:
                gaps.append({"invoice": i, "line": "", "field": f, "value": " | ".join(str(k) or "(blank)" for k in seen),
                             "rule": "mc-header-mismatch", "fix": f"Lines of one invoice must agree on {f}"})
        r = lines[0]
        if ((r.get("buyer_country") or "").strip().upper() in ("", "AE") and not (r.get("buyer_trn") or "").strip()
                and any((x.get("vat_category") or "").strip() == "S" for x in lines)):
            warnings.append({"invoice": i, "field": "buyer_trn", "rule": "mc-buyer-trn-blank",
                             "note": "UAE buyer with no TRN on a standard-rated invoice: fine for a consumer, a gap for a VAT-registered business"})
    return gaps, warnings


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


def load(path):
    # cp1256 (Arabic Windows) decodes any bytes, so it is the last try; save other files as UTF-8.
    for enc in ("utf-8-sig", "cp1256"):
        try:
            with open(path, newline="", encoding=enc) as fh:
                reader = csv.DictReader(fh)
                names = [k for k in ((n or "").strip().lower() for n in reader.fieldnames or []) if k]
                twice = sorted({k for k in names if names.count(k) > 1})
                if twice:
                    raise ValueError(f"these columns appear twice (headers ignore case and spaces): {', '.join(twice)}")
                rows = []
                for i, raw in enumerate(reader, start=2):
                    row = {k.strip().lower(): (v if isinstance(v, str) else "") for k, v in raw.items() if (k or "").strip()}
                    row["_row"] = i
                    rows.append(row)
                return rows, enc
        except UnicodeDecodeError:
            continue
    raise ValueError("could not read the file's text encoding")


def main(argv):
    if len(argv) < 2:
        print("usage: python3 -I check_uae.py invoices.csv [--all]", file=sys.stderr)
        return 2
    try:
        rows, enc = load(argv[1])
    except (OSError, ValueError, csv.Error) as e:
        print(f"could not check {argv[1]}: {e}", file=sys.stderr)
        return 2
    if not rows:
        print(f"{argv[1]} has no invoice lines, so nothing was checked", file=sys.stderr)
        return 2
    inv_gaps, warnings = check_invoices(rows)
    gaps = dedupe([g for r in rows for g in check_row(r)]) + inv_gaps
    by_rule, invoices_by_rule = defaultdict(int), defaultdict(dict)
    for g in gaps:
        by_rule[g["rule"]] += 1
        invoices_by_rule[g["rule"]][g["invoice"]] = True
    invoices = {inv(r) for r in rows}
    shown = gaps if "--all" in argv else gaps[:SHOWN]
    print(json.dumps({
        "file_encoding": enc, "lines": len(rows), "invoices": len(invoices),
        "invoices_with_gaps": len({g["invoice"] for g in gaps}),
        "gaps_total": len(gaps), "gaps_shown": len(shown), "truncated": len(shown) < len(gaps),
        "by_rule": [{"rule": k, "gaps": v, "invoices": len(invoices_by_rule[k])}
                    for k, v in sorted(by_rule.items(), key=lambda kv: -kv[1])],
        "coverage": coverage(rows), "warnings": warnings,
        "gaps": shown}, indent=2, ensure_ascii=False, default=str))
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
