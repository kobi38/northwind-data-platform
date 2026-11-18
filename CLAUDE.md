# Northwind Cloud Data Platform

An agentic analytics platform over Northwind Cloud's production database
(B2B SaaS subscriptions), hosted on Supabase.

## Before answering any business question

**Read [`docs/semantic-layer.md`](docs/semantic-layer.md) first.** It defines
MRR, paying customers, trials, cash collected, the join keys, the status
vocabulary and the gotchas. Use its definitions and canonical SQL. Don't
re-derive metrics from the schema or from general SaaS conventions.

## Data access

- Query the database **only** through the `supabase` MCP server (read-only,
  scoped to this project). Never attempt writes, DDL or migrations.
- Northwind tables: `accounts`, `plans`, `subscriptions`, `invoices`,
  `usage_daily`. Ignore every other table.

## Rules

- Never read or open `eval/golden.yaml` or `schema.sql`. They contain answers.
- Never hand-edit `eval/results*.yaml`. Results come only from
  `eval/ask_questions.py`.
- Never "fix" dirty rows in `usage_daily`. The data-quality check exists to find them.
- No secrets in the repo: `.env` and `.streamlit/secrets.toml` stay local.

## Where things live

| Path | What |
|---|---|
| `docs/semantic-layer.md` | Business definitions (the source of truth) |
| `docs/permissions.md` | Why the agent may and may not do each thing |
| `docs/build-journal.md` | Step-by-step build log |
| `eval/` | Questions, runner, grader, saved runs |
