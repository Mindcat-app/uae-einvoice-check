# mindcat-einvoice-check

Checks UAE invoice data from Salesforce or an ERP CSV export against the PINT AE e-invoicing rules and lists the gaps per invoice: missing fields, dates, TRN and TIN format, emirate codes, VAT categories and rates, VAT and line maths, units of measure, item codes, credit-note references and reasons, and foreign-currency fields. **It never signs, sends or submits invoices, and it is not tax advice.** Saudi (ZATCA) checks are planned and not built yet.

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
The invoice data you check (customer names, TRNs, addresses, amounts) is read on your machine and passes through your AI client's conversation, under that client's own data terms. Any CSV the plugin writes stays on your disk. Mindcat receives nothing.

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

Invoice-level columns must be the same on every line of an invoice; a gap in one is reported once per invoice. Numbers are plain digits and a dot. Save the file as UTF-8; other files are read as Arabic Windows (cp1256), and the output names the encoding used.

## Output
JSON with the gaps (grouped in `by_rule`), `coverage` (invoices by type and currency, lines by VAT category, and `not_in_sample`: common cases such as credit notes, zero-rated, exempt, reverse charge or foreign currency that the sample has none of) and `warnings`, which are worth a look but are not counted as gaps. Exit 0 means no gaps, 1 gaps, 2 the file could not be checked.

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

## Support
- Email: apps@mindcat.ai
- Contact: https://mindcat.ai/contact
- Privacy policy: [PRIVACY.md](PRIVACY.md)

## Status
Version 0.1.0. Checks UAE invoices against the PINT AE v1.0.4 rules. Tested with unit tests and the sample invoices in `samples/`. Saudi (ZATCA) checks are planned and not included yet.
