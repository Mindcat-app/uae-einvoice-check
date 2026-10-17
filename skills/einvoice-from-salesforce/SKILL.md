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
