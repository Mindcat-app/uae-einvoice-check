---
name: einvoice-from-salesforce
description: Pull a read-only sample of invoices, lines and customers from Salesforce (Salesforce Billing, Revenue Cloud or custom invoice objects) and turn it into the CSV the UAE or Saudi (ZATCA) e-invoice check reads. Use inside einvoice-readiness or einvoice-ksa when invoices live in Salesforce.
---

# Invoice data from Salesforce

Read-only SOQL only (`sf data query` or a read-only Salesforce MCP tool). Never update a record, even to fix a gap.

1. Find the invoice object: `blng__Invoice__c` and `blng__InvoiceLine__c` (Salesforce Billing), Revenue Cloud invoice objects, or a custom object. Ask if unsure.
2. Pull 20 recent invoices with their lines, the billing account and products.
3. Map fields to the columns in `${CLAUDE_PLUGIN_ROOT}/samples/uae-sample.csv` (the README lists what each holds). For `unit_code`, look at the product's unit of measure (`Product2.QuantityUnitOfMeasure` or the Billing equivalent); it must be a UN/ECE Rec 20 code in capitals (EA, HUR, DAY, MON, KGM). For credit notes, find the field that holds the reason (`credit_reason`). Write dates as YYYY-MM-DD and `exchange_rate` as AED per 1 unit of the invoice currency. A column with no source field is a gap in itself: list it as "no field holds this yet".
4. Write the CSV and run the check from `einvoice-readiness`.

## Fix pack for the Salesforce admin (text only)
When gaps come from fields Salesforce does not hold, you may output this pack. Label it "Suggestions for your Salesforce admin to review": the plugin never deploys or changes anything, and the admin decides names and where fields go (Account, Product2, or the invoice objects).

Suggested custom fields:
- Account: `VAT_TRN__c` (Text 15), `TIN__c` (Text 10), `Emirate__c` (picklist), `Peppol_Endpoint__c` (Text), `Peppol_Endpoint_Scheme__c` (Text 4, default 0235).
- Product2: `Item_Type__c` (picklist: Goods, Services, Both), `HS_Code__c` (Text), `SAC_Code__c` (Text), `UNECE_Unit_Code__c` (picklist), `VAT_Category__c` (picklist).
- Invoice (credit notes): `Credit_Reason__c` (picklist); invoice: `Transaction_Type__c` (Text 8, default 00000000).

Suggested picklist values:
- Emirate: AUH, DXB, SHJ, UAQ, FUJ, AJM, RAK (labels can say Abu Dhabi, Dubai and so on; the API value is the code).
- VAT category: S, Z, E, O, AE, N.
- Unit code: the UN/ECE Rec 20 codes the business uses, such as EA, HUR, DAY, MON, KGM, MTR, LTR.
- Credit reason: DL8.61.1.A, DL8.61.1.B, DL8.61.1.C, DL8.61.1.D, DL8.61.1.E, VD.

Suggested validation rules (Salesforce REGEX matches the whole value):
- TRN format, on Account: `AND(NOT(ISBLANK(VAT_TRN__c)), NOT(REGEX(VAT_TRN__c, "^1[0-9]{12}03$")))` with the message "TRN must be 15 digits, start with 1 and end with 03".
- TIN format: `AND(NOT(ISBLANK(TIN__c)), NOT(REGEX(TIN__c, "^1[0-9]{9}$")))`.
- Emirate for UAE accounts: `AND(OR(BillingCountry = "AE", BillingCountry = "United Arab Emirates"), ISBLANK(TEXT(Emirate__c)))` with the message "Pick the emirate for UAE accounts". If the org uses state and country picklists, compare `BillingCountryCode = "AE"` instead.
- Goods need an HS code, on Product2: `AND(OR(ISPICKVAL(Item_Type__c, "Goods"), ISPICKVAL(Item_Type__c, "Both")), ISBLANK(HS_Code__c))`; the same for services and `SAC_Code__c`.

Tell the admin to test new rules in a sandbox first, because existing records that fail them block later edits until fixed.

## Saudi (ZATCA) invoices
For Saudi invoices, map to the columns in `${CLAUDE_PLUGIN_ROOT}/samples/ksa-sample.csv` instead and run `einvoice-ksa`: `invoice_number`, `issue_date`, `issue_time`, `type_code` (388, 386, 383 or 381), `transaction_code` (7 characters such as 0100000; format as text), `currency`, `supply_date`, `supply_end_date`, `seller_name`, `seller_vat`, `seller_id`, `seller_id_scheme`, `seller_street`, `seller_building_number`, `seller_postal_code`, `seller_city`, `seller_district`, `seller_country`, the same `buyer_` columns, `preceding_invoice`, `note_reason`, `line_id`, `item_name`, `quantity`, `unit_code`, `unit_price`, `base_quantity`, `line_allowance`, `line_charge`, `line_net`, `vat_category` (S, Z, E or O), `vat_rate`, `line_vat`, `exemption_reason` (VATEX-SA codes), and optionally `invoice_total_net`, `invoice_total_vat`, `invoice_total_gross` and `invoice_total_vat_sar`. `${CLAUDE_PLUGIN_ROOT}/docs/ksa-rules.md` says what each holds.
