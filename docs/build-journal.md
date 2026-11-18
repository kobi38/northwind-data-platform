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
| 1 | 2. Semantic layer + `CLAUDE.md` | 2 | ✅ Done (written after the baseline, on purpose) |
| 2 | 3. Baseline eval (no semantic layer) | 3 | ✅ Done: 5/5, consistency PASS |
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

## Step 3 prep: testing the connection headlessly

**Decision:** run the **baseline eval first** (option A), *before* the semantic
layer exists. Then a before-and-after scorecard can show which written rule fixed
which question. The baseline is only possible now: once `docs/semantic-layer.md`
exists, a "no rules" run can't be measured again.

**What we did:** a cheap smoke test, one `claude -p` call (Haiku, 4-turn
cap, no built-in tools, only `list_tables` allowed) asking for the table list.

**What happened**
1. ✅ The read-only `supabase` server from `.mcp.json` loaded and was logged in.
   Claude tried to call `list_tables`.
2. ❌ The call was **denied**. Claude Code printed:
   *"Ignoring 13 permissions.allow entries from .claude/settings.json: this
   workspace has not been trusted."*
   **Concept: workspace trust.** A cloned repo could ship a `settings.json`
   that allows dangerous things. So Claude Code ignores a folder's `allow`
   rules until a human has accepted the folder once in the interactive
   "trust this folder?" dialog. **Deny rules still apply**, because loosening
   needs trust and tightening doesn't.
3. ⭐ **The agent refused to work around the denial.** It noticed it *could* get
   the same answer through `execute_sql`, said that would get around the
   block, and stopped to ask. A safe agent treats a denial as a decision,
   not an obstacle.

**Fix, and a second surprise:** the plan was for a human to run `claude` once
in the folder and accept the trust dialog. Deciding to trust a folder is the
user's call, not the agent's. The user did, but the warning stayed. Checking
`~/.claude.json` showed why: the **parent** folder `Agentic_AI_Course` was
already trusted, so the interactive session never showed a dialog and saved
nothing for `final-project`. Headless mode, however, checks the *exact* path.
With the user's decision made, the agent backed up the config
(`~/.claude.json.bak-before-trust`) and set `hasTrustDialogAccepted: true` for
that exact path. The re-test then read all 9 tables with zero denials.

**Lesson for the scheduled job (step 9):** interactive and headless sessions
can disagree about the same folder. A check that works in your terminal can
still fail at 6am. Test it the way it will actually run.

**Questions you might be asked**
- **"Why didn't your allow rules work?"** The folder wasn't trusted yet, a
  safety feature against malicious repos. Deny rules were enforced the whole time.
- **"Will the scheduled job hit this too?"** Yes, if the folder isn't trusted.
  That's one of the failures that only shows up unattended, which is why the
  spec insists on a real scheduled run.

---

## Step 3: Baseline eval (before any semantic layer)

**Goal:** measure how well the agent answers the 8 questions with **no**
business definitions written down. Repeating this after the semantic layer
exists shows what the documentation actually changed.

### 3a. A reusable question runner: `eval/ask_questions.py`

**Concept: an eval has two halves.**
- **The run** asks the questions and records what came back. That's our new script.
- **The grade** compares the recorded numbers to the answer key. That's
  `run_eval.py`, which we were given.

Keeping them separate means the system being measured never sees the key.

**What the script does**
1. Reads the 8 questions from `questions.yaml`.
2. Starts a **separate, fresh `claude -p` session for each question**
   (`--no-session-persistence`, 4 in parallel). The rules require fresh
   sessions: if c2 could see c1's answer, the consistency test would measure
   nothing.
3. Adds one formatting line to each question ("end with `ANSWER: <number>`")
   so the number can be read out mechanically. It says nothing about *how* to
   compute the answer.
4. Saves the full answer of every session to `eval/runs/before/<id>.json` as
   evidence, and the numbers only to `eval/results-before.yaml`.

**Guardrails on each session**
| Flag | Why |
|---|---|
| `--model claude-sonnet-5-5` | One fixed model, so before and after runs are comparable |
| `--tools Read` + Supabase read tools only | Same toolset in every run. Read is there so the *after* run can open the semantic layer. |
| `--disallowedTools Read(./project.md) Read(./eval/**) …` | Blocks files that would leak rules or answers: the spec spells out the MRR rules, `eval/` holds old answers and the key |
| `--permission-mode dontAsk` | Unattended: anything not allowed is denied, never prompted |
| `--max-turns 15`, 300 s timeout | A stuck session can't loop or bill forever |

