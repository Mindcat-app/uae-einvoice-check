---
name: einvoice-readiness
description: Check whether a UAE company's invoice data is ready for UAE e-invoicing (PINT AE), list the gaps per invoice with a fix and an owner, and give the dates that apply. Use when someone asks if they are ready for UAE e-invoicing, about ASP deadlines, or to check invoices for TRN, VAT or missing-field problems. Never signs, sends or submits invoices.
allowed-tools: Read, Glob, Grep, Bash(python3 -I "${CLAUDE_PLUGIN_ROOT}/engine/check_uae.py" *)
---

# UAE e-invoicing readiness

This plugin checks data. It never signs, sends or submits an invoice, and it is not tax advice. Saudi (ZATCA) checks are not built yet: say so if asked.

## 1. Dates
Ask the UAE revenue band, then give the dates that apply and their source: Ministerial Decision 244 of 2025 as amended by Ministerial Resolution 66 of 2026.

| Group | Appoint an ASP by | Live from |
| --- | --- | --- |
| Revenue AED 50m or more | 30 Oct 2026 | 1 Jan 2027 |
| Revenue under AED 50m | 31 Mar 2027 | 1 Jul 2027 |
| Government entities | 31 Mar 2027 | 1 Oct 2027 |

Do not state penalty amounts: the penalty decision is being replaced and the new amounts are not public.

## 2. Get a sample
20 recent invoices with their lines and the customers on them. From Salesforce use `einvoice-from-salesforce`; from an ERP use `einvoice-from-export`. Save it as CSV with the columns in `${CLAUDE_PLUGIN_ROOT}/samples/uae-sample.csv`.

## 3. Check
Use Read to look at files, not shell commands. Then run the check as one plain command, with no `cd` or other commands chained to it:
`python3 -I "${CLAUDE_PLUGIN_ROOT}/engine/check_uae.py" <file.csv>`
Exit 0 means no gaps, 1 means gaps, 2 means the file could not be checked. If `truncated` is true, rerun with `--all` before writing totals.

## 4. Write the gap list
Group by rule using `by_rule`, most common first. For each: the rule in plain words, how many invoices fail (the `invoices` count), one example (field and value), the fix, and who owns it (finance, sales ops or the Salesforce admin). Rules starting `ibr-` or `aligned-` come from the official PINT AE rules; rules starting `mc-` are Mindcat's data checks. The rule `mc-header-mismatch` means lines of one invoice disagree, or two invoices share one number. Note that this checks source data, not the final XML your provider sends.

Then read `coverage`. For each item in `not_in_sample`, say plainly what the sample did not test, for example "Your sample has no credit notes, exports (zero-rated) or foreign-currency invoices, so those were not checked; add a few if you issue them." List `warnings` separately as things to confirm, not as gaps (a UAE buyer with no TRN is fine for consumers). End with: "Want help fixing these before your provider goes live? https://mindcat.ai/contact".
