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
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

TRN = re.compile(r"^1[0-9]{12}03$")
TIN = re.compile(r"^1[0-9]{9}$")
ISO_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
UNIT_CODE = re.compile(r"^[A-Z0-9]{2,3}$")
NUMBER = re.compile(r"-?[0-9]+(\.[0-9]+)?")
EMIRATES = ("AUH", "DXB", "SHJ", "UAQ", "FUJ", "AJM", "RAK")
INVOICE_TYPES, CREDIT_TYPES = {"380", "480"}, {"381", "81"}
OUT_OF_SCOPE_TYPES = {"480", "81"}
VAT_CATEGORIES = ("S", "Z", "E", "O", "AE", "N")
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
NUMERIC_HEADER = ["exchange_rate", "invoice_total_net", "invoice_total_vat"]
CODE_HEADER = ["type_code", "currency", "seller_country", "seller_emirate", "buyer_country", "buyer_emirate",
               "credit_reason"]
FLAGS = ["--all", "--summary", "--mask"]
BOM = b"\xef\xbb\xbf"
PREFIX = 65536
TAX_IDS = ["seller_trn", "seller_tin", "buyer_trn"]
# Fields that tell two different invoices apart when they share one invoice number.
IDENTITY = ["seller_trn", "seller_tin", "seller_name", "issue_date"]
ARABIC_WORD = re.compile(r"[\u0621-\u064A]{3,}")
SHOWN = 50
CONTACT = "Want help fixing these before your provider goes live? Email apps@mindcat.ai (Dubai +971 4 266 2348)."


def dec(v):
    """Strict decimal: ASCII digits and one optional dot. Returns None for empty or unreadable values.
    The pattern only matches finite numbers, so Decimal() cannot fail on it."""
    s = (v or "").strip()
    return Decimal(s) if NUMBER.fullmatch(s) else None


def one_of(codes):
    """'A, B or C' from a list of codes, in the list's order."""
    return ", ".join(codes[:-1]) + " or " + codes[-1]


EMIRATE_FIX = f"Use {one_of(EMIRATES)} (capitals)"
CATEGORY_FIX = f"Use {one_of(VAT_CATEGORIES)} (capitals)"
# Tax number formats: field, pattern, rule, fix. Seller ones always apply; buyer ones only for a UAE buyer.
SELLER_IDS = [("seller_trn", TRN, "ibr-132-ae", "TRN must be 15 digits, start with 1 and end with 03"),
              ("seller_tin", TIN, "ibr-148-ae", "TIN must be 10 digits starting with 1")]
BUYER_IDS = [("buyer_trn", TRN, "ibr-132-ae", "Buyer TRN must be 15 digits, start with 1 and end with 03")]


def make_item(invoice, line, field, value, rule, fix):
    """One gap or warning, in the shape the JSON output uses."""
    return {"invoice": invoice, "line": line, "field": field, "value": value, "rule": rule, "fix": fix}


def invoice_key(r):
    return (r.get("invoice_number") or "").strip() or f"(row {r['_row']})"


