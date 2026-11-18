"""Unit tests for .claude/hooks/block_destructive_sql.py.

Each case is either an attack the hook must block or a legitimate read it must
not break. Runs the hook as a real subprocess, exactly as Claude Code does.

    python -m unittest tests/test_block_destructive_sql.py -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "block_destructive_sql.py"


def run_hook(payload, raw=False):
    log = Path(tempfile.gettempdir()) / "hook-test.log"
    env = {**os.environ, "HOOK_LOG": str(log)}
    stdin = payload if raw else json.dumps(payload)
    proc = subprocess.run([sys.executable, str(HOOK)], input=stdin.encode("utf-8"),
                          capture_output=True, env=env, timeout=10)
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def sql(query, tool="mcp__supabase__execute_sql"):
    return {"tool_name": tool, "tool_input": {"query": query}}


class MustAllow(unittest.TestCase):
    CASES = {
        "plain select": "select count(*) from accounts",
        "cte select": "with live as (select * from subscriptions where ended_on is null) select count(*) from live",
        "keyword-like column names": "select updated_at, created_at, deleted_flag from accounts",
        "keyword inside string literal": "select * from invoices where payment_status = 'delete' or payment_status = 'drop table x'",
        "explain without analyze": "explain select * from accounts",
        "trailing semicolon and comment": "select 1; -- just a read",
        "uppercase select": "SELECT * FROM PLANS",
        "multiple reads": "select 1; select 2",
    }

    def test_reads_are_allowed(self):
        for name, query in self.CASES.items():
            with self.subTest(name):
                code, err = run_hook(sql(query))
                self.assertEqual(code, 0, f"{name} wrongly blocked: {err}")

    def test_other_claude_ai_connector_reads_allowed(self):
        code, _ = run_hook(sql("select 1", tool="mcp__claude_ai_Supabase__execute_sql"))
        self.assertEqual(code, 0)

    def test_non_sql_tool_passes_through(self):
        code, _ = run_hook({"tool_name": "mcp__supabase__list_tables", "tool_input": {}})
        self.assertEqual(code, 0)


class MustBlock(unittest.TestCase):
    CASES = {
        "delete": "delete from usage_daily where active_seats < 0",
        "uppercase drop": "DROP TABLE accounts",
        "stacked statement": "select 1; drop table plans",
        "block-comment hidden": "/* harmless */ delete from invoices",
        "line-comment hidden": "-- note\ntruncate invoices",
        "write inside cte": "with d as (delete from usage_daily returning *) select count(*) from d",
        "explain analyze executes": "explain analyze delete from accounts",
        "select into creates table": "select * into backup_accounts from accounts",
        "update": "update subscriptions set amount = 0",
        "insert": "insert into accounts (account_code) values ('X')",
        "alter": "alter table accounts add column x int",
        "grant": "grant all on accounts to anon",
        "dangerous function": "select pg_terminate_backend(1234)",
        "set_config": "select set_config('role', 'postgres', false)",
        "dollar-quoted do block": "do $$ begin delete from accounts; end $$",
        "empty query": "   ",
    }

    def test_writes_are_blocked(self):
        for name, query in self.CASES.items():
            with self.subTest(name):
                code, err = run_hook(sql(query))
                self.assertEqual(code, 2, f"{name} was NOT blocked")
                self.assertIn("BLOCKED by block_destructive_sql hook", err)

    def test_write_via_claude_ai_connector_blocked(self):
        code, _ = run_hook(sql("delete from accounts", tool="mcp__claude_ai_Supabase__execute_sql"))
        self.assertEqual(code, 2)

    def test_apply_migration_always_blocked(self):
        payload = {"tool_name": "mcp__supabase__apply_migration",
                   "tool_input": {"name": "harmless", "query": "select 1"}}
        code, _ = run_hook(payload)
        self.assertEqual(code, 2)

    def test_malformed_payload_fails_closed(self):
        code, _ = run_hook("this is not json", raw=True)
        self.assertEqual(code, 2)

    def test_bom_prefixed_payload_still_parsed(self):
        # PowerShell 5.1 pipes add a BOM; the hook must still read the SQL,
        # and block for the RIGHT reason, not just "unparseable".
        code, err = run_hook("﻿" + json.dumps(sql("drop table x")), raw=True)
        self.assertEqual(code, 2)
        self.assertIn("starts with 'drop'", err)

    def test_missing_query_fails_closed(self):
        code, _ = run_hook({"tool_name": "mcp__supabase__execute_sql", "tool_input": {}})
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
