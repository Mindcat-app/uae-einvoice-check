---
name: einvoice-from-export
description: Read an ERP invoice export (CSV or Excel), map its columns to the UAE e-invoice check columns, and run the check. Use inside einvoice-readiness when invoices come from an ERP.
---

# Invoice data from an ERP export

1. Look at the header row and 5 sample rows; never print the whole file.
2. Map columns to the ones in `${CLAUDE_PLUGIN_ROOT}/samples/uae-sample.csv`. Ask the user only about columns you cannot map. Save Excel as CSV first.
3. Run the check from `einvoice-readiness`.

UBL XML files are not supported yet. Say so and ask for a CSV export instead.
