# Build Journal: Northwind Cloud Agentic Data Platform

A step-by-step record of how this platform was built: **what** was done,
**why**, **how to check it**, and **how to explain it** to someone else.
It's updated at the end of every step.

---

## Progress

| Phase | Step | Component | Status |
|---|---|---|---|
| 0 | Survey the project | - | ✅ Done |
| 1 | 1. Repo, `.gitignore`, MCP, permissions | 1 | ✅ Done (one action left for you, see below) |
| 1 | 2. Semantic layer + `CLAUDE.md` | 2 | ⬜ |
| 2 | 3. Baseline eval (optional) | 3 | ⬜ |
| 2 | 4. "Run the eval" skill | 4 | ⬜ |
| 2 | 5. Grade + diagnose failures | 3 | ⬜ |
| 3 | 6. Plan-mode plan saved | evidence | ⬜ |
| 3 | 7. Destructive-SQL hook + proof | 5 | ⬜ |
| 4 | 8. Headless data-quality check | 6 | ⬜ |
| 4 | 9. Schedule → log entry → unschedule | 6 | ⬜ |
| 5 | 10. Streamlit dashboard + screenshot | 7 | ⬜ |
| 5 | 11. README + publish to GitHub | - | ⬜ |

---

## The big picture (read this first)

The project asks for a **platform** that answers business questions correctly
on its own, not for the answers themselves. Each component closes one way an AI
data agent goes wrong:

| Failure mode | Component that prevents it |
|---|---|
| The agent doesn't know what the business means by "MRR" | **Semantic layer**: written definitions |
| We can't tell whether the agent is right | **Eval**: fixed questions graded against an answer key |
| A useful procedure is redone by hand, differently each time | **Skill**: the procedure written down once |
| A rule is only *requested* ("please don't delete") | **Hook**: a rule *enforced* in code |
| Checks only happen when someone remembers | **Headless script + schedule**: runs without a human |
| Nobody outside the terminal can see the numbers | **Dashboard**: the same rules, on a screen |

**One-sentence version:** *"I built the documentation, guardrails, tests and
automation that let an AI agent answer questions about a production database
correctly and safely, without me in the loop."*

---

## Step 0: Survey before building

**What we did**
- Read `project.md` (the spec), `schema.sql` (the database), `eval/questions.yaml`,
  `eval/results-template.yaml` and `eval/run_eval.py`.
- **Did not** read `eval/golden.yaml`. It's the answer key, and the spec
  says to read it only when grading.
- Checked the installed tools: git, Python 3.12, Node and Claude Code are present.
  The GitHub CLI (`gh`), Streamlit and the Supabase CLI are not.
- Checked Supabase: the project `atlas-practice` already has the five Northwind
  tables loaded with the expected row counts (accounts 8, plans 3,
  subscriptions 10, invoices 16, usage_daily 16). Four empty leftover tables
  from class (`d_ent`, `d_sku`, `f_doc`, `f_doc_ln`) are also there.

**What we discovered (important)**
1. **`schema.sql` contains the answers.** The comment block at its end
   ("Instructor reference") lists every gold number. If Claude reads that file
   while answering the eval questions, the eval is contaminated: it would be
   copying, not computing.
2. **The Supabase connector has write access.** The account-wide claude.ai
   connector can run any SQL and apply migrations on every project. A
   misunderstanding could change real data.

**Why this step matters / how to explain it**
> "Before building anything I surveyed what I'd been given and what could hurt
> me. I found two risks: the answer key was leaking through the schema file, and
> the agent had write access to a live database. Both shaped my first step."

---

## Step 1: Repo, `.gitignore`, MCP connection, permissions

**Goal (from the spec):** a git repo with `.gitignore` written *before* the
first commit, Supabase connected through MCP, and permissions chosen deliberately
with the reasoning written down.

### 1a. `git init` + `.gitignore` first

**What:** `git init -b main`, then wrote [`.gitignore`](../.gitignore)
*before* committing anything.

**Why the order matters:** git never forgets. If a secret (database password,
API key) is committed even once, it stays in the history after you delete the
file, and a public repo is scanned by bots within minutes. Writing `.gitignore`
first means a secret can't be staged by accident.

**What it ignores, and why:**
| Pattern | Reason |
|---|---|
| `.env`, `.env.*` | Where connection strings and keys usually live |
| `.streamlit/secrets.toml` | Where the dashboard will keep its database password |
| `.claude/settings.local.json` | Personal, machine-specific Claude settings |
| `__pycache__/`, `.venv/` | Generated Python files, not source |
| `data-helpers-hook.log` | Written by a Claude Code plugin on every edit, not project data |

**Commit 1:** `.gitignore` plus the files we were given (spec, schema, eval).

### 1b. `.mcp.json`: a read-only, single-project database connection

