# Permissions: what the agent may and may not do

This agent can reach a live production database. Every rule in
[`.claude/settings.json`](../.claude/settings.json) answers one question:
*what is the worst thing that happens if the model gets this wrong?*

## One door to the database, and it only opens inward

| Rule | Why |
|---|---|
| `.mcp.json` connects Supabase with `read_only=true` | The server itself refuses writes, so even a perfectly phrased `DELETE` fails at Supabase. This is the outermost wall. It doesn't depend on the model or on our hook. |
| `features=database,docs` | The agent only needs to read tables. Branching, edge functions, storage and account management are never loaded, so they can't be misused. |
| `project_ref=...` | Scoped to the one Northwind project. Other projects in the account are invisible. |
| Deny `mcp__claude_ai_Supabase` | The account-level claude.ai connector has **full write access** to every project. Denying it in this repo leaves exactly one path to the data: the read-only one above. |
| Deny `mcp__supabase__apply_migration` | Schema changes are a human decision. This is defense in depth in case read-only mode is ever switched off. |
| Allow `execute_sql`, `list_tables` | Answering questions is the job. Prompting for every `SELECT` would teach the user to click "yes" without reading, which is worse than no prompt. |

The **third layer** is the `PreToolUse` hook
[`.claude/hooks/block_destructive_sql.py`](../.claude/hooks/block_destructive_sql.py).
It inspects the SQL text of every `execute_sql` call, on either Supabase
connector, and blocks anything that isn't a pure read before it leaves the
machine. It also always blocks `apply_migration` and logs every decision to
`logs/hook.log`. Unlike layers 1 and 2, it doesn't depend on configuration
staying correct: if read-only mode were switched off tomorrow, the hook would
still stop a `DELETE`. Proof it fires: [evidence/hook-proof.md](evidence/hook-proof.md).

**Why a hook and not just an instruction?** `CLAUDE.md` *asks* the agent not
to touch the dirty rows, and in testing the agent obeyed. But an instruction
can be misread, overridden by a confusing prompt, or ignored by a weaker
model. A hook is code that runs every time, whatever the model decides.

## The answer key stays sealed

| Rule | Why |
|---|---|
| Deny reading `eval/golden.yaml` | It's the answer key. A run that can see it measures nothing. |
| Deny reading `schema.sql` | Its trailing comment block lists every gold number. Everything else in it, the table shapes, is available live via `list_tables`. |
| Matching `Bash(...)`/`PowerShell(...)` denies | `Read` rules don't stop `cat golden.yaml`. The shell rules close that side door. `python run_eval.py` is still allowed, because the grader is supposed to read the key. |

## Secrets never enter the context

`.env` and `.streamlit/secrets.toml` hold the database connection string used by
the dashboard. The agent has no reason to read them. Anything it reads can end
up in a transcript, a log or a commit.

## Git: work freely, publish deliberately

`status`/`diff`/`log` are allowed because they're harmless. `git push` asks
first, because publishing is outward-facing and hard to undo. Force-push and
recursive deletes are denied outright.

## Known limits

- Shell deny rules match command text, which cuts both ways. They over-block:
  the very first commit after adding them was refused because its *message*
  mentioned the answer-key filename. They also under-block: an obfuscated
  command could still slip past them. Supabase read-only mode and the hook don't share that weakness.
- `.claude/settings.local.json` (gitignored) can loosen these rules on one
  machine. That's intentional for personal overrides, but it means a checked-in
  policy isn't a guarantee on someone else's machine.
