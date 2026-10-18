# Changelog

## 0.2.1 - 2026-10-18
Security hardening after a red-team review.
- Output is masked by default; `--unmask` shows full values and `--mask` is still accepted. Party names are masked too, including inside `mc-header-mismatch` values, and masked customer gaps name the row. Echoed cell text is cut to 60 characters; Saudi `BR-KSA-F-06` reports the length, not the text.
- Skills treat invoice cells, files and Salesforce records as data, never instructions, read only the header and at most 5 rows, and no longer pass `--mask`. `einvoice-from-salesforce` queries only the fields the check needs, can run only `sf data query`, and asks for a read-only user.
- `--report` and `--handoff` only create new files: no overwrites, links, hard links to the input, or targets inside an XML folder being checked. `--report` needs `.csv`; `--handoff` creates at most one folder level. Report cells are all quoted, and cells starting `=`, `+`, `-`, `@`, tab or CR get a leading `'`.
- Country names (UAE, United Arab Emirates; KSA, Saudi Arabia) no longer switch the country rules off; a country that is not a 2-letter code is a gap (`ibr-cl-14`, `BR-CL-14`).
- UAE currency must be a 3-letter code in capitals (`ibr-cl-04`). Coverage shows only known codes, others as `(other)`, so no free text reaches the output or the hand-off pack.
- CSV lines other than exempt (E) need `line_vat`, as XML lines already did (`ibr-104-ae`).
- Repeated line ids in one invoice are a gap (`mc-duplicate-line`, `csv-duplicate-line`).
- Headers ignore invisible characters and read spaces and hyphens as `_`; unknown columns are warnings naming the closest known column (`mc-unknown-column`, `csv-unknown-column`).
- Inputs must be regular files of at most 200 MB. XML folders report `files_read`; skipped files, non-invoice files and invoices with no lines are gaps (`mc-xml-skipped`, `mc-xml-root`, `mc-xml-no-lines`). XML and .xlsx parts with a DOCTYPE are refused; .xlsx parts are capped at 50 MB each and 200 MB in all, and columns at 16384.
- Numbers longer than 30 digits are a format gap; an unexpected error prints a fixed message with no file values and exits 2.
- New warnings, not gaps: a negative line amount on a 380 invoice (`mc-negative-line`), and a Saudi standard-rated line that is not 15% (`csv-s-rate`).

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
