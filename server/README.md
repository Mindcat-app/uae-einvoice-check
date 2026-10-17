# Hosted rule server (to build in phase 3)

Remote MCP server over HTTPS with OAuth sign-in. Runs in a UAE region (and KSA for Saudi customers); no invoice data on non-GCC hosts.

| Tool | Input | Output |
| --- | --- | --- |
| `check_invoice` | one UBL XML, JSON or CSV row set | pass, or failed rules with field, value and fix |
| `check_batch` | up to a few thousand invoices | counts per rule, 20 worst invoices |
| `check_party` | a customer or supplier record | TRN/TIN, address and emirate problems |
| `map_fields` | a sample export | proposed mapping to the 51 UAE fields, gaps marked |
| `explain_rule` | a rule id | plain words, source line, example fix |
| `deadline_for` | country, revenue band, sector | dates and the decision that sets them |

All tools are read-only (`readOnlyHint: true`). None signs, sends or submits.

Rule sources, loaded by version (a daily job checks for new releases):
- PINT AE v1.0.4 Schematron: https://docs.peppol.eu/poac/ae/pint-ae/resources.zip
- ZATCA XML Implementation Standard v1.2 business rules