def check_row(r):
    """Returns (gaps, warnings) for one invoice line."""
    gaps, warnings = [], []
    v = {f: (x or "").strip() for f, x in r.items() if f != "_row"}
    get = lambda f: v.get(f, "")
    n = {f: dec(get(f)) for f in NUMERIC}

    def num_or(f, default):
        """The parsed number, the default when blank, or None when it does not parse."""
        return n[f] if get(f) else default

    def item(field, rule, fix):
        return make_item(invoice_key(r), r.get("line_id", ""), field, r.get(field, ""), rule, fix)

    def gap(field, rule, fix):
        gaps.append(item(field, rule, fix))

    for f in REQUIRED:
        if not get(f):
            gap(f, "mc-missing", f"{f} is empty")
    for f in NUMERIC:
        if get(f) and n[f] is None:
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
    if t not in OUT_OF_SCOPE_TYPES and not get("seller_trn"):
        gap("seller_trn", "ibr-134-ae", "Seller TRN is required except on type 480 and 81")
    if not get("seller_trn") and not get("seller_tin"):
        gap("seller_tin", "ibr-177-ae", "Give the seller TRN or TIN")
    def id_formats(checks):
        for f, pattern, rule, fix in checks:
            if get(f) and not pattern.match(get(f)):
                gap(f, rule, fix)

    id_formats(SELLER_IDS)
    if get("seller_country").upper() in ("", "AE") and get("seller_emirate") not in EMIRATES:
        gap("seller_emirate", "ibr-128-ae", EMIRATE_FIX)

    # Buyer: UAE rules apply only when the buyer is in the UAE (blank country is read as AE)
    if get("buyer_country").upper() in ("", "AE"):
        id_formats(BUYER_IDS)
        if get("buyer_emirate") and get("buyer_emirate") not in EMIRATES:
            gap("buyer_emirate", "ibr-128-ae", EMIRATE_FIX)
        if not get("buyer_trn") and cat != "AE":
            warnings.append(item("buyer_trn", "mc-buyer-trn-missing",
                                 "Buyer TRN is blank. Fine for a consumer, but a B2B buyer registered "
                                 "for VAT needs its TRN on the invoice"))

    # VAT category rules
    rate, vat, net = n["vat_rate"], n["line_vat"], n["line_net"]
    if cat and cat not in VAT_CATEGORIES:
        gap("vat_category", "ibr-139-ae", CATEGORY_FIX)
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
        if not get("vat_rate") or (rate is not None and rate != 0):
            gap("vat_rate", "aligned-ibrp-ae-05", "Reverse-charge (AE) lines must have VAT rate 0")
        if vat not in (None, Decimal(0)):
            gap("line_vat", "mc-reverse-charge-vat", "Reverse-charge lines carry 0 VAT; the buyer accounts for it")
    if cat in {"S", "Z", "N"} and None not in (net, rate, vat) and abs(net * rate / 100 - vat) > Decimal("0.01"):
        gap("line_vat", "mc-vat-maths", f"net x rate = {net * rate / 100:.2f}, not {vat}")

    # Line maths: qty x (price / base qty) + charges - allowances
    q, p = n["quantity"], n["unit_price"]
    base = num_or("base_quantity", Decimal(1))
    if base is not None and base <= 0:
        gap("base_quantity", "mc-base-quantity", "Base quantity must be more than 0; leave it empty for 1")
    allow, charge = num_or("line_allowance", Decimal(0)), num_or("line_charge", Decimal(0))
    if None not in (q, p, net, base, allow, charge) and base > 0:
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
        xr, net_aed = n["exchange_rate"], n["line_net_aed"]
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


def header_values(lines, field):
    """Distinct non-blank values of a header field across lines, as {compare key: first raw value}.
    Many ERPs fill header fields on the first line only, so blanks are ignored. Numbers compare
    by value (3.6725 = 3.67250); codes compare without case."""
    out = {}
    for r in lines:
        raw = (r.get(field) or "").strip()
        if not raw:
            continue
        number = dec(raw) if field in NUMERIC_HEADER else None
        if number is not None:
            key = str(number.normalize())
        elif field in CODE_HEADER:
            key = raw.upper()
        else:
            key = raw
        out.setdefault(key, raw)
    return out


def check_invoices(groups, columns):
    """Checks across the lines of one invoice: two invoices sharing a number, header fields that
    disagree, and optional totals."""
    gaps = []
    for inv, lines in groups.items():
        hv = {f: header_values(lines, f) for f in HEADER}
        if any(len(hv[f]) > 1 for f in IDENTITY):
            gaps.append(make_item(inv, "", "invoice_number", inv, "mc-duplicate-invoice",
                                  "Different invoices (seller or issue date differ) share this number. Give each "
                                  "invoice its own number in the file; header and totals checks are skipped for it"))
            continue
        for f in HEADER:
            if len(hv[f]) > 1:
                gaps.append(make_item(inv, "", f, " | ".join(hv[f].values()), "mc-header-mismatch",
                                      f"All lines of one invoice must carry the same {f}"))
        for total_col, line_col in (("invoice_total_net", "line_net"), ("invoice_total_vat", "line_vat")):
            if total_col not in columns or line_col not in columns:
                continue
            raw_parts = [(r.get(line_col) or "").strip() for r in lines]
            if len(hv[total_col]) != 1 or not all(raw_parts):
                continue  # no total, totals that disagree (reported above), or a blank line amount
            raw_total = next(iter(hv[total_col].values()))
            total, parts = dec(raw_total), [dec(x) for x in raw_parts]
            if total is None or None in parts:
                continue
            got = sum(parts, Decimal(0))
            if abs(got - total) > Decimal("0.01") * len(lines):
                gaps.append(make_item(inv, "", total_col, raw_total, "mc-totals",
                                      f"Sum of {line_col} over {len(lines)} lines is {got:.2f}, not {total}"))
    return gaps


def first_lines(rows):
    """The first line of each invoice, keyed by invoice."""
    first = {}
    for r in rows:
        first.setdefault(invoice_key(r), r)
    return first


