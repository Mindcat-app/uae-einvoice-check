# mindcat-einvoice-check

Checks UAE invoice data from Salesforce or an ERP (CSV, Excel or PINT AE UBL XML) against the PINT AE e-invoicing rules and lists the gaps per invoice: missing fields, dates, TRN and TIN format, emirate codes, VAT categories and rates, VAT and line maths, units of measure, item codes, credit-note references and reasons, transaction-type flags, Peppol endpoints and foreign-currency fields. It can also audit customer and item master data, write a gap list for a finance team, and write a hand-off pack for your accredited service provider. **It never signs, sends or submits invoices, and it is not tax advice.**

It also pre-checks **Saudi (ZATCA)** invoice data in CSV against the ZATCA E-Invoice XML Implementation Standard v1.2 rules (BR-KSA and BR ids): VAT numbers, transaction codes, addresses, VAT categories and exemption codes, credit and debit notes, and totals. It never signs an invoice, generates a QR code or hash, or submits anything; the final XML must still be validated with the ZATCA SDK or the Fatoora portal. Rules and sources: [docs/ksa-rules.md](docs/ksa-rules.md).

> **UAE e-invoicing dates** (Ministerial Decision 244 of 2025, Article 5, as amended by Ministerial Resolution No. 66 of 2026)
> | Group | Appoint an accredited service provider by | Live from |
> | --- | --- | --- |
> | Revenue AED 50m or more | 30 Oct 2026 | 1 Jan 2027 |
> | Revenue under AED 50m | 31 Mar 2027 | 1 Jul 2027 |
> | Government entities | 31 Mar 2027 | 1 Oct 2027 |
>
> Sources: [MD 244/2025](https://mof.gov.ae/wp-content/uploads/2025/09/Ministerial-Decision-No.-244-of-2025-on-the-Implementation-of-the-Electronic-Invoicing-System.pdf), [Ministerial Resolution No. 66 of 2026](https://mof.gov.ae/wp-content/uploads/2026/05/Ministerial-Resolution-No.-66-of-2026-Amending-Certain-Provisions-of-Ministerial-Resolution-No.-244-of-2025-Regarding-the-Implementation-of-the-Electronic-Invoicing-System-En-20260514.pdf), [Ministry of Finance e-invoicing page](https://mof.gov.ae/einvoicing). Check them for changes.

## Who it is for
UAE finance teams in the second wave (revenue under AED 50m: appoint an accredited service provider by 31 Mar 2027, live 1 Jul 2027), and first-wave teams whose data isn't clean.

## Install
```
/plugin marketplace add Mindcat-app/uae-einvoice-check
/plugin install mindcat-einvoice-check@mindcat
```

## What it runs, sends and fetches
- **Two local check engines**, Python standard library only: `engine/check_uae.py` (UAE, PINT AE) and `engine/check_ksa.py` (Saudi Arabia, ZATCA). Each reads the file the user points at and prints the gaps. Neither makes network calls. The UAE engine writes files only when asked: `--report` and `--handoff` write to the path you give. The Saudi engine writes nothing.
- **Salesforce reads** (optional) through the user's own read-only SOQL tools, to build the sample. `einvoice-from-salesforce` needs your own Salesforce CLI (`sf`) or a Salesforce MCP tool, signed in to your org; the plugin ships neither.
- **Nothing is sent to Mindcat.** There is no hosted server yet and no telemetry.
- **No hooks.** The plugin adds no hooks, so it never runs on your other commands or tools. It stays read-only towards your systems: the engine has no network code, it writes only the report files you ask for, and its skills only read; for Salesforce, sign in as a read-only user. Salesforce fix suggestions are text for your admin; the plugin never deploys them.

## Data handling
The invoice data you check (customer names, TRNs, addresses, amounts) is read on your machine and passes through your AI client's conversation, so it goes to your AI provider under that client's own data terms. The check's output does too; run it with `--mask` to hide all but the last 4 characters of TRNs, TINs and endpoint ids (the Saudi check: VAT numbers and other IDs). Any file the plugin writes stays on your disk; the `--handoff` pack holds no names, invoice numbers, TRNs or amounts. Mindcat receives nothing.

Needs Python 3 (standard library only).

## Rules
Checks marked `ibr-...` or `aligned-...` mirror rules in the official PINT AE v1.0.4 Schematron (https://docs.peppol.eu/poac/ae/pint-ae/resources.zip). Checks marked `mc-` are Mindcat data checks. `ibr-cl-23` checks the shape of the unit code (2 or 3 capital letters or digits), not the full UN/ECE list. This is a pre-check on source data; the provider still validates the final XML. For UBL XML input it runs these same checks on the XML's data: **it is not full Schematron validation** and does not replace your provider's validator.

## Inputs
- **CSV** with the columns below (one row per invoice line).
- **Excel .xlsx**, first sheet, same columns. Cell text is read as Excel stored it, and `issue_date` cells stored as Excel dates become `YYYY-MM-DD`. Format `transaction_type`, endpoint and code columns as text, or Excel drops their leading zeros.
- **PINT AE UBL XML**: one invoice or credit note, or a folder of them. Fields are read from the XML (for example `cbc:ProfileExecutionID` for `transaction_type`, `cac:ItemPriceExtension` for the line VAT and amount payable). An invoice number used in more than one file is flagged.
- **Master data** with `--master customers` or `--master items`: a CSV or .xlsx list of customers (`customer_name`, `country`, `trn`, `tin`, `emirate`) or items (`item_name`, `item_kind`, `hs_code`, `sac_code`, `unit_code`, `vat_category`), checked with the same rules as invoice lines.

## CSV columns
One row per invoice line. Header names ignore case and surrounding spaces; a column that appears twice stops the check.

| Column | What |
| --- | --- |
| `invoice_number`, `issue_date`, `type_code`, `currency`, `exchange_rate` | Invoice header. `issue_date` is `YYYY-MM-DD`. `type_code` is 380 or 480 (invoice), 381 or 81 (credit note). `exchange_rate` is AED per 1 unit of the invoice currency (for USD, about 3.6725) |
| `transaction_type` | BTAE-02: 8 flags of 0 or 1, in this order: free trade zone, deemed supply, margin scheme, summary invoice, continuous supply, disclosed agent billing, e-commerce, exports. `00000000` for none |
| `seller_name`, `seller_trn`, `seller_tin`, `seller_country`, `seller_emirate` | Seller. Emirate is AUH, DXB, SHJ, UAQ, FUJ, AJM or RAK |
| `seller_endpoint`, `seller_endpoint_scheme` | Seller's Peppol electronic address and its scheme (0235 in the UAE) |
| `buyer_name`, `buyer_trn`, `buyer_country`, `buyer_emirate` | Buyer |
| `buyer_endpoint`, `buyer_endpoint_scheme` | Buyer's Peppol electronic address and scheme. Your provider can tell you the predefined addresses for buyers outside Peppol, such as exports |
| `preceding_invoice`, `credit_reason` | Credit notes: the original invoice number and the reason code (DL8.61.1.A to DL8.61.1.E, or VD) |
| `line_id`, `item_name`, `item_kind`, `hs_code`, `sac_code` | Line and item. `item_kind` is goods, service or both |
| `quantity`, `unit_code`, `unit_price`, `base_quantity`, `line_allowance`, `line_charge`, `line_net`, `line_net_aed` | Amounts. `unit_code` is a UN/ECE Rec 20 code in capitals, such as EA, HUR, DAY, MON or KGM. `line_net_aed` is `line_net` x `exchange_rate` |
| `vat_category`, `vat_rate`, `line_vat`, `exemption_reason` | VAT. Category is S, Z, E, O, AE or N |
| `invoice_total_net`, `invoice_total_vat`, `invoice_total_gross` | Optional. When present, each is checked once per invoice against the sum of `line_net`, the sum of `line_vat`, and the two added together |

Invoice-level columns must be the same on every line of an invoice; a gap in one is reported once per invoice. If they are filled on an invoice's first line only, later blank cells are read from that line; every line still needs the invoice number. Numbers are plain digits and a dot. Rows with only empty cells are skipped. Save the file as UTF-8 (UTF-16 with a byte order mark is read too). Other files are read as Arabic Windows (cp1256) when they hold Arabic words and as Western Windows (cp1252) otherwise; the output names the encoding used.

## Output
JSON with the gaps (grouped in `by_rule`), `coverage` (invoices by type and currency, lines by VAT category, and `not_in_sample`: common cases such as credit notes, zero-rated, exempt, reverse charge or foreign currency that the sample has none of) and `warnings`, which are worth a look but are not counted as gaps. A required column that is missing from the file entirely is one gap for the whole file, with invoice `(all)` and the fix "column missing from the file"; `by_rule` still counts every invoice it affects. A cell that is there but blank or wrong is a gap on its invoice. Exit 0 means no gaps, 1 gaps, 2 the file could not be checked.

Options (`--help` lists them; a mistyped option stops with exit 2, in both engines):

| Option | What |
| --- | --- |
| `--all` | List every gap in the output; the default shows the first 50. Totals always count every gap |
| `--mask` | Hide all but the last 4 characters of TRNs, TINs and endpoint ids (UAE endpoint ids hold the TIN), in the output and in `--report` |
| `--summary` | Print a short text summary instead of JSON |
| `--master customers` / `--master items` | Check a customer or item list instead of invoices |
| `--report gaps.csv` | Also write every gap to a CSV, one row per gap, with empty owner and status columns to assign fixes |
| `--handoff folder` | Also write `field-map.md` (each column and the PINT AE id it feeds) and `readiness.md` (gap counts by rule and sample coverage) for your provider, with no names, invoice numbers, TRNs or amounts |

Sample report (`python3 -I engine/check_uae.py samples/uae-sample.csv --summary`):
```
Checked 4 lines in 4 invoices (utf-8).
Invoices with gaps: 2 of 4. Gaps: 7.
Top rules:
  ibr-132-ae: 1 gap(s) in 1 invoice(s)
  ibr-128-ae: 1 gap(s) in 1 invoice(s)
  ibr-190-ae: 1 gap(s) in 1 invoice(s)
  ...
Not in this sample: exempt (E), reverse charge (AE)
Warnings (not gaps): 1
Help getting ready: mindcat.ai/contact
```

## What this does not check
- The final UBL XML. Validating it, signing and sending it is your accredited service provider's job.
- Addresses, payment means, invoice periods, delivery details and legal registration ids, so the rules that depend on them (for example the extra fields for free trade zone, summary, e-commerce, export and agent invoices) are not checked.
- Whether an endpoint id is the right one: only that it is there with a valid scheme.
- Whether a business buyer must have a TRN: a UAE buyer with no TRN on a standard-rated invoice is a warning only, because consumers have none.

## Layout
| Path | What |
| --- | --- |
| `skills/einvoice-readiness` | Main skill: dates, sample, check, gap list |
| `skills/einvoice-from-salesforce` | Read-only SOQL sample and column mapping |
| `skills/einvoice-from-export` | CSV, Excel or XML exports, with export tips for common ERPs |
| `skills/einvoice-master-data` | Customer and item list audit |
| `skills/einvoice-ksa` | Saudi (ZATCA) data pre-check |
| `engine/check_ksa.py`, `docs/ksa-rules.md`, `samples/ksa-sample.csv` | Saudi checks, their rules and sources, and a sample |
| `engine/check_uae.py` | UAE checks for CSV, Excel and UBL XML |
| `samples/uae-sample.csv` | 4 invoices: 2 clean, 2 with gaps |
| `tests/` | `python3 -I -m unittest discover -s tests` |

## Try it
Install the plugin, then ask Claude:
- "Check samples/uae-sample.csv from the e-invoice plugin for UAE e-invoicing gaps." (No account needed; the sample ships with the plugin.)
- "Here is our invoice export, invoices.csv. Which invoices would fail PINT AE, and why?"
- "When do we need an accredited service provider for UAE e-invoicing, and what should we fix in our data first?"

To run the check by hand: `python3 -I engine/check_uae.py samples/uae-sample.csv`

## FAQ
- **Is this tax advice?** No. It checks data against published rules.
- **Do I still need an accredited service provider?** Yes. This checks your source data before your provider builds and sends the invoices.
- **Does Mindcat see my data?** No. The check runs on your machine; see [PRIVACY.md](PRIVACY.md).

## Troubleshooting
- **Exit code 2:** the file could not be checked. The message says why: no lines, a column that appears twice, an unknown option, a file that could not be read, or `--report` naming the file being checked.
- **`ibr-154-ae` or `ibr-cl-25` on every invoice from Excel:** Excel turned `00000000` into `0` or `0235` into `235`. Format those columns as text.
- **Odd characters in names:** save the file as UTF-8. `file_encoding` in the output shows how it was read.
- **Many `mc-number-format` gaps:** Excel often writes numbers as `1,000` or `5%`. Format the columns as plain numbers with no thousands separator before saving as CSV.

## Get help
- Mapping help or a bug: open a GitHub issue, with made-up data only. Never paste real invoices, TRNs or customer names.
- Security issues: email apps@mindcat.ai, not a public issue (see [SECURITY.md](SECURITY.md)).
- Mindcat helps UAE finance and Salesforce teams get invoice data ready before their provider goes live: https://mindcat.ai/contact or apps@mindcat.ai.
- Privacy policy: [PRIVACY.md](PRIVACY.md). Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).

## Status
Version 0.2.0. Checks UAE invoices against the PINT AE v1.0.4 rules and pre-checks Saudi invoice data against the ZATCA XML Implementation Standard v1.2. Tested with unit tests and the sample invoices in `samples/`.
