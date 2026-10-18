# Saudi (ZATCA) checks: rules and sources

`engine/check_ksa.py` checks invoice data exported to CSV (one row per invoice line) against rules published by the Zakat, Tax and Customs Authority (ZATCA). It is a **data pre-check**. It does not build, sign, stamp, hash, send, report or clear invoices, and it does not create or verify QR codes, cryptographic stamps or invoice hashes. The final XML must still be validated with ZATCA's official tools (the ZATCA SDK or the Fatoora portal's validation). It is not tax advice.

Every check names the official rule id. Rules were read from these ZATCA documents only. The ZATCA SDK was not downloaded or used.

| Short name | Document | Version | Where |
| --- | --- | --- | --- |
| **XML Std** | E-Invoice XML Implementation Standard | v1.2, 2023-05-19 (file `20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_ vF.pdf`) | https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_ZATCA_Electronic_Invoice_XML_Implementation_Standard_%20vF.pdf |
| **DD** | E-Invoice Data Dictionary | 2023-05-19 vF (file `20230519_EInvoice_Data_Dictionary vF.xlsx`), sheet "Data dictionary" | https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20230519_EInvoice_Data_Dictionary%20vF.xlsx |
| **Security** | Electronic Invoice Security Features Implementation Standards | v1.1, 2022-06-24 | https://zatca.gov.sa/ar/E-Invoicing/SystemsDevelopers/Documents/20220624_ZATCA_Electronic_Invoice_Security_Features_Implementation_Standards.pdf |
| **Guideline** | E-Invoicing Detailed Guideline | Version 2, May 2023 | https://zatca.gov.sa/en/E-Invoicing/Introduction/Guidelines/Documents/E-Invoicing_Detailed__Guideline.pdf |

The documents are listed on ZATCA's pages https://zatca.gov.sa/en/E-Invoicing/SystemsDevelopers/Pages/E-Invoice-specifications.aspx and https://zatca.gov.sa/en/E-Invoicing/Introduction/Guidelines/Pages/default.aspx. Read on 2026-10-17; check them for newer versions.

## Rules checked

"Subtype" is positions 1 and 2 of the transaction code (KSA-2): `01` tax invoice, `02` simplified tax invoice. Credit and debit notes take the subtype of the invoice they amend.

### Required fields

| Rule | What the check does | CSV column | Source |
| --- | --- | --- | --- |
| `BR-02` | Invoice number present | `invoice_number` | XML Std 13.2.1 |
| `BR-03` | Issue date present | `issue_date` | XML Std 13.2.1 |
| `BR-04` | Invoice type code present | `type_code` | XML Std 13.2.1 |
| `BR-05` | Invoice currency present | `currency` | XML Std 13.2.1 |
| `BR-06` | Seller name present | `seller_name` | XML Std 13.2.1 |
| `BR-21` | Line identifier present | `line_id` | XML Std 13.2.1 |
| `BR-22` | Invoiced quantity present | `quantity` | XML Std 13.2.1 |
| `BR-24` | Line net amount present | `line_net` | XML Std 13.2.1 |
| `BR-25` | Item name present | `item_name` | XML Std 13.2.1 |
| `BR-26` | Item net price present | `unit_price` | XML Std 13.2.1 |
| `BR-CO-04` | Every line has a VAT category | `vat_category` | XML Std 13.2.2 |
| `BR-KSA-39` | Seller VAT number (or group VAT number) present | `seller_vat` | XML Std 13.3.1 |

### Dates, times and formats

