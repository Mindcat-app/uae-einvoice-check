# Sample report

Output of `python3 -I engine/check_uae.py samples/uae-sample.csv --summary` (exit code 1, gaps found). The sample data is made up.

```
Checked 4 lines in 4 invoices.
Gaps: 7 on 2 invoices (50% of invoices have none). Warnings: 1.
  ibr-132-ae: gaps 1, invoices 1
  ibr-128-ae: gaps 1, invoices 1
  ibr-190-ae: gaps 1, invoices 1
  ibr-147-ae: gaps 1, invoices 1
  ibr-184-ae: gaps 1, invoices 1
  ibr-159-ae: gaps 1, invoices 1
  ibr-104-ae: gaps 1, invoices 1
  warning mc-buyer-trn-missing: 1
Sample: invoices 3, credit notes 1, other 0; VAT categories S, Z; foreign currency yes.
Not in this sample, so not checked: exempt (E) lines, reverse-charge (AE) lines.
Want help fixing these before your provider goes live? Email apps@mindcat.ai (Dubai +971 4 266 2348).
```

What it means:
- INV-1002 has a short seller TRN (`ibr-132-ae`), "Dubai" instead of DXB (`ibr-128-ae`), a 15% rate on a standard-rated line (`ibr-190-ae`), a line amount that does not match quantity x price (`ibr-147-ae`) and goods with no HS code (`ibr-184-ae`). Its buyer TRN is blank: a warning, because the CSV cannot tell a consumer from a VAT-registered business.
- INV-1003 is in USD with no exchange rate (`ibr-159-ae`) and no AED line amount (`ibr-104-ae`).
- INV-1001 and the credit note CN-2001 have no gaps.
- The sample has no exempt (E) or reverse-charge (AE) lines, so a clean result says nothing about them. Add a few before testing with your provider.

Run without `--summary` for the full JSON, with each gap's invoice, line, field, value and fix.