def scenarios(rows, first):
    """What the sample covers, so a clean result on a narrow sample is not read as ready."""
    by_type = {"invoice": 0, "credit_note": 0, "other": 0}
    foreign = 0
    for r in first.values():
        t = (r.get("type_code") or "").strip()
        by_type["invoice" if t in INVOICE_TYPES else "credit_note" if t in CREDIT_TYPES else "other"] += 1
        cur = (r.get("currency") or "").strip().upper()
        foreign += bool(cur and cur != "AED")
    categories = Counter(c for c in ((r.get("vat_category") or "").strip() for r in rows) if c)
    missing = [label for label, present in (
        ("credit notes (381 or 81)", by_type["credit_note"] > 0),
        ("zero-rated (Z) lines", categories["Z"] > 0),
        ("exempt (E) lines", categories["E"] > 0),
        ("reverse-charge (AE) lines", categories["AE"] > 0),
        ("non-AED invoices", foreign > 0)) if not present]
    return {"invoices_by_type": by_type, "vat_category_lines": dict(sorted(categories.items())),
            "foreign_currency": foreign > 0, "foreign_currency_invoices": foreign, "not_in_sample": missing}


def by_rule(items):
    counts, invoices = Counter(g["rule"] for g in items), defaultdict(dict)
    for g in items:
        invoices[g["rule"]][g["invoice"]] = True
    return [{"rule": k, "gaps": c, "invoices": len(invoices[k])} for k, c in counts.most_common()]


def detect(prefix, complete):
    """Picks an encoding from the start of the file (BOM already removed). UTF-8 first. Otherwise
    Windows Arabic (cp1256) if that gives Arabic words, then Windows Latin (cp1252), then Latin-1,
    which reads any bytes. A UTF-8 character cut off at the end of the prefix is not an error."""
    try:
        prefix.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError as e:
        if not complete and e.reason == "unexpected end of data" and e.start >= len(prefix) - 3:
            return "utf-8"
    if ARABIC_WORD.search(prefix.decode("cp1256", errors="ignore")):
        return "cp1256"
    try:
        prefix.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        return "latin-1"


def read_rows(path, skip, enc):
    with open(path, "rb") as raw:
        raw.seek(skip)
        with io.TextIOWrapper(raw, encoding=enc, newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, None) or []
            columns = [k.strip().lower() for k in header]
            twice = [c for c, k in Counter(columns).items() if k > 1 and c]
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
    return rows, columns


def load(path):
    """Detects the encoding on the first 64 KB, then reads the file as a stream. If a later part of
    the file does not decode, falls back to cp1252 and then Latin-1."""
    with open(path, "rb") as fh:
        prefix = fh.read(PREFIX + 1)
    skip = len(BOM) if prefix.startswith(BOM) else 0
    complete = len(prefix) <= PREFIX
    enc = detect(prefix[skip:PREFIX], complete)
    for e in dict.fromkeys([enc, "cp1252", "latin-1"]):
        try:
            rows, columns = read_rows(path, skip, e)
        except UnicodeDecodeError:
            continue
        name = "utf-8-sig" if e == "utf-8" and skip else e
        return rows, name, columns
    raise ValueError("could not read the file's text encoding")


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
        warnings.append(make_item("", "", "unit_code", "", "mc-unit-code",
                                  "The file has no unit_code column. Add the unit of measure (BT-130, UN/ECE Rec 20) "
                                  "for each line, such as EA, HUR or DAY"))
    if hide_ids:
        gaps, warnings = masked(gaps), masked(warnings)
    shown = gaps if show_all else gaps[:SHOWN]
    warnings_shown = warnings if show_all else warnings[:SHOWN]
    first = first_lines(rows)
    invoices = len(first)
    with_gaps = len(dict.fromkeys(g["invoice"] for g in gaps if g["invoice"]))
    return {
        "file_encoding": enc, "lines": len(rows), "invoices": invoices,
        "invoices_with_gaps": with_gaps,
        "invoices_without_gaps_pct": round(100 * (invoices - with_gaps) / invoices) if invoices else 0,
        "gaps_total": len(gaps), "gaps_shown": len(shown), "truncated": len(shown) < len(gaps) or len(warnings_shown) < len(warnings),
        "by_rule": by_rule(gaps),
        "warnings_total": len(warnings), "warnings_shown": len(warnings_shown),
        "warnings_truncated": len(warnings_shown) < len(warnings),
        "warnings_by_rule": by_rule(warnings),
        "scenarios": scenarios(rows, first),
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
    unknown = [a for a in argv[1:] if a.startswith("--") and a not in FLAGS]
    if len(files) != 1 or unknown:
        if unknown:
            print(f"unknown option: {', '.join(unknown)}", file=sys.stderr)
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
