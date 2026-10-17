# mindcat-einvoice-check

Checks UAE invoice data from Salesforce or an ERP CSV export against the PINT AE e-invoicing rules and lists the gaps per invoice: missing fields, TRN and TIN format, emirate codes, VAT categories and rates, VAT and line maths, credit-note references and reasons, units of measure and foreign-currency fields. **It never signs, sends or submits invoices, and it is not tax advice.** Saudi (ZATCA) checks are planned and not built yet.

> **UAE e-invoicing deadlines**
>
> | Group | Appoint an ASP by | Live from |
> | --- | --- | --- |
> | Revenue AED 50m or more | 30 Oct 2026 | 1 Jan 2027 |
> | Revenue under AED 50m | 31 Mar 2027 | 1 Jul 2027 |
> | Government entities | 31 Mar 2027 | 1 Oct 2027 |
>
> Source: Ministerial Decision 244 of 2025 as amended by Ministerial Decision 66 of 2026. ASP means accredited service provider.

## Who it is for
UAE finance teams in the second wave (revenue under AED 50m), and first-wave teams whose data isn't clean.

## Install
```
/plugin marketplace add Mindcat-app/uae-einvoice-check
/plugin install mindcat-einvoice-check@mindcat
```

## What it runs, sends and fetches
- **Local check engine** (`engine/check_uae.py`, Python standard library only). It reads the CSV the user points at and prints the gaps. It makes no network calls.
- **Salesforce reads** (optional) through the user's own read-only SOQL tools, to build the sample.
- **Nothing is sent to Mindcat.** There is no hosted server yet and no telemetry.
- **No hooks.** The plugin adds no hooks, so it never runs on your other commands or tools. It stays read-only because its engine has no network or write code and its skills only read; for Salesforce, sign in as a read-only user.

## Data handling
The invoice data you check (customer names, TRNs, addresses, amounts) is read on your machine and passes through your AI client's conversation, under that client's own data terms. Any CSV the plugin writes stays on your disk. Mindcat receives nothing. Use `--mask` to hide the middle digits of TRNs and TINs in the output.

Needs Python 3 (standard library only).