### 3b. Result

```
q1-q5: 5/5 PASS    consistency c1-c3: PASS    cost ≈ $1.05
```
(Full scorecard: `eval/scorecard-before.txt`. No session even tried to read a
blocked file: zero permission denials.)

### 3c. What a 5/5 baseline means (the important part)

The schema is readable (`is_internal`, `billing_interval`, `status`), and a
strong model inferred the conventional rules: annual ÷ 12, exclude trials,
exclude internal accounts, paid invoices only. **But read the answers, not
just the score.** The agent openly made three judgment calls that the data
can't settle:

| Question | Agent's guess | It also offered |
|---|---|---|
| MRR | `past_due` still counts as live | a lower MRR if excluded |
| Cash collected | includes tax | a lower figure net of tax |
| Paying customers | an account with a live, non-trial contract | a lower count if "paying" means "paid an invoice in March" |

It guessed right each time. A different model, a rephrased question or a new
analyst could guess the other way. **That's the job of the semantic layer:
turn guesses into written decisions.**

**What this eval does *not* test** (the start of the write-up):
- **Model variation:** only one strong model was measured. A cheaper model
  (like the Haiku the scheduled job will use) wasn't.
- **Hard ambiguity:** no question forces a choice where the "obvious"
  convention is wrong for *this* business.
- **Other months:** everything is March / Q1. Mid-month starts, proration and
  the February upgrade-and-churn transitions are barely exercised.
- **Multi-currency:** every Northwind row is USD. The leftover `f_doc` tables
  are multi-currency, and the agent correctly ignored them on its own.
- **Data quality:** `usage_daily`'s dirty rows aren't touched by any question.

### How to explain step 3 in 30 seconds
> "Before writing any documentation I measured the agent cold: 8 questions,
> each in a fresh headless session, with the spec and answer key blocked. It
> scored 5/5. Reading its answers showed why that's not the whole story: it
> made three business-rule guesses it couldn't verify from the data, and said
> so. The semantic layer exists to turn those guesses into decisions, and the
> after run will show whether answers stop hedging."

### Questions you might be asked
- **"If it already scored 5/5, why build a semantic layer?"** The score
  measures this model on these 8 questions. The answers showed three guesses,
  and a different model or question could break any of them. Documentation is
  for every future question, not just these eight.
- **"How do you know it didn't cheat?"** The answer key and the schema
  comments were denied in settings, the spec and `eval/` were denied per run,
  and the logs show zero attempts to read any blocked file.

---

## Step 2: The semantic layer and `CLAUDE.md`

*(Done after step 3 on purpose: the baseline had to be measured before any
rules were written down.)*

**Goal (from the spec):** a document from which *someone who has never seen
the database can compute MRR correctly*, with `CLAUDE.md` pointing to it
instead of repeating it.

**Concept: semantic layer.** The schema says *what columns exist*
(`amount`, `billing_interval`, `status`). It can't say *what the business
decided*: that MRR divides annual contracts by 12, that `past_due` customers
still count, that cash includes tax. Those are decisions. The semantic layer
is where decisions are written down so every person and every AI session
makes the same ones.

### 2a. Profile the data first, write second

Before writing a single definition, we ran one profiling query against the
live database. The main session couldn't query directly, so a headless
`claude -p` run on Haiku with only `execute_sql` allowed ran the exact SQL.
It confirmed:

| Finding | Becomes which rule |
|---|---|
| Brightpath (ACC-1002) has **two** live contracts at once | Count customers by **distinct account**, not by row |
| `total_amount - tax_amount` = contract `amount` on every normal invoice | Proof that `total_amount` **includes tax** |
| The only mismatch is a `void` invoice (500 vs a 9600 contract) | Void invoices are adjustments: never include |
| Every `cancelled`/`churned` term has an `ended_on`. Every live status is open | Dates and statuses agree, so dates can be trusted for history |
| Cobalt's old term ends 02-14, new term starts 02-15 | `ended_on` is the **inclusive** last day |
| One `usage_daily` row points to an unknown account | `usage_daily` has no foreign key: validate it (step 8) |
| All rows are USD | Rule kept anyway: never sum across currencies |

