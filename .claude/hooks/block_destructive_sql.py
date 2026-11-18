"""
block_destructive_sql.py - PreToolUse guard for Supabase SQL tools.

Claude Code runs this BEFORE every matching tool call and pipes the call in as
JSON on stdin ({"tool_name": ..., "tool_input": {...}}). Exit codes:
    0 -> allow the call
    2 -> block it; stderr is shown to Claude as the reason

Policy: agents may only READ the Northwind database.
  - apply_migration is always blocked (schema changes are a human decision).
  - execute_sql is allowed only if every statement is a read: it must start
    with an allowlisted keyword AND contain no denylisted keyword anywhere
    (catches writes hidden in CTEs, EXPLAIN ANALYZE, SELECT ... INTO).
  - Anything unparseable fails closed (blocked).

Every decision, ALLOW and BLOCK, is appended to logs/hook.log (override with the
HOOK_LOG env var), so the log proves the guard runs on every call.

Layer 3 of 3. Layers 1-2 are Supabase read_only mode (.mcp.json) and the
permission deny rules (.claude/settings.json). See docs/permissions.md.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOG_PATH = Path(os.environ.get("HOOK_LOG", REPO / "logs" / "hook.log"))

ALLOWED_STARTS = {"select", "with", "explain", "show", "values", "table"}

DENIED_WORDS = {
    # writes and DDL
    "insert", "update", "delete", "merge", "drop", "truncate", "alter",
    "create", "grant", "revoke", "copy", "call", "do", "vacuum", "reindex",
    "cluster", "comment", "lock", "refresh",
    # SELECT ... INTO creates a table
    "into",
    # dangerous functions callable from a plain SELECT
    "pg_terminate_backend", "pg_cancel_backend", "pg_read_file",
    "pg_read_binary_file", "lo_import", "lo_export", "dblink", "dblink_exec",
    "set_config", "pg_reload_conf",
}

SUFFIX = ("The Northwind database is read-only for agents; "
          "a human must run writes.")


def log(decision, tool, reason, query):
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        snippet = " ".join((query or "").split())[:200]
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{stamp} | {decision} | {tool} | {reason} | {snippet}\n")
    except OSError:
        pass  # logging must never decide the outcome


def normalize(sql):
    """Remove comments and quoted text, lowercase. What's left is SQL keywords
    and identifiers only, so keywords can't hide in comments and words inside
    strings (e.g. status = 'deleted') can't cause false alarms."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)   # block comments
    sql = re.sub(r"--[^\n]*", " ", sql)                 # line comments
    sql = re.sub(r"'(?:[^']|'')*'", " '' ", sql)        # string literals
    sql = re.sub(r'"(?:[^"]|"")*"', ' "" ', sql)        # quoted identifiers
    sql = re.sub(r"\$([a-z_]*)\$.*?\$\1\$", " '' ", sql, flags=re.S | re.I)  # $$ bodies
    return sql.lower()


def check_sql(query):
    """Return None if the query is a pure read, else the reason to block."""
    if not query or not query.strip():
        return "empty or missing query"
    statements = [s.strip() for s in normalize(query).split(";") if s.strip()]
    if not statements:
        return "no SQL statement found"
    for stmt in statements:
        first = re.match(r"[a-z_]+", stmt)
        if not first or first.group(0) not in ALLOWED_STARTS:
            word = first.group(0) if first else stmt[:20]
            return f"statement starts with '{word}', not a read (select/with/explain/show/values/table)"
        for word in re.findall(r"\b[a-z_]+\b", stmt):
            if word in DENIED_WORDS:
                return f"contains forbidden keyword '{word}'"
    return None


def block(tool, reason, query):
    log("BLOCK", tool, reason, query)
    print(f"BLOCKED by block_destructive_sql hook: {reason}. {SUFFIX}",
          file=sys.stderr)
    sys.exit(2)


def main():
    # Read bytes and decode as UTF-8 ourselves: on Windows, sys.stdin uses the
    # locale code page (e.g. cp1255), which garbles non-ASCII text, and some
    # shells prepend a byte-order mark. utf-8-sig handles both.
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    try:
        payload = json.loads(raw)
        tool = payload["tool_name"]
        tool_input = payload.get("tool_input") or {}
    except (json.JSONDecodeError, KeyError, TypeError):
        block("unknown", "unparseable hook payload (fail closed)", raw[:200])

    if tool.endswith("__apply_migration"):
        block(tool, "schema migrations are never run by agents",
              tool_input.get("query") or tool_input.get("name"))

    if tool.endswith("__execute_sql"):
        query = tool_input.get("query")
        reason = check_sql(query)
        if reason:
            block(tool, reason, query)
        log("ALLOW", tool, "read-only query", query)

    sys.exit(0)


if __name__ == "__main__":
    main()
