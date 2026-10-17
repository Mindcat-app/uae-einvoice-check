"""PreToolUse guard: this plugin checks invoices and must never sign, send, submit or change them.

Looks only at the command or tool name, not at file contents, so writing a report that says
"never submits" is fine. It is a backstop: the plugin itself has no tool that sends anything.
"""
import json
import re
import sys

# Command-line HTTP clients, and the flags that make them write.
HTTP_CLIENTS = {"curl", "wget", "http", "https", "xh", "httpie"}
HTTP_WRITE_FLAG = re.compile(r"(\s-X\s*(POST|PUT|PATCH|DELETE)\b|--request\s+(POST|PUT|PATCH|DELETE)\b|\s-d\b|--data|\s-F\b|--form|--upload-file|\s-T\b|--post-(data|file)|\s(POST|PUT|PATCH|DELETE)\s)", re.I)


def http_write(cmd):
    words = re.findall(r"[\w.-]+", cmd)
    if not any(w.lower() in HTTP_CLIENTS for w in words):
        return False
    return bool(HTTP_WRITE_FLAG.search(" " + cmd + " "))


SF_WRITE = re.compile(r"(?<![\w-])sf(dx)?(?![\w-])\s+.*?\b(data\s+(create|update|delete|upsert|import)|apex\s+run|project\s+deploy)\b", re.I | re.S)
SIGN = re.compile(r"(?<![\w-])openssl(?![\w-]).*\s-sign\b", re.I | re.S)
MCP_WRITE = re.compile(r"(submit|send|transmit|clear|report|sign|post|create|update|upsert|delete|issue)", re.I)


def block(why):
    print(f"mindcat-einvoice-check only checks invoices: {why}", file=sys.stderr)
    sys.exit(2)


try:
    data = json.load(sys.stdin)
    name = data["tool_name"]
    tin = data.get("tool_input") or {}
except Exception:
    block("could not read the tool call, so it is blocked")

if name == "Bash":
    cmd = str(tin.get("command", ""))
    if http_write(cmd):
        block("HTTP writes are blocked")
    for rx, why in ((SF_WRITE, "Salesforce writes are blocked"), (SIGN, "signing is blocked")):
        if rx.search(cmd):
            block(why)
elif name.startswith("mcp__"):
    tool = name.split("__")[-1]
    if MCP_WRITE.search(tool):
        block(f"the MCP tool '{tool}' looks like it sends or changes data")
sys.exit(0)
