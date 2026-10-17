# mindcat-einvoice-check

Checks UAE invoice data from Salesforce or an ERP CSV export against the PINT AE e-invoicing rules and lists the gaps per invoice: missing fields, dates, TRN and TIN format, emirate codes, VAT categories and rates, VAT and line maths, units of measure, item codes, credit-note references and reasons, and foreign-currency fields. **It never signs, sends or submits invoices, and it is not tax advice.** Saudi (ZATCA) checks are planned and not built yet.

> **UAE e-invoicing dates** (Ministerial Decision 244 of 2025, Article 5, as amended by Ministerial Decision 66 of 2026)
> | Group | Appoint an accredited service provider by | Live from |
> | --- | --- | --- |
> | Revenue AED 50m or more | 30 Oct 2026 | 1 Jan 2027 |
> | Revenue under AED 50m | 31 Mar 2027 | 1 Jul 2027 |
> | Government entities | 31 Mar 2027 | 1 Oct 2027 |
>
> Sources: [MD 244/2025](https://mof.gov.ae/wp-content/uploads/2025/09/Ministerial-Decision-No.-244-of-2025-on-the-Implementation-of-the-Electronic-Invoicing-System.pdf), [MD 66/2026](https://mof.gov.ae/wp-content/uploads/2026/05/Ministerial-Resolution-No.-66-of-2026-Amending-Certain-Provisions-of-Ministerial-Resolution-No.-244-of-2025-Regarding-the-Implementation-of-the-Electronic-Invoicing-System-En-20260514.pdf), [Ministry of Finance e-invoicing page](https://mof.gov.ae/einvoicing). Check them for changes.

## Who it is for
UAE finance teams in the second wave (revenue under AED 50m: appoint an accredited service provider by 31 Mar 2027, live 1 Jul 2027), and first-wave teams whose data isn't clean.

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
The invoice data you check (customer names, TRNs, addresses, amounts) is read on your machine and passes through your AI client's conversation, so it goes to your AI provider under that client's own data terms. The check's output does too; run it with `--mask` to hide all but the last 4 characters of TRNs and TINs. Any CSV the plugin writes stays on your disk. Mindcat receives nothing.

Needs Python 3 (standard library only).

## Rules
Checks marked `ibr-...` or `aligned-...` mirror rules in the official PINT AE v1.0.4 Schematron (https://docs.peppol.eu/poac/ae/pint-ae/resources.zip). Checks marked `mc-` are Mindcat data checks. `ibr-cl-23` checks the shape of the unit code (2 or 3 capital letters or digits), not the full UN/ECE list. This is a pre-check on source data; the provider still validates the final XML.

## CSV columns
One row per invoice line. Header names ignore case and surrounding spaces; a column that appears twice stops the check.

| Column | What |
| --- | --- |
| `invoice_number`, `issue_date`, `type_code`, `currency`, `exchange_rate` | Invoice header. `issue_date` is `YYYY-MM-DD`. `type_code` is 380 or 480 (invoice), 381 or 81 (credit note). `exchange_rate` is AED per 1 unit of the invoice currency (for USD, about 3.6725) |
| `seller_name`, `seller_trn`, `seller_tin`, `seller_country`, `seller_emirate` | Seller. Emirate is AUH, DXB, SHJ, UAQ, FUJ, AJM or RAK |
| `buyer_name`, `buyer_trn`, `buyer_country`, `buyer_emirate` | Buyer |
| `preceding_invoice`, `credit_reason` | Credit notes: the original invoice number and the reason code (DL8.61.1.A to DL8.61.1.E, or VD) |
| `line_id`, `item_name`, `item_kind`, `hs_code`, `sac_code` | Line and item. `item_kind` is goods, service or both |
| `quantity`, `unit_code`, `unit_price`, `base_quantity`, `line_allowance`, `line_charge`, `line_net`, `line_net_aed` | Amounts. `unit_code` is a UN/ECE Rec 20 code in capitals, such as EA, HUR, DAY, MON or KGM. `line_net_aed` is `line_net` x `exchange_rate` |
| `vat_category`, `vat_rate`, `line_vat`, `exemption_reason` | VAT. Category is S, Z, E, O, AE or N |
| `invoice_total_net`, `invoice_total_vat`, `invoice_total_gross` | Optional. When present, each is checked once per invoice against the sum of `line_net`, the sum of `line_vat`, and the two added together |

Invoice-level columns must be the same on every line of an invoice; a gap in one is reported once per invoice. Numbers are plain digits and a dot. Save the file as UTF-8; other files are read as Arabic Windows (cp1256), and the output names the encoding used.

## Output
JSON with the gaps (grouped in `by_rule`), `coverage` (invoices by type and currency, lines by VAT category, and `not_in_sample`: common cases such as credit notes, zero-rated, exempt, reverse charge or foreign currency that the sample has none of) and `warnings`, which are worth a look but are not counted as gaps. Exit 0 means no gaps, 1 gaps, 2 the file could not be checked.

Options: `--all` lists every gap (the default shows 50), `--mask` hides TRNs and TINs, `--summary` prints a short text summary instead of JSON.

Sample report (`python3 -I engine/check_uae.py samples/uae-sample.csv --summary`):
```
Checked 4 lines in 4 invoices (utf-8-sig).
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
- Addresses, payment means, transaction-type flags and Peppol endpoint ids.
- Whether a business buyer must have a TRN: a UAE buyer with no TRN on a standard-rated invoice is a warning only, because consumers have none.

## Layout
| Path | What |
| --- | --- |
| `skills/einvoice-readiness` | Main skill: dates, sample, check, gap list |
| `skills/einvoice-from-salesforce` | Read-only SOQL sample and column mapping |
| `skills/einvoice-from-export` | CSV or Excel exports |
| `engine/check_uae.py` | UAE checks for CSV |
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
- **Exit code 2:** the file could not be checked. The message says why: no lines, a column that appears twice, or a file that could not be read.
- **Odd characters in names:** save the file as UTF-8. Other files are read as Arabic Windows (cp1256); `file_encoding` in the output shows which was used.
- **Many `mc-number-format` gaps:** Excel often writes numbers as `1,000` or `5%`. Format the columns as plain numbers with no thousands separator before saving as CSV.

## Get help
- Mapping help or a bug: open a GitHub issue, with made-up data only. Never paste real invoices, TRNs or customer names.
- Security issues: email apps@mindcat.ai, not a public issue (see [SECURITY.md](SECURITY.md)).
- Mindcat helps UAE finance and Salesforce teams get invoice data ready before their provider goes live: https://mindcat.ai/contact or apps@mindcat.ai.
- Privacy policy: [PRIVACY.md](PRIVACY.md). Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).

## Status
Version 0.1.0. Checks UAE invoices against the PINT AE v1.0.4 rules. Tested with unit tests and the sample invoices in `samples/`. Saudi (ZATCA) checks are planned and not included yet.
