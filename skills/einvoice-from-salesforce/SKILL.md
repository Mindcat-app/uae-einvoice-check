---
name: einvoice-from-salesforce
description: Pull a read-only sample of invoices, lines and customers from Salesforce (Salesforce Billing, Revenue Cloud or custom invoice objects) and turn it into the CSV the UAE e-invoice check reads. Use inside einvoice-readiness when invoices live in Salesforce.
---

# Invoice data from Salesforce

Read-only SOQL only (`sf data query` or a read-only Salesforce MCP tool). Never update a record, even to fix a gap.

1. Find the invoice object: `blng__Invoice__c` and `blng__InvoiceLine__c` (Salesforce Billing), Revenue Cloud invoice objects, or a custom object. Ask if unsure.
2. Pull 20 recent invoices with their lines, the billing account and products.
3. Map fields to the columns in `${CLAUDE_PLUGIN_ROOT}/samples/uae-sample.csv`. A column with no source field is a gap in itself: list it as "no field holds this yet".
4. Write the CSV and run the check from `einvoice-readiness`.

Columns (one row per invoice line; header fields repeat on every line of an invoice):
- Required: `invoice_number`, `issue_date` (YYYY-MM-DD), `type_code`, `currency`, `seller_name`, `buyer_name`, `line_id`, `item_name`, `quantity`, `unit_price`, `line_net`, `vat_category`.
- Checked when present: `seller_trn`, `seller_tin`, `seller_country`, `seller_emirate`, `buyer_trn`, `buyer_country`, `buyer_emirate`, `exchange_rate`, `preceding_invoice`, `credit_reason` (needed on credit notes), `item_kind`, `hs_code`, `sac_code`, `unit_code` (unit of measure, UN/ECE Rec 20 such as EA, HUR or DAY), `base_quantity`, `line_allowance`, `line_charge`, `line_net_aed`, `vat_rate`, `line_vat`, `exemption_reason`.
- Optional totals: `invoice_total_net` and `invoice_total_vat`, checked against the sum of the lines.

Unit of measure is often on the product or the quote line (for example a `Unit of Measure` picklist). Map its values to Rec 20 codes; if no field holds it, say so.
