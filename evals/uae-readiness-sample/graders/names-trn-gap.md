---
type: regex
pattern: "INV-1002[\\s\\S]*(TRN|ibr-132)|(TRN|ibr-132)[\\s\\S]*INV-1002"
flags: i
match: contains
target: last_message
---
