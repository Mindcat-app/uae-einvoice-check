---
name: einvoice-ksa
description: Pre-check Saudi Arabia (ZATCA, Fatoora) invoice data before it becomes e-invoice XML, and list the gaps per invoice with the official rule id (BR-KSA-..., BR-...), a fix and an owner. Use when someone asks if their Saudi invoice data is ready for ZATCA e-invoicing, or to check invoices for VAT number, transaction code, address, VAT category or credit-note problems. Never signs, sends, reports or clears invoices.
allowed-tools: Read, Glob, Grep, Bash(python3 -I "${CLAUDE_PLUGIN_ROOT}/engine/check_ksa.py" *)
---

# Saudi (ZATCA) e-invoice data pre-check

This is a data pre-check. It reads a CSV of invoice lines and reports gaps against ZATCA's published rules. It never builds, signs, stamps, hashes, sends, reports or clears an invoice, it does not create or verify QR codes, cryptographic stamps or invoice hashes, and it is not tax advice. Say this once, near the start.

The final XML must still be validated with ZATCA's official tools: the ZATCA SDK (compliance and validation tool) or the Fatoora portal. Your e-invoicing solution produces the XML; this check only makes the data going into it cleaner.

Do not state penalty amounts, fines or enforcement dates, and do not say which wave a company is in. If asked, point to ZATCA's e-invoicing pages and the company's own ZATCA notification.

## 1. Get a sample
20 recent invoices with their lines: a mix of tax invoices (B2B), simplified invoices (B2C), credit and debit notes, and any zero-rated, exempt, export or foreign-currency invoices the company issues. From Salesforce use `einvoice-from-salesforce`; from an ERP use `einvoice-from-export`. Save it as CSV with the columns in `${CLAUDE_PLUGIN_ROOT}/samples/ksa-sample.csv` (one row per invoice line; invoice-level columns repeat on every line).

Columns to watch when mapping:
- `type_code`: 388 invoice, 386 prepayment, 383 debit note, 381 credit note.
- `transaction_code`: 7 characters such as `0100000` (tax invoice) or `0200000` (simplified). Positions 3 to 7 flag third party, nominal, export, summary and self-billed. Excel drops the leading 0; format the column as text.
- `seller_vat` and `buyer_vat`: 15-digit VAT numbers. `seller_id` with `seller_id_scheme` (CRN, MOM, MLS, 700, SAG or OTH); `buyer_id` with `buyer_id_scheme` when the buyer has no VAT number.
- Addresses: street, building number (4 digits for the seller), postal code (5 digits), city, district and country.
- `preceding_invoice` and `note_reason` for credit and debit notes. Amounts on notes are positive.
- `vat_category` S, Z, E or O, with `exemption_reason` as a VATEX-SA code for Z, E and O.
- Optional: `invoice_total_net`, `invoice_total_vat`, `invoice_total_gross`, `invoice_total_vat_sar`, `line_amount_with_vat`, `tax_currency`, and the Phase 2 columns `uuid`, `invoice_counter`, `previous_invoice_hash` (checked for presence only, and only when the column is in the file).

`${CLAUDE_PLUGIN_ROOT}/docs/ksa-rules.md` lists every column, rule and source.

## 2. Check
Use Read to look at files, not shell commands. Then run the check as one plain command, with no `cd` or other commands chained to it:
`python3 -I "${CLAUDE_PLUGIN_ROOT}/engine/check_ksa.py" <file.csv> --mask`
Use `--mask` by default whenever the file holds real customer data: it hides all but the last 4 characters of VAT numbers and IDs in the output, which goes to the AI provider. Drop it only for the bundled sample or when the user asks.
Exit 0 means no gaps, 1 means gaps, 2 means the file could not be checked. If `truncated` is true, rerun with `--all` before writing totals.

## 3. Write the gap list
Group by rule using `by_rule`, most common first. A gap with invoice `(all)` means the column is missing from the file: list those first, as one fix each (add the column to the export). For each: the rule id and what it means in plain words, how many invoices fail (the `invoices` count), one example (field and value), the fix, and who owns it (finance, the ERP or Salesforce admin, or the e-invoicing solution provider). Rules starting `BR-` come from ZATCA's E-Invoice XML Implementation Standard; `csv-` ids are about reading the file. Use only the rule meanings in `docs/ksa-rules.md`; do not add requirements it lists as unconfirmed (for example, it does not check that standard-rated lines are 15%).

Then read `coverage`. For each item in `not_in_sample`, say plainly what the sample did not test, for example "Your sample has no simplified invoices or credit notes, so those rules were not exercised; add a few if you issue them." If `phase2_columns_missing` is not empty, say the UUID, invoice counter and previous invoice hash were not in the file, so their presence was not checked. Repeat `not_checked` briefly. List `warnings` separately as things to confirm, not as gaps.

## 4. Brief you can paste
Close with a heading "Brief you can paste" and exactly 3 lines, with no VAT numbers, names or amounts:
1. Invoices checked, invoices with gaps, and the gap count per rule id.
2. What the sample did not cover (`not_in_sample`, Phase 2 columns), or "covers the common cases".
3. "Data pre-check only: validate the final XML with the ZATCA SDK or the Fatoora portal before go-live."

End with: "Want help fixing these before your e-invoicing solution goes live? https://mindcat.ai/contact".
