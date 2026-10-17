"""UAE e-invoice data checks for CSV exports (one row per invoice line).

Each check names the PINT AE v1.0.4 rule it mirrors (ibr-...-ae or aligned-ibrp-...-ae, from the
official Schematron; the README links the source). Checks with an "mc-" id are our own
data-quality checks with no single Schematron rule. This is a pre-check on source data, not a
replacement for validating the final UBL XML, and not tax advice.

Gaps are things to fix. Warnings are things the CSV alone cannot decide (for example a blank
buyer TRN, which is fine for a consumer but not for a VAT-registered business).

Usage: python3 -I check_uae.py invoices.csv [--all] [--summary] [--mask]
  --all      list every gap and warning, not the first 50
  --summary  print a short text summary instead of JSON
  --mask     hide the middle digits of TRNs and TINs in the output
Exit codes: 0 no gaps, 1 gaps found, 2 the file could not be checked.
"""
import csv
import io
import json
import re
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

TRN = re.compile(r"^1[0-9]{12}03$")
TIN = re.compile(r"^1[0-9]{9}$")
ISO_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
UNIT_CODE = re.compile(r"^[A-Z0-9]{2,3}$")
EMIRATES = {"AUH", "DXB", "SHJ", "UAQ", "FUJ", "AJM", "RAK"}
INVOICE_TYPES, CREDIT_TYPES = {"380", "480"}, {"381", "81"}
OUT_OF_SCOPE_TYPES = {"480", "81"}
VAT_CATEGORIES = {"S", "Z", "E", "O", "AE", "N"}
ITEM_KINDS = {"goods": "G", "g": "G", "service": "S", "services": "S", "s": "S", "both": "B", "b": "B"}
REQUIRED = ["invoice_number", "issue_date", "type_code", "currency", "seller_name", "buyer_name",
            "line_id", "item_name", "quantity", "unit_price", "line_net", "vat_category"]
NUMERIC = ["quantity", "unit_price", "base_quantity", "line_allowance", "line_charge", "line_net",
           "vat_rate", "line_vat", "line_net_aed", "exchange_rate", "invoice_total_net", "invoice_total_vat"]
# Invoice-level fields. A CSV repeats them on every line, so gaps on them are reported once per
# invoice, and lines of one invoice that disagree on them are a gap of their own.
HEADER = ["issue_date", "type_code", "currency", "exchange_rate", "seller_trn", "seller_tin",
          "seller_name", "seller_country", "seller_emirate", "buyer_name", "buyer_trn", "buyer_country",
          "buyer_emirate", "preceding_invoice", "credit_reason", "invoice_total_net", "invoice_total_vat"]
TAX_IDS = ["seller_trn", "seller_tin", "buyer_trn"]
# Fields that tell two different invoices apart when they share one invoice number.
IDENTITY = ["seller_trn", "seller_tin", "seller_name", "issue_date"]
ARABIC_WORD = re.compile(r"[\u0621-\u064A]{3,}")
SHOWN = 50
CONTACT = "Want help fixing these before your provider goes live? Email apps@mindcat.ai (Dubai +971 4 266 2348)."


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


def invoice_key(r):
    return (r.get("invoice_number") or "").strip() or f"(row {r['_row']})"


