# Privacy policy: GCC E-invoicing Readiness Check (UAE and KSA)

Effective 18 October 2026. Publisher: Mindcat Technology Consultants FZE, Dubai. Contact: apps@mindcat.ai.

## What the plugin reads
Data you point it at:
- invoice exports as CSV or Excel (.xlsx);
- PINT AE UBL XML invoices and credit notes (one file or a folder);
- customer and item master data lists (CSV or .xlsx);
- a read-only sample pulled from your Salesforce org with your own login.

This can include customer names, TRNs, VAT numbers, addresses and invoice amounts.

## Where it runs
Everything runs in your own AI client (Claude Code, Cowork, Claude apps or Cursor) and on your own machine.

Anything Claude itself reads goes to your AI provider unmasked, under that client's own data terms. That includes the header row and the few sample rows Claude looks at to map your columns, and any Salesforce query results it sees. The skills tell Claude to read only the header row and at most 5 rows of a file, and to write Salesforce results to a file instead of the conversation.

The check's own output also goes to your AI provider. It is masked by default: TRNs, TINs, endpoint ids, Saudi VAT numbers and IDs, party names and Saudi street names show only their last 4 characters, and long cell text is cut to 60 characters. `--unmask` turns masking off; use it only when you accept that the full values go to your AI provider.

## What is stored
If you ask it to build a sample from Salesforce, it writes that sample as a CSV file on your own disk. If you ask for a gap report (`--report`) or a provider hand-off pack (`--handoff`), it creates those as new files where you say; it never replaces an existing file. The gap report is masked like the output. The hand-off pack holds no names, invoice numbers, TRNs or amounts. Nothing else is stored.

## What Mindcat receives
Nothing. The plugin has no Mindcat server, sends no data to Mindcat, and has no analytics or telemetry. Mindcat cannot see your data, your files or your use of the plugin.

## Third parties
The plugin sends data to no third party. Salesforce queries go from your machine to your own Salesforce org.

## Retention and deletion
Mindcat retains nothing, because it receives nothing. Files the plugin writes are on your disk; delete them when you like. Uninstall the plugin with `/plugin uninstall`.

## Children
The plugin is for businesses and is not intended for anyone under 18.

## Changes and contact
Changes to this policy are published in this file, with a new effective date. Questions: apps@mindcat.ai or https://mindcat.ai/contact. This policy covers the plugin only; https://mindcat.ai/privacy-policy covers the mindcat.ai website.
