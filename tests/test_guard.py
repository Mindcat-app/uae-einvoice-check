"""Run: python3 -I -m unittest discover -s tests (from the plugin root)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent.parent / "hooks" / "no_submit_guard.py"
ALLOW = [("Write", {"file_path": "r.md", "content": "This plugin never submits invoices. ASP clearance."}),
         ("Edit", {"new_string": "<form onSubmit={handleSubmit}>"}),
         ("Bash", {"command": "git commit -m 'fix form submit'"}),
         ("Read", {"file_path": "submitted-invoices.csv"}),
         ("Bash", {"command": "python3 -I engine/check_uae.py exports/Q3_reporting_clearance.csv"}),
         ("Bash", {"command": "sf data query -q 'SELECT Submitted_Date__c FROM blng__Invoice__c'"}),
         ("Bash", {"command": "curl https://docs.peppol.eu/poac/ae/pint-ae/resources.zip -o r.zip"}),
         ("mcp__salesforce__soqlQuery", {})]
DENY = [("Bash", {"command": "curl -X POST https://api.asp.example/v1/invoices -d @inv.xml"}),
        ("Bash", {"command": "curl --data-binary @inv.xml https://x/v1/documents"}),
        ("Bash", {"command": "curl -F f=@inv.xml https://x/peppol/send"}),
        ("Bash", {"command": "wget --post-file=inv.xml https://x"}),
        ("Bash", {"command": "http POST https://x inv=@a"}),
        ("Bash", {"command": "openssl dgst -sha256 -sign key.pem inv.xml"}),
        ("Bash", {"command": "sf data update record -s blng__Invoice__c -i a1 -v Status=Posted"}),
        ("mcp__asp__transmit_document", {}), ("mcp__zatca__report_invoice", {})]


def code(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, "-I", str(GUARD)], input=raw, capture_output=True, text=True).returncode


class Guard(unittest.TestCase):
    def test_allowed(self):
        for n, ti in ALLOW:
            with self.subTest(n=n, ti=ti):
                self.assertEqual(code({"tool_name": n, "tool_input": ti}), 0)

    def test_blocked(self):
        for n, ti in DENY:
            with self.subTest(n=n, ti=ti):
                self.assertEqual(code({"tool_name": n, "tool_input": ti}), 2)

    def test_fails_closed(self):
        self.assertEqual(code("garbage"), 2)
        self.assertEqual(code("{}"), 2)


if __name__ == "__main__":
    unittest.main()