def check_row(r):
    """Returns (gaps, warnings) for one invoice line."""
    gaps, warnings = [], []

    def item(field, rule, fix):
        return {"invoice": invoice_key(r), "line": r.get("line_id", ""),
                "field": field, "value": r.get(field, ""), "rule": rule, "fix": fix}

    def gap(field, rule, fix):
        gaps.append(item(field, rule, fix))

    get = lambda f: (r.get(f) or "").strip()
    for f in REQUIRED:
        if not get(f):
            gap(f, "mc-missing", f"{f} is empty")
    for f in NUMERIC:
        if get(f) and dec(get(f)) is None:
            gap(f, "mc-number-format", "Use a plain number: digits and a dot, no commas, % or currency signs")

    issued = get("issue_date")
    if issued:
        try:
            ok = bool(ISO_DATE.match(issued)) and bool(date.fromisoformat(issued))
        except ValueError:
            ok = False
        if not ok:
            gap("issue_date", "mc-issue-date", "Use YYYY-MM-DD")

    t, cat, cur = get("type_code"), get("vat_category"), get("currency").upper()
    if t and t not in INVOICE_TYPES | CREDIT_TYPES:
        gap("type_code", "ibr-cl-01", "Invoice type must be 380 or 480; credit note 381 or 81")
    if t in CREDIT_TYPES and not get("credit_reason"):
        gap("credit_reason", "ibr-158-ae", "Credit notes need a credit note reason code (BTAE-03)")
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
        if not get("buyer_trn") and cat != "AE":
            warnings.append(item("buyer_trn", "mc-buyer-trn-missing",
                                 "Buyer TRN is blank. Fine for a consumer, but a B2B buyer registered "
                                 "for VAT needs its TRN on the invoice"))

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
        if rate != 0:
            gap("vat_rate", "aligned-ibrp-ae-05", "Reverse-charge (AE) lines must have VAT rate 0")
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
    if None not in (q, p, net, base) and base > 0:
        want = q * (p / base) + charge - allow
        if abs(want - net) > Decimal("0.01"):
            gap("line_net", "ibr-147-ae", f"quantity x price / base quantity + charges - allowances = {want:.2f}, not {net}")

    # Unit of measure (BT-130, UN/ECE Rec 20). Checked only when the file has the column.
    if "unit_code" in r:
        if not get("unit_code"):
            gap("unit_code", "mc-unit-code", "Give the unit of measure as a UN/ECE Rec 20 code, such as EA, HUR or DAY")
        elif not UNIT_CODE.match(get("unit_code")):
            gap("unit_code", "mc-unit-code", "Unit code must be 2 or 3 capitals or digits (UN/ECE Rec 20), such as EA, HUR or DAY")

    # Currency
    if cur and cur != "AED":
        if not get("exchange_rate"):
            gap("exchange_rate", "ibr-159-ae", "Non-AED invoices need the exchange rate to AED")
        if cat != "E" and not get("line_net_aed"):
            gap("line_net_aed", "ibr-104-ae", "Non-AED invoices need each line's amount in AED")
        xr, net_aed = dec(get("exchange_rate")), dec(get("line_net_aed"))
        if None not in (xr, net_aed, net):
            want = net * xr
            tolerance = max(Decimal("0.01"), abs(net) * Decimal("0.0001"))
            if abs(want - net_aed) > tolerance:
                gap("line_net_aed", "mc-fx-maths", f"line_net x exchange_rate = {want:.2f}, not {net_aed}")

    # Item codes
    kind = ITEM_KINDS.get(get("item_kind").lower())
    if get("item_kind") and not kind:
        gap("item_kind", "mc-item-kind", "Use goods, service or both")
    if kind == "G" and not get("hs_code"):
        gap("hs_code", "ibr-184-ae", "Goods need an item classification code (HS code)")
    if kind == "S" and not get("sac_code"):
        gap("sac_code", "ibr-185-ae", "Services need a service accounting code (SAC)")
    if kind == "B":
        for f in ("hs_code", "sac_code"):
            if not get(f):
                gap(f, "ibr-186-ae", "Items that are both goods and services need an HS code and a SAC code")
    return gaps, warnings


def once_per_invoice(items):
    """Keeps one gap per invoice, field and rule for header fields; line fields are kept as they are."""
    seen, out = {}, []
    for g in items:
        if g["field"] in HEADER:
            key = (g["invoice"], g["field"], g["rule"])
            if key in seen:
                continue
            seen[key] = True
        out.append(g)
    return out


def group_lines(rows):
    groups = defaultdict(list)
    for r in rows:
        if (r.get("invoice_number") or "").strip():
            groups[invoice_key(r)].append(r)
    return groups


