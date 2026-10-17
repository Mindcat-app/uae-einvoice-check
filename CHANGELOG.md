# Changelog

## Unreleased
- Gaps on invoice-level fields are reported once per invoice, and lines of one invoice that disagree (or two invoices sharing a number) are flagged (`mc-header-mismatch`).
- New checks: issue date format (`mc-date-format`), line amount in AED (`mc-aed-maths`), unit code (`ibr-023`, `ibr-cl-23`), credit note reason (`ibr-158-ae`, `ibr-001-ae`), VAT rate on reverse-charge lines (`aligned-ibrp-ae-05-ae`), and optional invoice totals (`mc-total-net`, `mc-total-vat`, `mc-total-gross`).
- Item code gaps use the official ids `ibr-184-ae`, `ibr-185-ae` and `ibr-186-ae`.
- Output adds `coverage` (what the sample covers and lacks) and `warnings` (not counted as gaps).
- New options: `--mask` hides TRNs and TINs, `--summary` prints a short text summary.
- A non-numeric base quantity no longer crashes the check; duplicate column headers stop it with exit 2; blank header cells are ignored.
- README: deadlines with sources, CSV columns, what is not checked, FAQ, troubleshooting and help. New SECURITY, CONTRIBUTING and issue templates, and tests run in GitHub Actions.

## 0.1.0 - 2026-10-17
- First release: UAE PINT AE readiness checks for CSV invoice data, with skills for Salesforce and ERP exports.