## Rules
Checks marked `ibr-...-ae` or `aligned-ibrp-...` mirror rules in the official PINT AE v1.0.4 Schematron (https://docs.peppol.eu/poac/ae/pint-ae/resources.zip). Checks marked `mc-` are Mindcat data checks. This is a pre-check on source data; the provider still validates the final XML.

The output has **gaps** (fix these), **warnings** (the CSV alone cannot decide, such as a blank buyer TRN, which is fine for a consumer but not for a VAT-registered business), the share of invoices with no gaps, and **scenario coverage**: which invoice types, VAT categories and currencies the sample had, and which it did not.

## Columns
One row per invoice line. Invoice-level fields repeat on every line of the invoice; gaps on them are reported once per invoice, and lines that disagree are a gap. Column names are matched without case or surrounding spaces.

| Column | Meaning | Required? | Example |
| --- | --- | --- | --- |
| `invoice_number` | Invoice or credit note number | Yes | INV-1001 |
| `issue_date` | Issue date, YYYY-MM-DD | Yes | 2026-10-01 |
| `type_code` | 380 or 480 invoice; 381 or 81 credit note | Yes | 380 |
| `currency` | Invoice currency | Yes | AED |
| `exchange_rate` | Rate to AED | If not AED | 3.6725 |
| `seller_trn` | Seller TRN, 15 digits | Yes, except types 480 and 81 | 100000000000003 |
| `seller_tin` | Seller TIN, 10 digits | If no TRN | 1000000000 |
| `seller_name` | Seller legal name | Yes | Example Trading LLC |
| `seller_country` | Seller country code | No (blank is AE) | AE |
| `seller_emirate` | AUH, DXB, SHJ, UAQ, FUJ, AJM or RAK | If seller in UAE | DXB |
| `buyer_name` | Buyer name | Yes | Buyer One LLC |
| `buyer_trn` | Buyer TRN | For reverse charge; warning if blank for a UAE buyer | 100000000000103 |
| `buyer_country` | Buyer country code | No (blank is AE) | AE |
| `buyer_emirate` | Buyer emirate code | Checked if given | AUH |
| `preceding_invoice` | Original invoice, on credit notes | Credit notes, unless reason is VD | INV-1001 |
| `credit_reason` | Credit note reason code (BTAE-03) | Credit notes | VD |
| `line_id` | Line number | Yes | 1 |
| `item_name` | Item name | Yes | Consulting day |
| `item_kind` | goods, service or both | Checked if given | service |
| `hs_code` | Item classification code | Goods | 84713000 |
| `sac_code` | Service accounting code | Services | 998311 |
| `unit_code` | Unit of measure (BT-130, UN/ECE Rec 20) | Checked if the column exists; warning if absent | DAY |
| `quantity` | Invoiced quantity | Yes | 2 |
| `unit_price` | Net price per base quantity | Yes | 1500 |
| `base_quantity` | Quantity the price is for | No (blank is 1) | 1 |
| `line_allowance` | Line discount amount | No | 100 |
| `line_charge` | Line charge amount | No | 0 |
| `line_net` | Line net amount | Yes | 2900 |
| `line_net_aed` | Line net in AED | If not AED (except E lines) | 10650.25 |
| `vat_category` | S, Z, E, O, AE or N | Yes | S |
| `vat_rate` | VAT rate in percent | S 5, Z 0, AE 0, E and O blank | 5 |
| `line_vat` | Line VAT amount | Checked if given | 145 |
| `exemption_reason` | Exemption reason code | E lines | VATEX-AE-EXEMPT |
| `invoice_total_net` | Invoice net total | Optional, checked against lines | 2900 |
| `invoice_total_vat` | Invoice VAT total | Optional, checked against lines | 145 |

## What this does not check
- The final UBL XML. Your accredited service provider validates that against the full Schematron.
- Addresses, payment means, transaction-type flags and many optional PINT AE fields.
- Whether a credit note reason code is on the official code list, and whether a buyer is B2B or B2C.
- Whether a TRN is real. It checks the format only and does no online lookup.

## Layout
| Path | What |
| --- | --- |
| `skills/einvoice-readiness` | Main skill: dates, sample, check, gap list, readiness brief |
| `skills/einvoice-from-salesforce` | Read-only SOQL sample and column mapping |
| `skills/einvoice-from-export` | CSV or Excel exports |
| `engine/check_uae.py` | UAE checks for CSV |
| `samples/uae-sample.csv` | 4 invoices: 2 clean, 2 with gaps |
| `docs/sample-report.md` | The `--summary` report for the sample |
| `tests/` | `python3 -I -m unittest discover -s tests` |

## Try it
Install the plugin, then ask Claude:
- "Check samples/uae-sample.csv from the e-invoice plugin for UAE e-invoicing gaps." (No account needed; the sample ships with the plugin.)
- "Here is our invoice export, invoices.csv. Which invoices would fail PINT AE, and why?"
- "When do we need an accredited service provider for UAE e-invoicing, and what should we fix in our data first?"

To run the check by hand:
```
python3 -I engine/check_uae.py samples/uae-sample.csv             # JSON
python3 -I engine/check_uae.py samples/uae-sample.csv --summary   # short text
python3 -I engine/check_uae.py invoices.csv --all --mask           # every gap, TRNs masked
```
Exit codes: 0 no gaps, 1 gaps found, 2 the file could not be checked. See [docs/sample-report.md](docs/sample-report.md).

## FAQ
- **Is this tax advice?** No. It checks data against published rules. Ask your tax adviser about how to treat a transaction.
- **Do we still need an ASP?** Yes. This plugin does not sign, send or submit anything. An accredited service provider does that.
- **Does Mindcat see our invoices?** No. The check runs on your machine. See [PRIVACY.md](PRIVACY.md).

## Troubleshooting
- **Exit code 2.** The file could not be checked: it is empty, has only a header row, has the same column twice (`Invoice_Number` and `invoice_number` count as the same), or could not be read. The message says which.
- **Encoding.** Save as CSV UTF-8 if you can. Windows Arabic (cp1256) and Latin-1 files are read too; `file_encoding` in the output says which was used.
- **Excel number formats.** Excel may save `1,000.00`, `5%` or `AED 100`. Use plain numbers: digits and a dot only. These show as `mc-number-format`.
- **Dates.** Excel may save `01/10/2026`. Use `2026-10-01` (YYYY-MM-DD).
- **Commas in names.** A name with a comma must be in double quotes in the CSV. Excel does this when it saves as CSV.

## Get help
Mindcat can help with a readiness review, data clean-up before go-live, and the hand-off to your ASP. This plugin is not tax advice.
- **Mapping help:** open an issue with the "Mapping help" template. Share column headers only, never real invoices.
- **Bug report:** open an issue with the "Bug" template, using made-up data.
- **Security:** email apps@mindcat.ai. See [SECURITY.md](SECURITY.md).
- **Contact:** https://mindcat.ai/contact or apps@mindcat.ai
- **Regional desks:**
  - Dubai: info@mindcat.ai, +971 4 266 2348
  - India: india@mindcat.ai
  - US: usa@mindcat.ai
- Privacy policy: [PRIVACY.md](PRIVACY.md)

## Status
Version 0.2.0. Checks UAE invoices against the PINT AE v1.0.4 rules. Tested with unit tests and the sample invoices in `samples/`. See [CHANGELOG.md](CHANGELOG.md). Saudi (ZATCA) checks are planned and not included yet.