| Rule | What the check does | CSV column | Source |
| --- | --- | --- | --- |
| `BR-KSA-F-01` | Dates are real dates written YYYY-MM-DD | `issue_date`, `supply_date`, `supply_end_date` | XML Std 13.3.5 |
| `BR-KSA-04` | Issue date is not later than today | `issue_date` | XML Std 13.3.1 |
| `BR-KSA-70` | Issue time present, written hh:mm:ss (Saudi time) or hh:mm:ssZ (UTC) | `issue_time` | XML Std 13.3.1; DD KSA-25 |
| `BR-KSA-35` | A supply end date needs a supply date | `supply_date`, `supply_end_date` | XML Std 13.3.1 |
| `BR-KSA-36` | Supply end date is not before the supply date | `supply_end_date` | XML Std 13.3.1 |
| `BR-KSA-F-04` | Amounts and quantities are not negative (credit notes carry positive amounts) | all number columns | XML Std 13.3.5 |
| `BR-KSA-F-06` | Text is no longer than the Data Dictionary maximum (invoice number 127, names and streets 1,000, city and district 127, line id 6, item name 1,000, note reason 1,000, billing reference 5,000, unit code 127) | as listed | XML Std 13.3.5; DD column "Number of characters (maximum limit)" |
| `BR-DEC-12`, `BR-DEC-13`, `BR-DEC-14`, `BR-DEC-15` | Invoice totals (without VAT, VAT, with VAT, VAT in SAR) have at most 2 decimals | `invoice_total_net`, `invoice_total_vat`, `invoice_total_gross`, `invoice_total_vat_sar` | XML Std 13.2.8 |
| `BR-DEC-23`, `BR-DEC-24`, `BR-DEC-27` | Line net amount, line allowance and line charge have at most 2 decimals | `line_net`, `line_allowance`, `line_charge` | XML Std 13.2.8 |
| `BR-KSA-DEC-03`, `BR-KSA-DEC-04` | Line VAT and line amount with VAT have at most 2 decimals | `line_vat`, `line_amount_with_vat` | XML Std 13.3.2 |

### Invoice type, transaction code, notes

| Rule | What the check does | CSV column | Source |
| --- | --- | --- | --- |
| `BR-KSA-05` | Type code is 388 (tax invoice), 386 (prepayment), 383 (debit note) or 381 (credit note) | `type_code` | XML Std 13.3.1 and 11.2.1 |
| `BR-KSA-06` | Transaction code present, 7 characters NNPNESB: NN is 01 or 02, positions 3 to 7 are 0 or 1 (third party, nominal, export, summary, self-billed) | `transaction_code` | XML Std 13.3.1 and 11.2.1; DD KSA-2 |
| `BR-KSA-07` | Export invoices (position 5) cannot be self-billed (position 7) | `transaction_code` | XML Std 13.3.1 |
| `BR-KSA-31` | Simplified invoices (02) may flag only third party, nominal and summary | `transaction_code` | XML Std 13.3.1 |
| `BR-KSA-15` | Tax invoices (388 with subtype 01) carry the supply date | `supply_date` | XML Std 13.3.1 |
| `BR-KSA-71` | Simplified summary invoices (02, position 6 = 1) carry the buyer name | `buyer_name` | XML Std 13.3.1 |
| `BR-KSA-72` | Simplified summary invoices carry a supply date and supply end date | `supply_date`, `supply_end_date` | XML Std 13.3.1 |
| `BR-KSA-56` | Credit notes (381) and debit notes (383) carry the billing reference (the original invoice number) | `preceding_invoice` | XML Std 13.3.1 |
| `BR-KSA-17` | Credit and debit notes carry the reason they were issued | `note_reason` | XML Std 13.3.1; DD KSA-10 |

### Currency

| Rule | What the check does | CSV column | Source |
| --- | --- | --- | --- |
| `BR-CL-04` | Invoice currency is a 3-letter code in capitals (the shape of ISO 4217; the full list is not bundled) | `currency` | XML Std 13.2.7 and 11.2.3 |
| `BR-KSA-EN16931-02` | When the file has a tax currency, it is SAR | `tax_currency` (optional) | XML Std 13.3.4 |
| `BR-53` | Invoices in a currency other than SAR give the total VAT in SAR (the tax currency, which BR-KSA-68 and BR-KSA-EN16931-02 make SAR) | `invoice_total_vat_sar` | XML Std 13.2.1 and 13.3.4 |

### Seller

