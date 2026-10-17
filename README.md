# mindcat-einvoice-check

Checks UAE invoice data from Salesforce or an ERP CSV export against the PINT AE e-invoicing rules and lists the gaps per invoice: missing fields, TRN and TIN format, emirate codes, VAT categories and rates, VAT and line maths, credit-note references and foreign-currency fields. **It never signs, sends or submits invoices, and it is not tax advice.** Saudi (ZATCA) checks are planned and not built yet.

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
- **Guard hook** (`hooks/no_submit_guard.py`): blocks HTTP writes, Salesforce writes, signing commands and MCP tools whose names look like sending or changing data. It reads only the command or tool name, never file contents, and fails closed.

## Rules
Checks marked `ibr-...-ae` mirror rules in the official PINT AE v1.0.4 Schematron (https://docs.peppol.eu/poac/ae/pint-ae/resources.zip). Checks marked `mc-` are Mindcat data checks. This is a pre-check on source data; the provider still validates the final XML.

## Layout
| Path | What |
| --- | --- |
| `skills/einvoice-readiness` | Main skill: dates, sample, check, gap list |
| `skills/einvoice-from-salesforce` | Read-only SOQL sample and column mapping |
| `skills/einvoice-from-export` | CSV or Excel exports |
| `engine/check_uae.py` | UAE checks for CSV |
| `samples/uae-sample.csv` | 4 invoices: 2 clean, 2 with gaps |
| `hooks/no_submit_guard.py` | No-send guard |
| `tests/` | `python3 -I -m unittest discover -s tests` |
| `server/` | Plan for a hosted server (not built) |

## Try it
`python3 -I engine/check_uae.py samples/uae-sample.csv`

## Support
- Email: apps@mindcat.ai
- Contact: https://mindcat.ai/contact
- Privacy policy: https://mindcat.ai/privacy-policy

## Status
Version 0.1.0. Checks UAE invoices against the PINT AE v1.0.4 rules. Tested with unit tests and the sample invoices in `samples/`. Saudi (ZATCA) checks are planned and not included yet.
