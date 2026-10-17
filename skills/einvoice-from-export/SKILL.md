---
name: einvoice-from-export
description: Read an ERP invoice export (CSV or Excel), map its columns to the UAE e-invoice check columns, and run the check. Use inside einvoice-readiness when invoices come from an ERP.
---

# Invoice data from an ERP export

1. Look at the header row and 5 sample rows; never print the whole file.
2. Map columns to the ones in `${CLAUDE_PLUGIN_ROOT}/samples/uae-sample.csv`. Ask the user only about columns you cannot map. Save Excel as CSV first.
3. Run the check from `einvoice-readiness`.

Columns (one row per invoice line; header fields repeat on every line of an invoice):
- Required: `invoice_number`, `issue_date` (YYYY-MM-DD), `type_code`, `currency`, `seller_name`, `buyer_name`, `line_id`, `item_name`, `quantity`, `unit_price`, `line_net`, `vat_category`.
- Checked when present: `seller_trn`, `seller_tin`, `seller_country`, `seller_emirate`, `buyer_trn`, `buyer_country`, `buyer_emirate`, `exchange_rate`, `preceding_invoice`, `credit_reason` (needed on credit notes), `item_kind`, `hs_code`, `sac_code`, `unit_code` (unit of measure, UN/ECE Rec 20 such as EA, HUR or DAY), `base_quantity`, `line_allowance`, `line_charge`, `line_net_aed`, `vat_rate`, `line_vat`, `exemption_reason`.
- Optional totals: `invoice_total_net` and `invoice_total_vat`, checked against the sum of the lines.

UBL XML files are not supported yet. Say so and ask for a CSV export instead.
