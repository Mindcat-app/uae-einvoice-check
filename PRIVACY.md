# Privacy policy: UAE E-invoicing Readiness Check

Effective 17 October 2026. Publisher: Mindcat Technology Consultants FZE, Dubai. Contact: apps@mindcat.ai.

## What the plugin reads
Invoice data you point it at: a CSV export, or a read-only sample pulled from your Salesforce org with your own login. This can include customer names, TRNs, addresses and invoice amounts.

## Where it runs
Everything runs in your own AI client (Claude Code, Cowork, Claude apps or Cursor) and on your own machine. What the plugin reads, and the check's output, pass through that client's conversation to your AI provider, under that client's own data terms. Run the check with `--mask` to hide all but the last 4 characters of TRNs and TINs in its output.

## What is stored
If you ask it to build a sample from Salesforce, it writes that sample as a CSV file on your own disk. If you ask for a gap report (`--report`) or a provider hand-off pack (`--handoff`), it writes those to the folder you name. The hand-off pack holds no names, invoice numbers, TRNs or amounts. Nothing else is stored.

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
