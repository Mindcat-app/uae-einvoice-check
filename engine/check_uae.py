"""UAE e-invoice data checks for CSV exports (one row per invoice line).

Each check names the PINT AE v1.0.4 rule it mirrors (ibr-...-ae, from the official Schematron in
https://docs.peppol.eu/poac/ae/pint-ae/resources.zip). Checks with an "mc-" id are our own
data-quality checks with no single Schematron rule. This is a pre-check on source data, not a
replacement for validating the final UBL XML, and not tax advice.

Usage: python3 -I check_uae.py invoices.csv [--all]
Exit codes: 0 no gaps, 1 gaps found, 2 the file could not be checked.
"""
import csv
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
ITEM_KINDS = {"goods": "G", "g": "G", "service": "S", "services": "S", "s": "S", "both": "B", "b": "B"}
REQUIRED = ["invoice_number", "issue_date", "type_code", "currency", "seller_name", "buyer_name",
            "line_id", "item_name", "quantity", "unit_price", "line_net", "vat_category"]
NUMERIC = ["quantity", "unit_price", "base_quantity", "line_allowance", "line_charge", "line_net",
           "vat_rate", "line_vat", "line_net_aed", "exchange_rate"]
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


def check_row(r):
    gaps = []

    def gap(field, rule, fix):
        gaps.append({"invoice": r.get("invoice_number", "") or f"(row {r['_row']})", "line": r.get("line_id", ""),
                     "field": field, "value": r.get(field, ""), "rule": rule, "fix": fix})

    get = lambda f: (r.get(f) or "").strip()
    for f in REQUIRED:
        if not get(f):
            gap(f, "mc-missing", f"{f} is empty")
    for f in NUMERIC:
        if get(f) and dec(get(f)) is None:
            gap(f, "mc-number-format", "Use a plain number: digits and a dot, no commas, % or currency signs")

    t, cat, cur = get("type_code"), get("vat_category"), get("currency").upper()
    if t and t not in INVOICE_TYPES | CREDIT_TYPES:
        gap("type_code", "ibr-cl-01", "Invoice type must be 380 or 480; credit note 381 or 81")
    if t in CREDIT_TYPES and not get("preceding_invoice") and get("credit_reason") != "VD":
        gap("preceding_invoice", "ibr-055-ae", "Credit notes need the original invoice number")
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
        if not get("buyer_trn"):
            gap("buyer_trn", "ibr-103-ae", "Reverse-charge (AE) lines need the buyer's TRN")
        if vat not in (None, Decimal(0)):
            gap("line_vat", "mc-reverse-charge-vat", "Reverse-charge lines carry 0 VAT; the buyer accounts for it")
    if cat in {"S", "Z", "N"} and None not in (net, rate, vat) and abs(net * rate / 100 - vat) > Decimal("0.01"):
        gap("line_vat", "mc-vat-maths", f"net x rate = {net * rate / 100:.2f}, not {vat}")

    # Line maths: qty x (price / base qty) + charges - allowances
    q, p = dec(get("quantity")), dec(get("unit_price"))
    base = dec(get("base_quantity")) or Decimal(1)
    allow, charge = dec(get("line_allowance")) or Decimal(0), dec(get("line_charge")) or Decimal(0)
    if None not in (q, p, net) and base != 0:
        want = q * (p / base) + charge - allow
        if abs(want - net) > Decimal("0.01"):
            gap("line_net", "ibr-147-ae", f"quantity x price / base quantity + charges - allowances = {want:.2f}, not {net}")

    # Currency
    if cur and cur != "AED":
        if not get("exchange_rate"):
            gap("exchange_rate", "ibr-159-ae", "Non-AED invoices need the exchange rate to AED")
        if cat != "E" and not get("line_net_aed"):
            gap("line_net_aed", "ibr-104-ae", "Non-AED invoices need each line's amount in AED")

    # Item codes
    kind = ITEM_KINDS.get(get("item_kind").lower())
    if get("item_kind") and not kind:
        gap("item_kind", "mc-item-kind", "Use goods, service or both")
    if kind in {"G", "B"} and not get("hs_code"):
        gap("hs_code", "mc-item-code", "Goods need an HS code")
    if kind in {"S", "B"} and not get("sac_code"):
        gap("sac_code", "mc-item-code", "Services need a SAC code")
    return gaps


def load(path):
    for enc in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            with open(path, newline="", encoding=enc) as fh:
                reader = csv.DictReader(fh)
                rows = []
                for i, raw in enumerate(reader, start=2):
                    row = {(k or "").strip().lower(): (v if isinstance(v, str) else "") for k, v in raw.items()}
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
    gaps = [g for r in rows for g in check_row(r)]
    by_rule, invoices_by_rule = defaultdict(int), defaultdict(set)
    for g in gaps:
        by_rule[g["rule"]] += 1
        invoices_by_rule[g["rule"]].add(g["invoice"])
    invoices = {r.get("invoice_number") or f"(row {r['_row']})" for r in rows}
    shown = gaps if "--all" in argv else gaps[:SHOWN]
    print(json.dumps({
        "file_encoding": enc, "lines": len(rows), "invoices": len(invoices),
        "invoices_with_gaps": len({g["invoice"] for g in gaps}),
        "gaps_total": len(gaps), "gaps_shown": len(shown), "truncated": len(shown) < len(gaps),
        "by_rule": [{"rule": k, "gaps": v, "invoices": len(invoices_by_rule[k])}
                    for k, v in sorted(by_rule.items(), key=lambda kv: -kv[1])],
        "gaps": shown}, indent=2, ensure_ascii=False, default=str))
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