def check_invoices(groups, columns):
    """Checks across the lines of one invoice: header fields that disagree, and optional totals."""
    gaps = []
    for inv, lines in groups.items():
        identities = list(dict.fromkeys(" / ".join((r.get(f) or "").strip() for f in IDENTITY) for r in lines))
        if len(identities) > 1:
            gaps.append({"invoice": inv, "line": "", "field": "invoice_number", "value": inv,
                         "rule": "mc-duplicate-invoice",
                         "fix": "Different invoices (seller or issue date differ) share this number. Give each invoice "
                                "its own number in the file; header and totals checks are skipped for it"})
            continue
        for f in HEADER:
            values = list(dict.fromkeys((r.get(f) or "").strip() for r in lines))
            if len(values) > 1:
                gaps.append({"invoice": inv, "line": "", "field": f, "value": " | ".join(values),
                             "rule": "mc-header-mismatch", "fix": f"All lines of one invoice must carry the same {f}"})
        for total_col, line_col in (("invoice_total_net", "line_net"), ("invoice_total_vat", "line_vat")):
            if total_col not in columns:
                continue
            total = next((dec(r.get(total_col)) for r in lines if (r.get(total_col) or "").strip()), None)
            parts = [dec(r.get(line_col)) if (r.get(line_col) or "").strip() else Decimal(0) for r in lines]
            if total is None or None in parts:
                continue
            got = sum(parts, Decimal(0))
            if abs(got - total) > Decimal("0.01") * len(lines):
                gaps.append({"invoice": inv, "line": "", "field": total_col, "value": lines[0].get(total_col, ""),
                             "rule": "mc-totals", "fix": f"Sum of {line_col} over {len(lines)} lines is {got:.2f}, not {total}"})
    return gaps


def scenarios(rows):
    """What the sample covers, so a clean result on a narrow sample is not read as ready."""
    first = {}
    for r in rows:
        first.setdefault(invoice_key(r), r)
    by_type = {"invoice": 0, "credit_note": 0, "other": 0}
    foreign = 0
    for r in first.values():
        t = (r.get("type_code") or "").strip()
        by_type["invoice" if t in INVOICE_TYPES else "credit_note" if t in CREDIT_TYPES else "other"] += 1
        cur = (r.get("currency") or "").strip().upper()
        if cur and cur != "AED":
            foreign += 1
    categories = defaultdict(int)
    for r in rows:
        cat = (r.get("vat_category") or "").strip()
        if cat:
            categories[cat] += 1
    missing = [label for label, present in (
        ("credit notes (381 or 81)", by_type["credit_note"] > 0),
        ("zero-rated (Z) lines", categories.get("Z", 0) > 0),
        ("exempt (E) lines", categories.get("E", 0) > 0),
        ("reverse-charge (AE) lines", categories.get("AE", 0) > 0),
        ("non-AED invoices", foreign > 0)) if not present]
    return {"invoices_by_type": by_type, "vat_category_lines": dict(sorted(categories.items())),
            "foreign_currency": foreign > 0, "foreign_currency_invoices": foreign, "not_in_sample": missing}


def by_rule(items):
    counts, invoices = defaultdict(int), defaultdict(dict)
    for g in items:
        counts[g["rule"]] += 1
        invoices[g["rule"]][g["invoice"]] = True
    return [{"rule": k, "gaps": v, "invoices": len(invoices[k])}
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


def decode(data):
    """UTF-8 (with or without BOM) first. Otherwise Windows Arabic (cp1256) if that gives Arabic
    words, else Latin-1. Both single-byte encodings read any bytes, so the Arabic test decides."""
    try:
        return data.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp1256")
        if ARABIC_WORD.search(text):
            return text, "cp1256"
    except UnicodeDecodeError:
        pass
    return data.decode("latin-1"), "latin-1"


def load(path):
    with open(path, "rb") as fh:
        text, enc = decode(fh.read())
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None) or []
    columns = [(k or "").strip().lower() for k in header]
    counts = defaultdict(int)
    for c in columns:
        counts[c] += 1
    twice = [c for c, n in counts.items() if n > 1 and c]
    if twice:
        raise ValueError("these columns appear more than once (names are compared without case or spaces): "
                         + ", ".join(twice))
    rows = []
    for i, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue
        row = {c: (values[j] if j < len(values) else "") for j, c in enumerate(columns) if c}
        row["_row"] = i
        rows.append(row)
    return rows, enc, columns


