# Changelog

## 0.2.0 - 2026-10-17
- Saudi (ZATCA) data pre-check: `engine/check_ksa.py` and skill `einvoice-ksa`, against the ZATCA E-Invoice XML Implementation Standard v1.2 rules (BR-KSA ids). It never signs, generates a QR code or hash, or submits; validate the final XML with the ZATCA SDK or the Fatoora portal. The listing is now "GCC E-invoicing Readiness Check (UAE and KSA)".
- Gaps on invoice-level fields are reported once per invoice, and lines of one invoice that disagree (or two invoices sharing a number) are flagged (`mc-header-mismatch`).
- New checks: issue date format (`mc-date-format`), line amount in AED (`mc-aed-maths`), unit code (`ibr-023`, `ibr-cl-23`), credit note reason (`ibr-158-ae`, `ibr-001-ae`), VAT rate on reverse-charge lines (`aligned-ibrp-ae-05-ae`), and optional invoice totals (`mc-total-net`, `mc-total-vat`, `mc-total-gross`).
- Item code gaps use the official ids `ibr-184-ae`, `ibr-185-ae` and `ibr-186-ae`.
- Output adds `coverage` (what the sample covers and lacks) and `warnings` (not counted as gaps).
- New options: `--mask` hides TRNs and TINs, `--summary` prints a short text summary.
- A non-numeric base quantity no longer crashes the check; duplicate column headers stop it with exit 2; blank header cells are ignored.
- New inputs: Excel .xlsx (first sheet) and PINT AE UBL XML (a file or a folder). XML input runs the same checks on the XML's data; it is not full Schematron validation.
- Transaction type flags (`ibr-154-ae`, `ibr-157-ae`) and Peppol endpoints (`ibr-080`, `ibr-081`, `ibr-062`, `ibr-063`, `ibr-cl-25`).
- `--master customers` and `--master items` audit master data; new skill `einvoice-master-data`.
- `--report` writes every gap to a CSV for a finance team; `--handoff` writes a field map and gap summary for the provider.
- Salesforce fix pack (suggested fields, picklists and validation rules, as text for an admin) and export tips for common ERPs (unverified until checked against real exports).
- Options are checked: a mistyped option stops with exit 2. Invoice-level cells filled on the first line only are read for the whole invoice. Non-UTF-8 files are read as cp1256 or cp1252.
- A required column missing from the whole file is one gap per file (invoice `(all)`, "column missing from the file") instead of one per invoice, in both engines.
- Review fixes: `--mask` also hides endpoint ids (they hold the TIN); rows of empty cells are skipped; UTF-16 files are read; .xlsx cells without a cell reference are read in order; `--report` cannot overwrite the file being checked; the Saudi check stops on a mistyped option (exit 2).
- README: deadlines with sources, CSV columns, what is not checked, FAQ, troubleshooting and help. New SECURITY, CONTRIBUTING and issue templates, and tests run in GitHub Actions.

## 0.1.0 - 2026-10-17
- First release: UAE PINT AE readiness checks for CSV invoice data, with skills for Salesforce and ERP exports.