| Rule | What the check does | CSV column | Source |
| --- | --- | --- | --- |
| `BR-KSA-40` | Seller VAT number is 15 digits, first and last digit 3 | `seller_vat` | XML Std 13.3.1 |
| `BR-KSA-08` | One seller ID, letters and digits only, with scheme CRN, MOM, MLS, 700, SAG or OTH (the DD marks it mandatory for every document type) | `seller_id`, `seller_id_scheme` | XML Std 13.3.1; DD BT-29 |
| `BR-KSA-09` | Seller address has street, building number, postal code, city, district and country | `seller_street`, `seller_building_number`, `seller_postal_code`, `seller_city`, `seller_district`, `seller_country` | XML Std 13.3.1 |
| `BR-KSA-37` | Seller building number is 4 digits | `seller_building_number` | XML Std 13.3.1 |
| `BR-KSA-66` | Seller postal code is 5 digits | `seller_postal_code` | XML Std 13.3.1 |
| `BR-CL-14` | Country codes are 2 capital letters (the shape of ISO 3166-1 alpha-2) | `seller_country`, `buyer_country` | XML Std 13.2.7 and 11.2.2 |

### Buyer

| Rule | What the check does | CSV column | Source |
| --- | --- | --- | --- |
| `BR-KSA-42` | Tax invoices and their notes (01) carry the buyer name | `buyer_name` | XML Std 13.3.1 |
| `BR-KSA-10` | Tax invoices and their notes (01) carry buyer street, city and country (also BR-10) | `buyer_street`, `buyer_city`, `buyer_country` | XML Std 13.3.1 and 13.2.1 |
| `BR-KSA-81` | Tax invoices and their notes (01) with no buyer VAT number carry another buyer ID | `buyer_id` | XML Std 13.3.1 |
| `BR-KSA-63` | Buyers in Saudi Arabia (country SA) have street, building number, postal code, city, district and country | `buyer_*` address columns | XML Std 13.3.1 |
| `BR-KSA-67` | A Saudi buyer's postal code is 5 digits | `buyer_postal_code` | XML Std 13.3.1 |
| `BR-KSA-44` | When present on a non-export invoice, the buyer VAT number is 15 digits, first and last digit 3 | `buyer_vat` | XML Std 13.3.1 |
| `BR-KSA-46` | Export invoices (position 5 = 1) carry no buyer VAT number | `buyer_vat` | XML Std 13.3.1 |
| `BR-KSA-14` | When present, the other buyer ID is letters and digits only with scheme TIN, CRN, MOM, MLS, 700, SAG, NAT, GCC, IQA, PAS or OTH (PAS is in the rule's list of schemes, though not in its summary line) | `buyer_id`, `buyer_id_scheme` | XML Std 13.3.1 |

### VAT

| Rule | What the check does | CSV column | Source |
| --- | --- | --- | --- |
| `BR-KSA-18` | VAT category is S, Z, E or O | `vat_category` | XML Std 13.3.1 and 11.2.4 |
| `BR-KSA-DEC-02` | VAT rate is 0 to 100 with at most 2 decimals, no % sign | `vat_rate` | XML Std 13.3.2 |
| `BR-48` | S, Z and E lines have a VAT rate (only "not subject to VAT" may go without one) | `vat_rate` | XML Std 13.2.1; DD BT-152 |
| `BR-Z-05` | Zero-rated (Z) lines have rate 0 | `vat_rate` | XML Std 13.2.4 |
| `BR-E-05` | Exempt (E) lines have rate 0 | `vat_rate` | XML Std 13.2.5 |
| `BR-KSA-11` | Not subject to VAT (O) lines have rate 0, if a rate is given | `vat_rate` | XML Std 13.3.1 |
| `BR-S-10` | Standard-rated (S) lines carry no exemption reason | `exemption_reason` | XML Std 13.2.3 |
| `BR-KSA-23` | Exempt (E) lines carry an exemption reason code | `exemption_reason` | XML Std 13.3.1 |
| `BR-KSA-69` | Zero-rated (Z) lines carry an exemption reason code | `exemption_reason` | XML Std 13.3.1 |
| `BR-KSA-24` | Not subject to VAT (O) lines carry an exception reason code | `exemption_reason` | XML Std 13.3.1 |
| `BR-KSA-CL-04` | The reason code is one listed for the line's category: E: VATEX-SA-29, VATEX-SA-29-7, VATEX-SA-30. Z: VATEX-SA-32, VATEX-SA-33, VATEX-SA-34-1 to VATEX-SA-34-5, VATEX-SA-35, VATEX-SA-36, VATEX-SA-EDU, VATEX-SA-HEA, VATEX-SA-MLTRY. O: VATEX-SA-OOS | `exemption_reason` | XML Std 13.3.3 and 11.2.4 |
| `BR-KSA-49` | VATEX-SA-EDU and VATEX-SA-HEA need the buyer's national ID (scheme NAT) | `buyer_id`, `buyer_id_scheme` | XML Std 13.3.1 |
| `BR-KSA-25` | Simplified invoices (02) with VATEX-SA-EDU or VATEX-SA-HEA carry the buyer name | `buyer_name` | XML Std 13.3.1 |
| `BR-KSA-52` | Tax invoices and their notes (01) carry the VAT amount on every line | `line_vat` | XML Std 13.3.1 |
| `BR-KSA-51` | When the file gives the line amount with VAT, it equals line net + line VAT | `line_amount_with_vat` (optional) | XML Std 13.3.1 |
| `BR-S-09`, `BR-Z-09`, `BR-E-09`, `BR-O-09` | Per invoice, one VAT breakdown for each category and rate: tax = sum of line nets x rate / 100, rounded half up to 2 decimals (so 0 for Z, E, O). The lines' VAT in that group must add up to it, allowing 0.005 per line for each line's own rounding. Skipped for a group when a line has no VAT amount | `line_vat` | XML Std 13.2.3 to 13.2.6, 9.6 and 10 |

### Line maths and line charges

| Rule | What the check does | CSV column | Source |
| --- | --- | --- | --- |
| `BR-KSA-EN16931-11` | Line net = quantity x (price / base quantity), rounded to 2 decimals, + line charge - line allowance (tolerance 0.01) | `line_net` | XML Std 13.3.4 and 9.3 |
| `BR-KSA-EN16931-12` | Base quantity is more than 0 (empty means 1) | `base_quantity` | XML Std 13.3.4 |
| `BR-KSA-20` | A line charge carries a reason code | `line_charge_reason_code` | XML Std 13.3.1 |
| `BR-KSA-22` | A line charge carries a reason in words | `line_charge_reason` | XML Std 13.3.1 |

### Invoice totals (optional columns)

| Rule | What the check does | CSV column | Source |
| --- | --- | --- | --- |
| `BR-CO-13` | Total without VAT = sum of line net amounts (the CSV has no document-level allowances or charges) | `invoice_total_net` | XML Std 13.2.2 |
| `BR-CO-14` | Total VAT = sum of the VAT breakdown amounts above | `invoice_total_vat` | XML Std 13.2.2 |
| `BR-CO-15` | Total with VAT = total without VAT + total VAT | `invoice_total_gross` | XML Std 13.2.2 |

### Phase 2 fields: presence only

These run only when the CSV has the column. They check that a value is there and has the shape the rule states. They never generate or verify an invoice counter, UUID, hash, QR code or cryptographic stamp; your e-invoicing solution produces those, and ZATCA's tools validate them.

| Rule | What the check does | CSV column | Source |
| --- | --- | --- | --- |
| `BR-KSA-03` | Each invoice has a UUID of letters, digits and dashes, and no two invoices in the file share one | `uuid` | XML Std 13.3.1; DD KSA-1 |
| `BR-KSA-33` | Each invoice has an invoice counter value | `invoice_counter` | XML Std 13.3.1; DD KSA-16 |
| `BR-KSA-34` | The invoice counter value is digits only | `invoice_counter` | XML Std 13.3.1 |
| `BR-KSA-61` | Each invoice has a previous invoice hash (its value is not checked) | `previous_invoice_hash` | XML Std 13.3.1; DD KSA-13; Security section 3 |

### Checks that are not ZATCA rules

| Id | What | Why |
| --- | --- | --- |
| `csv-number-format` | A number column holds something other than plain digits 0-9 and a dot (commas, %, currency signs, Arabic-Indic digits) | Needed to read the file. The DD format column asks for "Arabic numerals (The following numerals: 1234567890)" and BR-KSA-DEC-02 rejects the % sign |
| `csv-header-mismatch` | Lines of one invoice disagree on an invoice-level column, or two invoices share a number | Needed to read one invoice from several rows |
| `csv-duplicate-line` | Two or more lines of one invoice share a line id | A repeated row would be counted twice in the totals and VAT breakdown |
| `csv-unknown-column` | Warning only, not a gap: a column the check does not read, with the closest known name. Headers ignore case, spaces, hyphens and invisible characters, so "Buyer VAT" reads as `buyer_vat` | A misnamed column would otherwise be skipped without a word |
| `csv-s-rate` | Warning only, not a gap: a standard-rated (S) line with a rate other than 15 | Saudi VAT is 15% today, but no e-invoicing business rule fixes the S rate (see "Unconfirmed" below), so it is not reported as a gap |
| `guideline-4.2.1` | Warning only, not a gap: a simplified invoice (02) to a buyer with a VAT number for SAR 1,000 or more before VAT. Confirm the subtype | Guideline 2.3 and 4.2.1(b): simplified invoices for B2B are an option below SAR 1,000 |

## Not checked

- **Cryptographic stamp, QR code, previous invoice hash value** (BR-KSA-26 to BR-KSA-30, BR-KSA-60; Security sections 2 to 4). This tool never creates, signs or verifies them.
- **Prepayment invoices and adjustment lines** (BR-KSA-73 to BR-KSA-80, BR-KSA-82, BR-KSA-DEC-06): not modelled in the CSV.
- **Document-level allowances and charges** (BR-31, BR-32, BR-36, BR-37, BR-CO-11, BR-CO-12, BR-KSA-12, BR-KSA-13, BR-KSA-19, BR-KSA-21, BR-O-13, BR-KSA-EN16931-03 to -05): not modelled in the CSV.
- **Code lists that are not bundled**: payment means (BR-KSA-16, UNTDID 4461), charge reason codes (BR-KSA-CL-06, UNTDID 7161), the full ISO 4217 and ISO 3166 lists (only the shape is checked), MIME codes (BR-KSA-CL-03).
- **Exemption reason text** (BR-KSA-83): the CSV carries the code; your solution writes the matching text.
- **XML-only rules**: business process "reporting:1.0" (BR-KSA-EN16931-01), one tax total (BR-KSA-EN16931-08, -09), empty elements (BR-KSA-F-03), indicator values (BR-KSA-F-02), currencyID attributes (BR-KSA-CL-01, BR-KSA-CL-02), at least one VAT breakdown (BR-CO-18), file name (XML Std 14).
- **Line amount with VAT required** (BR-KSA-53): it is derived from line net + line VAT, so a missing column is not reported; when present, BR-KSA-51 checks it.

## Unconfirmed: left out on purpose

These are common expectations that we could not confirm as rules in the documents above, so the engine does not report them as gaps.

| Expectation | What the documents say |
| --- | --- |
| Standard-rated (S) lines must be 15% | No business rule fixes the S rate. The 15% figure appears only in examples (XML Std 9.4, 9.6; Guideline examples). BR-KSA-DEC-02 only limits rates to 0 to 100. The engine gives a warning (`csv-s-rate`), not a gap. |
| S lines must have a rate above 0 | BR-S-06 and BR-S-07 require it for document-level allowances and charges only; no line-level rule is published in XML Std 13.2.3. |
| Seller country must be SA | BR-KSA-09 requires a seller country code; no rule fixes its value. |
| Buyer VAT number always required on tax invoices (B2B) | Not a rule. The DD marks BT-48 conditional; BR-KSA-81 accepts another buyer ID instead. |
| Buyer building number 4 digits | BR-KSA-37 covers the seller only. BR-KSA-63 requires the buyer's building number for Saudi buyers but sets no length. |
| Unit of measure required | The DD marks BT-130 optional; XML Std 11.2.6 only recommends UN/ECE Rec 20 codes. |
| Line identifier numeric between 1 and 999,999 | DD BT-126 describes it, but no BR rule tests it; only the 6-character limit (BR-KSA-F-06) is checked. |
| Line VAT = line net x rate for each line | No rule for KSA-11 alone; VAT is set per breakdown (XML Std 9.6, BR-S-09 etc.), which is what the engine checks. |