def mask(value):
    """Keeps the first 3 and last 2 characters of a tax number."""
    v = (value or "").strip()
    return v[:3] + "*" * (len(v) - 5) + v[-2:] if len(v) > 5 else "*" * len(v)


def masked(items):
    out = []
    for g in items:
        if g["field"] in TAX_IDS:
            g = {**g, "value": " | ".join(mask(v) for v in g["value"].split(" | "))}
        out.append(g)
    return out


def report(rows, enc, columns, show_all=False, hide_ids=False):
    gaps, warnings = [], []
    for r in rows:
        g, w = check_row(r)
        gaps += g
        warnings += w
    gaps = once_per_invoice(gaps) + check_invoices(group_lines(rows), columns)
    warnings = once_per_invoice(warnings)
    if "unit_code" not in columns:
        warnings.append({"invoice": "", "line": "", "field": "unit_code", "value": "", "rule": "mc-unit-code",
                         "fix": "The file has no unit_code column. Add the unit of measure (BT-130, UN/ECE Rec 20) "
                                "for each line, such as EA, HUR or DAY"})
    if hide_ids:
        gaps, warnings = masked(gaps), masked(warnings)
    shown = gaps if show_all else gaps[:SHOWN]
    warnings_shown = warnings if show_all else warnings[:SHOWN]
    invoices = len(dict.fromkeys(invoice_key(r) for r in rows))
    with_gaps = len(dict.fromkeys(g["invoice"] for g in gaps if g["invoice"]))
    return {
        "file_encoding": enc, "lines": len(rows), "invoices": invoices,
        "invoices_with_gaps": with_gaps,
        "invoices_without_gaps_pct": round(100 * (invoices - with_gaps) / invoices) if invoices else 0,
        "gaps_total": len(gaps), "gaps_shown": len(shown), "truncated": len(shown) < len(gaps),
        "by_rule": by_rule(gaps),
        "warnings_total": len(warnings), "warnings_shown": len(warnings_shown),
        "warnings_by_rule": by_rule(warnings),
        "scenarios": scenarios(rows),
        "gaps": shown, "warnings": warnings_shown}


def summary(out):
    s = out["scenarios"]
    t = s["invoices_by_type"]
    lines = [f"Checked {out['lines']} lines in {out['invoices']} invoices.",
             f"Gaps: {out['gaps_total']} on {out['invoices_with_gaps']} invoices "
             f"({out['invoices_without_gaps_pct']}% of invoices have none). Warnings: {out['warnings_total']}."]
    for b in out["by_rule"]:
        lines.append(f"  {b['rule']}: gaps {b['gaps']}, invoices {b['invoices']}")
    for b in out["warnings_by_rule"]:
        lines.append(f"  warning {b['rule']}: {b['gaps']}")
    cats = ", ".join(s["vat_category_lines"]) or "none"
    lines.append(f"Sample: invoices {t['invoice']}, credit notes {t['credit_note']}, other {t['other']}; "
                 f"VAT categories {cats}; foreign currency {'yes' if s['foreign_currency'] else 'no'}.")
    if s["not_in_sample"]:
        lines.append("Not in this sample, so not checked: " + ", ".join(s["not_in_sample"]) + ".")
    lines.append(CONTACT)
    return "\n".join(lines)


def run(argv):
    files = [a for a in argv[1:] if not a.startswith("--")]
    if not files:
        print("usage: python3 -I check_uae.py invoices.csv [--all] [--summary] [--mask]", file=sys.stderr)
        return 2
    try:
        rows, enc, columns = load(files[0])
    except (OSError, ValueError, csv.Error) as e:
        print(f"could not check {files[0]}: {e}", file=sys.stderr)
        return 2
    if not rows:
        print(f"{files[0]} has no invoice lines, so nothing was checked", file=sys.stderr)
        return 2
    out = report(rows, enc, columns, show_all="--all" in argv, hide_ids="--mask" in argv)
    if "--summary" in argv:
        print(summary(out))
    else:
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 1 if out["gaps_total"] else 0


def main(argv):
    """Any unexpected error exits 2, so a crash is never read as "gaps found" (exit 1)."""
    try:
        return run(argv)
    except Exception as e:  # noqa: BLE001
        print(f"could not check the file: unexpected error {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
