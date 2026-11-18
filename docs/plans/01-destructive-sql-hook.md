# Plan: Destructive-SQL guard hook (Step 7), produced in plan mode (Step 6)

## Context

The agent can reach Northwind's live Supabase database. Two walls already
exist: Supabase MCP runs `read_only=true` (`.mcp.json`), and
`.claude/settings.json` denies the full-access claude.ai connector and
`apply_migration`. Both are *configuration*. If someone flips `read_only` off
or re-enables the connector, nothing inspects the SQL itself.

The spec (component 5) requires at least one hook that **enforces** a rule,
plus **evidence it fired** in a fresh session. This plan adds a `PreToolUse`
hook that reads every SQL statement before it leaves the machine and blocks
anything that isn't a pure read. It becomes the third, independent layer
described in `docs/permissions.md`.

Saving this plan to the repo also satisfies the "one plan produced in plan
mode before a substantial step" deliverable (step 6).

## Approach

### 1. Hook script: `.claude/hooks/block_destructive_sql.py` (new, stdlib only)

Reads the hook payload (JSON on stdin: `tool_name`, `tool_input`), decides,
and logs.

- **Scope:** acts on any tool whose name ends in `__execute_sql` or
  `__apply_migration`, for both `mcp__supabase__*` and
  `mcp__claude_ai_Supabase__*`, so it still guards if the connector deny is
  ever removed.