### 2b. What's in `docs/semantic-layer.md`

| Section | Content |
|---|---|
| 1. Business | One paragraph: what Northwind sells and how it bills |
| 2. Tables | Grain of every table, join keys (`*_code`, never `*_id`), and the 4 leftover class tables marked "not Northwind" |
| 3. Vocabulary | Every status value: what it means, whether it's paying, whether it counts toward MRR |
| 4. Universal filters | Exclude internal, exclude trials, use the contract `amount` not list price, never mix currencies |
| 5. Metrics | MRR, paying customers, trial accounts, cash collected, net revenue, each with a definition and **canonical SQL** |
| 6. Gotchas | 13 traps, each one a way to get a wrong number |
| 7. Data-quality rules | What makes a `usage_daily` row valid (used by the scheduled check) |
| 8. Glossary | Plain definitions, including synonyms ("recurring revenue" = MRR) |
| 9. Answer protocol | How to answer: map to a metric, apply filters, use the SQL, state the definition |

### 2c. The key decisions (the three baseline guesses, now settled)

| Baseline guess | Now a written rule | Reasoning |
|---|---|---|
| `past_due` counts? | **Yes.** It's a live contract | A failing payment is a collections problem, not churn |
| Cash includes tax? | **Yes** | Cash = what landed in the bank, and `total_amount` is what the customer paid |
| "Paying" = live contract, or paid a March invoice? | **A live non-trial contract** at month end | An annual customer pays once a year but is a customer all year |

**One more decision the baseline never faced: what "in March" means.** We
defined it as a **month-end snapshot** (live on the last day of the month),
using **dates, not status**. Why it matters:
- *Status has no history.* Harbor Freight is `churned` **today** but was paying
  all of February. A status filter would drop it from February's MRR.
- *Upgrades overlap.* Cobalt's old and new terms both touch February. Summing
  every overlapping term would count Cobalt twice. A snapshot counts once.

The document includes a **worked example for February** (MRR 1539.00),
deliberately *not* March. It teaches the method and shows the trap without
handing the eval its answer.

### 2d. `CLAUDE.md`: a router, not a copy

`CLAUDE.md` is loaded into every Claude session automatically. It stays short
and says: *for any business question, read `docs/semantic-layer.md` first*.
It also lists the hard rules (read-only access, don't open the answer key,
don't hand-edit results, don't "fix" dirty usage rows).
**Why not put the definitions in `CLAUDE.md`?** Two copies drift apart. One
source of truth, many pointers to it.

### 2e. Verification

The canonical SQL from the document was run against the live database on
non-eval periods and checked by hand against the raw rows:

| Query | Result | Hand check |
|---|---|---|
| MRR, Feb 2026 | 1539.00 | 800 + 180 + 170 + 199 + 190 ✓ |
| Paying customers, Feb 2026 | 5 | Vertex, Brightpath, Nordwind, Cobalt, Harbor ✓ |
| Trial accounts, Feb 2026 | 2 | Lumen, Sable ✓ |
| Cash collected, Jan 2026 | 11921.13 | 5 paid January invoices, demo tenant excluded ✓ |

The real test, whether answers *change* with the document present, is the
"after" eval run in step 5.

### How to explain step 2 in 30 seconds
> "The schema tells you columns. It doesn't tell you decisions. I profiled the
> live data first, then wrote down every decision: what MRR includes, why
> past-due customers still count, why cash includes tax, why customers are
> counted by account. Every metric has canonical SQL, checked against the
> database. I used a month-end snapshot with dates instead of status, because
> status has no history, and I put a February worked example in the doc so it
> teaches the method without leaking the eval's March answers."

### Questions you might be asked
- **"Why canonical SQL? Isn't that spoon-feeding the AI?"** That's the
  point. A metric with one agreed query gives one answer. The eval's
  consistency test (three phrasings, one number) checks exactly that.
- **"Why a February example and not March?"** March is what the eval asks.
  An example with March numbers would turn the eval into copying.
- **"What happens when the business changes a rule?"** Change it in one
  place, `semantic-layer.md`, then re-run the eval to see what moved.

---

<!-- Next entry: Step 4 - eval skill / Step 5 - after-run and diagnosis -->
