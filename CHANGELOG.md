# Changelog

## 0.2.0
- Reverse charge (AE) lines need VAT rate 0 (`aligned-ibrp-ae-05`).
- Credit notes need a reason code (`ibr-158-ae`; BTAE-03 is mandatory since PINT AE 1.0.1). New `credit_reason` column.
- Goods and services codes use the official ids `ibr-184-ae`, `ibr-185-ae` and `ibr-186-ae` (were `mc-item-code`).
- New checks: `mc-issue-date` (YYYY-MM-DD and a real date), `mc-fx-maths` (line_net x exchange_rate = line_net_aed), `mc-unit-code` (new `unit_code` column, UN/ECE Rec 20), `mc-header-mismatch`, `mc-duplicate-invoice`, `mc-totals` (optional `invoice_total_net` and `invoice_total_vat`).
- Invoice-level gaps are reported once per invoice, not once per line.
- Warnings, separate from gaps. A blank buyer TRN for a UAE buyer is now a warning (`mc-buyer-trn-missing`).
- Output has scenario coverage and the share of invoices with no gaps.
- New flags: `--summary` (short text) and `--mask` (hides the middle of TRNs and TINs).
- Fixed a crash on a non-numeric `base_quantity`. Any unexpected error now exits 2, never 1.
- Encoding: UTF-8 (with or without BOM), then cp1256 only when the file has Arabic words, then cp1252, then Latin-1. Detected on the first 64 KB, then read as a stream.
- Unknown options or more than one file exit 2 with the usage message.
- A column that appears twice after normalising names exits 2 with a message.
- Readiness skill: readiness brief to copy and send, scenario coverage. README: deadlines, column guide, FAQ, troubleshooting, help.

## 0.1.0
- First release: UAE PINT AE checks on CSV invoice lines, Salesforce and ERP export skills, sample file and tests.