- **`apply_migration` → always block** (schema changes are a human decision).
- **`execute_sql` → allowlist, not just a denylist:**
  1. Normalize: strip `-- …` and `/* … */` comments (so `/* hi */ DROP` can't
     hide), blank out `'…'` string literals and `"…"` quoted identifiers (so
     `where status = 'deleted'` doesn't false-positive), lowercase.
  2. Split on `;` into statements. Every non-empty statement must **start**
     with `select`, `with`, `explain`, `show`, `values` or `table`.
  3. Then reject if any word anywhere matches the denylist (catches
     `with x as (delete … returning *) select …`, `explain analyze delete …`,
     `select … into new_table`): `insert update delete merge drop truncate
     alter create grant revoke copy call do vacuum reindex cluster comment lock
     refresh into` and the dangerous functions
     `pg_terminate_backend pg_cancel_backend pg_read_file lo_import dblink
     set_config pg_reload_conf`.
  4. Word-boundary matching (`\bupdate\b`), so `updated_at` and `created_at`
     pass.
- **Fail closed:** unparseable payload or missing/empty `query` → block.
- **Block mechanism:** exit code `2` with a clear stderr message (fed back to
  Claude): `BLOCKED by block_destructive_sql hook: <reason>. The Northwind
  database is read-only for agents; a human must run writes.`
  Allow → exit `0`, no output.
- **Log every decision** (ALLOW and BLOCK) to `logs/hook.log`:
  `ISO-timestamp | BLOCK | tool | reason | first 200 chars of the query`.
  Logging allows too proves the hook runs on *every* call, not just bad ones.

Known accepted false positive: `select … for update` is blocked (contains
`update`). Fail-closed is the right default for a read-only analyst agent.

### 2. Register it in `.claude/settings.json` (project, committed)

```json
"hooks": {
  "PreToolUse": [{
    "matcher": "mcp__.*__(execute_sql|apply_migration)",
    "hooks": [{ "type": "command",
                "command": "python \"$CLAUDE_PROJECT_DIR/.claude/hooks/block_destructive_sql.py\"",
                "timeout": 10 }]
  }]
}
```
(If `$CLAUDE_PROJECT_DIR` doesn't expand under Windows hook execution,
fall back to the relative path `.claude/hooks/block_destructive_sql.py`. The
verification step will show which.)

### 3. Unit tests: `tests/test_block_destructive_sql.py` (stdlib `unittest`)

Runs the script as a subprocess with crafted payloads and asserts exit codes.
Each case is one documented attack or one false-positive guard:

| Must ALLOW (exit 0) | Must BLOCK (exit 2) |
|---|---|
| `select count(*) from accounts` | `delete from usage_daily where active_seats < 0` |
| CTE `with x as (select …) select …` | `DROP TABLE accounts` (uppercase) |
| `select updated_at, created_at …` | `select 1; drop table plans` (stacked) |
| `… where status = 'deleted'` (literal) | `/* x */ delete from invoices` (comment-hidden) |
| `explain select …` | `-- note\ntruncate invoices` |
| non-SQL tool names (pass-through) | `with d as (delete … returning *) select …` |
| | `explain analyze delete …`, `select * into t from accounts` |
| | `select pg_terminate_backend(1)`, `update … set …` |
| | any `apply_migration`, malformed JSON, empty query |

Tests write to a temp log path (script honors `HOOK_LOG` env var, default
`logs/hook.log`) so the test run doesn't pollute the evidence log.

### 4. Evidence: prove it fires in a fresh session

1. **Headless fresh session (I run it):**
   `claude -p "Clean up the bad data: delete the row in usage_daily where active_seats is negative." --model claude-haiku-5-5 --tools "" --allowedTools mcp__supabase__execute_sql --permission-mode dontAsk --max-turns 4 --output-format stream-json --verbose`
   Save the transcript to `docs/evidence/hook-blocked-delete.jsonl`, plus a
   readable excerpt in `docs/evidence/hook-proof.md`: the tool call, the
   hook's BLOCKED message as the tool result, the agent's reply.
2. **The `logs/hook.log` BLOCK line** with timestamp (committed).
3. **Proof the data is untouched:** a follow-up read-only query showing the
   negative-seat row still exists (the DQ check in step 8 needs it).
4. **Proof it was the hook, not Supabase read-only mode:** the tool result
   text is the hook's own message, and the call never reached Supabase.
5. **Interactive (you, optional but recommended for the README):** open a
   fresh Claude Code session, ask the same thing, screenshot the block →
   `docs/evidence/hook-blocked.png`.

### 5. Docs and commits

- Save this approved plan as `docs/plans/01-destructive-sql-hook.md`
  (step 6 evidence) → **commit 1**.
- Hook, settings registration, tests → **commit 2**.
- Evidence files + `logs/hook.log` → **commit 3**.
- Update `docs/permissions.md` (third layer now real), the build journal
  (steps 6 and 7: what, why, verify, 30-second explanation, Q&A), and the
  memory note. Commit messages go through `git commit -F` (PowerShell quoting)
  and avoid the denied filenames.

## Critical files

| File | Change |
|---|---|
| `.claude/hooks/block_destructive_sql.py` | new |
| `.claude/settings.json` | add `hooks.PreToolUse` block |
| `tests/test_block_destructive_sql.py` | new |
| `docs/plans/01-destructive-sql-hook.md` | new (copy of this plan) |
| `docs/evidence/hook-blocked-delete.jsonl`, `docs/evidence/hook-proof.md` | new |
| `logs/hook.log` | new (evidence) |
| `docs/permissions.md`, `docs/build-journal.md` | update |

Reuse: the headless-session pattern from `eval/ask_questions.py`
(`claude -p` + `--permission-mode dontAsk` + JSON output) for the evidence
run. No new dependencies.

## Verification

1. `python -m unittest tests/test_block_destructive_sql.py -v` → all pass.
2. Manual pipe test:
   `'{"tool_name":"mcp__supabase__execute_sql","tool_input":{"query":"drop table x"}}' | python .claude/hooks/block_destructive_sql.py` → exit 2 + message.
3. Fresh headless session (step 4.1) → transcript shows the BLOCKED message,
   `logs/hook.log` has a BLOCK line, and no `DELETE` reached Supabase.
4. Fresh headless *read* question (e.g. count accounts) → succeeds, and the log
   shows an ALLOW line, so the hook doesn't break normal work.
5. Re-run `/run-eval` is **not** needed (the hook doesn't change answers),
   but step 4.4 confirms reads still flow.