**What:** [`.mcp.json`](../.mcp.json) defines a Supabase MCP server for this
project only:
```
https://mcp.supabase.com/mcp?project_ref=egzungqlpsseljrcokmy&read_only=true&features=database,docs
```

**Key concept: MCP (Model Context Protocol).** It's how Claude gets *tools*
beyond reading files, here "run SQL on Supabase". The `.mcp.json` file in the
repo means anyone who clones it gets the same connection, configured the same
way.

**Each URL parameter is a decision:**
| Parameter | Effect | Why |
|---|---|---|
| `project_ref=...` | Only this one project is visible | Least privilege: the agent can't touch other projects |
| `read_only=true` | Supabase itself refuses writes | The strongest guard, because it doesn't depend on the AI behaving |
| `features=database,docs` | Only database and docs tools are loaded | Branching, storage, edge functions and account tools never exist for the agent |

No password is in this file. Login happens through OAuth (a browser login),
so the file is safe to commit.

### 1c. `.claude/settings.json`: deliberate permissions

**Key concept: three lists.**
- **allow**: runs without asking
- **ask**: Claude must get your OK each time
- **deny**: blocked outright, and **deny always wins**

**The rules and the reasoning** (full version in [permissions.md](permissions.md)):

| Rule | Type | Why |
|---|---|---|
| `mcp__claude_ai_Supabase` | deny | The account-wide connector has full write access. Blocking it leaves one path to the data: the read-only one. |
| `mcp__supabase__apply_migration` | deny | Schema changes are a human decision. Backup in case read-only is ever turned off. |
| `mcp__supabase__execute_sql`, `list_tables`, … | allow | Answering questions is the job. Prompting on every `SELECT` trains people to click "yes" blindly. |
| `Read(./eval/golden.yaml)`, `Read(./schema.sql)` | deny | Seals the answer key so the eval measures real computation |
| `Bash/PowerShell(*golden.yaml*)`, `(*schema.sql*)` | deny | `Read` rules don't stop `cat golden.yaml`. This closes the shell side door. |
| `Read(./.env)`, `Read(./.streamlit/secrets.toml)` | deny | Secrets never enter the AI's context, so they can't leak into logs or commits |
| `git status/diff/log` | allow | Harmless, used constantly |
| `git push` | ask | Publishing is outward-facing and hard to undo |
| `git push --force`, recursive delete | deny | Destroys history or files with no undo |
| `enabledMcpjsonServers: ["supabase"]` | approve | Explicitly approves *only* our server from `.mcp.json` |

**The idea of layers (defense in depth):** for the database there are three
independent walls:
1. **Supabase read-only mode**: the server refuses writes.
2. **Permissions**: the dangerous tools are denied.
3. **The hook** (step 7): inspects the SQL text and blocks destructive statements.

If one wall fails, the next still holds.

### 1d. Evidence the rules work (it happened live)

1. **The connector block worked instantly.** As soon as `settings.json` was
   saved, the running Claude session lost its claude.ai Supabase tools.
2. **The answer-key block worked, and showed its cost.** The commit for this
   step was **refused** because its *commit message* contained the word
   `golden.yaml`, which matched `PowerShell(*golden.yaml*)`. We reworded the
   message and recorded this in `permissions.md` as a known limit: text-matching
   rules can over-block (harmless commands that mention the name) and
   under-block (a cleverly disguised command).

**Commit 2:** `.mcp.json`, `.claude/settings.json`, `docs/permissions.md`.

### How to check it yourself
```powershell
git log --oneline              # two commits, .gitignore came first
git show --stat HEAD~1         # first commit includes .gitignore
git check-ignore -v .env       # confirms .env would be ignored
```

### ⚠️ Action left for you
Open a **new** Claude Code session in this folder, run `/mcp`, choose
`supabase` and complete the browser login. Then ask *"list the tables"*.
You should see the Northwind tables. Until you log in, Claude has no
database access in this project, because the old connector is denied on purpose.

### How to explain step 1 in 30 seconds
> "The agent holds live database credentials, so I started with safety. The
> `.gitignore` went in before the first commit so secrets can never be
> committed. The database connection is read-only at the server, scoped to one
> project, with only the tools it needs. On top of that, a permission file
> denies the full-access connector, schema changes, and reading the answer key.
> I tested it while building: the rules blocked access immediately, and one
> rule was strict enough to block my own commit message, which I documented as
> a known trade-off."

### Questions you might be asked
- **"Why not just tell Claude in CLAUDE.md not to write to the database?"**
  A request isn't enforcement. The model usually complies, but "usually" isn't
  good enough with production data. Read-only mode and deny rules don't depend
  on the model's judgment.
- **"Isn't the project ref a secret?"** No. It's an identifier, like a URL.
  Access needs an authenticated login, which isn't in the repo.
- **"Why allow `execute_sql` without asking?"** The server is read-only, so the
  worst a query can do is read. Asking every time adds friction without adding
  safety.

---

<!-- Next entry: Step 2 - semantic layer -->
