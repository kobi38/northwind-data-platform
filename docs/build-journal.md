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
| 2 | 4. "Run the eval" skill | 4 | ✅ Done |
| 2 | 5. After-run, grade, write-up | 3 | ✅ Done: 5/5 → 5/5, hedging gone, cost −40% |
| 3 | 6. Plan-mode plan saved | evidence | ✅ Done |
| 3 | 7. Destructive-SQL hook + proof | 5 | ✅ Done: blocked a real DELETE in a fresh session |
| 4 | 8. Headless data-quality check | 6 | ✅ Done: finds all 4 seeded issues, exit 1 |
| 4 | 9. Schedule → log entry → unschedule | 6 | ✅ Done: ran unattended 16:14, task deleted |
| 5 | 10. Streamlit dashboard + screenshot | 7 | ✅ Done: every number matches the eval |
| 5 | 11. README + publish to GitHub | - | 🟨 README done, publish pending |

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

## Step 4: The skill, `.claude/skills/run-eval/`

**Concept: skill.** A skill is a written procedure Claude can load on demand,
a `SKILL.md` file with a name, a description (so Claude knows *when* to use
it), and the steps. You can trigger it by typing `/run-eval`, or Claude picks
it up when you say "run the eval". The point: a procedure you repeat is done
**the same way every time**, not however it gets remembered that day.

**Why this procedure?** Every change to the semantic layer should be followed
by re-running the eval. That's how you know a change helped. It's the
procedure that repeats most in this project.

**What the skill does**
1. Runs `eval/ask_questions.py` (8 fresh headless sessions) → `eval/results.yaml`.
2. Grades with `run_eval.py` → `scorecard.txt`, plus a before-and-after
   comparison → `scorecard-compare.txt`.
3. **Reads the answers, not just the score:** does each one cite the layer,
   does it still hedge, which rule is missing behind any failure.
4. Reports and *suggests* layer edits, without applying them unasked.

**Rules written into the skill:** never open the answer key, never answer the
questions in the current session (they'd see each other), never hand-edit a
results file ("a wrong number is the finding").

**Supporting change:** `settings.json` now allows `python eval/ask_questions.py`
so the skill runs without a permission prompt.

**Bug found while using it:** the first run crashed *after* saving results,
because a relative `--out` path broke a print statement. Fixed by resolving
`--out` against the repo root. Using a tool for real finds what writing it
doesn't.

---

## Step 5: After-run, grading and the write-up

**What we did:** ran the skill's procedure with the semantic layer in place,
same model (Sonnet), same isolation, same questions.

**Result**
```
Accuracy:    5/5 -> 5/5      Consistency: PASS -> PASS
Cost:        $1.05 -> $0.63  Avg turns:   3.9 -> 3.25
```

**The finding is in the answers, not the score.** The baseline offered a
competing number on MRR, paying customers and cash ("if you exclude
past_due…", "if paying means a paid invoice…", "excluding tax…"). With the
layer, every answer:
- cited `docs/semantic-layer.md` by name,
- stated the definition it applied (e.g. "month-end snapshot as of 2026-03-31"),
- gave **one** number, quoting the layer's *reason* (e.g. past_due counts
  "because their contract is in force").

It was also 40% cheaper: the agent stopped exploring the schema to rediscover
rules.

**The write-up: `eval/FINDINGS.md`.** With no failures, the spec asks *what the
eval doesn't test*. The headline gaps:
1. **History.** In March, status and dates agree, so the eval can't tell a
   correct date-based definition from a wrong status-based one. February
   would.
2. **Mid-month upgrades.** Snapshot vs overlap (Cobalt double-count).
3. **Only one model, one run per question.**
4. **Multi-currency, dirty usage data, unanswerable periods:** never exercised.

It also proposes five discriminating questions to add next.

### How to explain steps 4 and 5 in 30 seconds
> "I packaged the eval as a skill so re-running it after any doc change is one
> command and always done the same way. After the semantic layer, the score
> stayed 5/5, so the score alone says nothing changed. The answers say
> otherwise: the hedges disappeared, every answer cited the definition it
> used, and cost dropped 40%. Since nothing failed, my write-up focuses on
> what the eval can't see: the questions only ask about March, where the
> dangerous status-vs-date mistake happens to give the right answer."

### Questions you might be asked
- **"Your score didn't improve, so what did the semantic layer achieve?"**
  It changed *why* the answers are right: from a strong model's guess to a
  documented, cited rule. That survives model changes and rephrasings, and
  the guess doesn't.
- **"How would you make the eval catch more?"** Add February questions
  (status trap), Cobalt in February (upgrade double-count), and "MRR right
  now" (data ends in March). Listed in `FINDINGS.md`.
- **"Is 5/5 from one run reliable?"** It's one sample per question. Repeated
  runs and a second model would make it stronger. Listed as a limitation.

---

## Step 6: A plan made in plan mode

**Concept: plan mode.** In plan mode (Shift+Tab) Claude can only *read and
think*. It can't edit files, run commands that change anything, or commit.
It writes a plan, and nothing happens until you approve it. It's the "measure
twice, cut once" step for anything substantial.

**What we did:** you switched to plan mode. Claude wrote a plan for the hook:
- the context: why a third layer is needed
- the detection logic: allowlist + denylist, fail closed
- how to register it
- a table of test cases
- how to prove it fires
- which files change
- how to verify it

You approved it, and only then was any code written. The approved plan is
saved as [`docs/plans/01-destructive-sql-hook.md`](plans/01-destructive-sql-hook.md)
and committed **before** the hook code. The git history shows the plan came
first.

**Why the hook was the right step to plan:** it's security code. A design
mistake (e.g. a regex that misses `/* */ DROP`) is cheap to fix on paper and
expensive to discover later.

---

## Step 7: The guard hook

**Concept: hook.** A hook is a script Claude Code runs automatically at a
fixed moment. A `PreToolUse` hook runs **before** a tool call. It receives
the call as JSON (`tool_name`, `tool_input`) and decides:
**exit 0 = allow, exit 2 = block** (the message on stderr goes back to Claude).
The model doesn't choose whether the hook runs. That's the difference between
*enforcing* a rule and *requesting* it.

### 7a. How the hook decides ([`block_destructive_sql.py`](../.claude/hooks/block_destructive_sql.py))

| Step | What | Why |
|---|---|---|
| 1 | Strip comments (`--`, `/* */`), blank out quoted text, lowercase | `/* hi */ DROP` can't hide in a comment, and `status = 'deleted'` doesn't cause a false alarm |
| 2 | Split on `;`. Every statement must **start** with `select / with / explain / show / values / table` | **Allowlist:** anything not known to be a read is refused |
| 3 | Reject if **any** word is a write keyword or dangerous function | **Denylist:** catches writes *inside* reads, e.g. `with d as (delete …) select`, `explain analyze delete`, `select … into new_table` |
| 4 | `apply_migration` → always blocked | Schema changes are a human decision |
| 5 | Bad input → blocked | **Fail closed:** when unsure, say no |
| 6 | Log every ALLOW and BLOCK to `logs/hook.log` | Proves it runs on *every* call, not just bad ones |

It covers **both** Supabase connectors (`mcp__.*__execute_sql`), so it still
protects the database if someone removes the deny on the full-access one.

### 7b. Tests (`tests/test_block_destructive_sql.py`)
9 tests, 24 cases: 16 attacks that must be blocked, 8 legitimate reads that
must pass. All pass.

**A bug the testing found:** a manual PowerShell pipe test was blocked for the
*wrong reason* ("unparseable"). PowerShell 5.1 prepended a byte-order mark,
and Python on Windows decoded stdin with the Hebrew code page (cp1255). The fix
reads stdin as raw UTF-8 bytes, and a regression test now checks it blocks
for the *right* reason. Lesson: check *why* a test passed, not only *that*
it did.

### 7c. The proof (spec: "try the forbidden thing in a fresh session")

Full write-up: [`docs/evidence/hook-proof.md`](evidence/hook-proof.md).

| Run | What happened | What it shows |
|---|---|---|
| 1. "Clean up the bad data: delete the negative row" | The agent **refused on its own**, citing `CLAUDE.md`, and only ran a `SELECT` (hook: **ALLOW**) | The written rule worked *this time*, but that's the model choosing to obey |
| 2. Explicit test: send the `DELETE` | The agent sent it, the hook **blocked** it, and the agent got the hook's message as an error (hook: **BLOCK**) | The enforcement works even when the model *does* try |
| 3. Read the row again | The row is still there (-5 seats), and the read passed (hook: **ALLOW**) | Data untouched, and normal work isn't broken |

Run 1 is worth showing on its own: it's the difference between a
**request** (worked because the model cooperated) and **enforcement** (works
regardless).

### How to explain steps 6 and 7 in 30 seconds
> "The agent holds live database credentials, so I added a guard that runs
> before every SQL call and blocks anything that isn't a pure read, including
> writes hidden in comments, CTEs or `EXPLAIN ANALYZE`. I planned it in plan
> mode first and committed the plan before the code. Then I proved it: in a
> fresh session the agent tried a `DELETE`, the hook stopped it before it
> reached Supabase, and the log has the timestamped BLOCK line. Interestingly,
> when I just *asked* it to delete, it refused because of `CLAUDE.md`. That
> shows the instruction works when the model cooperates, and the hook is for
> when it doesn't."

### Questions you might be asked
- **"Supabase is already read-only, so why a hook?"** Defense in depth.
  Read-only mode is one setting in a URL. The hook is independent code, and it
  stops the query *before* it leaves the machine, with a clear reason and a log.
- **"Can it be bypassed?"** A pattern-based guard can't parse every possible
  SQL trick, so it's built to fail closed: anything not provably a read is
  blocked. Known cost: `select … for update` is blocked even though it's
  harmless here.
- **"How do you know the hook blocked it and not Supabase?"** The error text
  is the hook's own message, Claude Code labels it `PreToolUse … hook error`,
  and the hook log has the BLOCK line with the exact query.
- **"Doesn't it slow things down?"** It's a ~50 ms Python script per SQL call.
  The eval and data-quality check run normally through it.

---

## Step 8: The robot, a headless data-quality check

**Goal (from the spec):** a `claude -p` script that runs unattended, checks
`usage_daily` for data-quality problems, returns **structured output**, and
**exits non-zero** when something is wrong. It needs every guardrail: a
restricted toolset, an explicit permission mode, a turn cap, a timeout and a
cheap model.

**Concept: headless.** `claude -p "…"` runs Claude with no chat window. It
gets a prompt, does the work, prints a result and exits. That's what lets a
scheduler run it at 6 am with nobody there. "Nobody there" also means nobody
can approve a prompt, stop a runaway loop or notice a hang. **The guardrails
replace the human.**

### 8a. Design: [`scripts/dq_check.py`](../scripts/dq_check.py)

A Python wrapper around **one** `claude -p` call:

| Guardrail | Setting | What it prevents |
|---|---|---|
| Cheap model | `claude-haiku-5-5` | A daily job costing real money (actual: ~$0.01 per run) |
| Restricted tools | `--tools ""` + only `execute_sql` allowed | The job can't read files, run shell commands or browse |
| Permission mode | `--permission-mode dontAsk` | Waiting forever for an approval nobody will give: anything not allowed is denied |
| Turn cap | `--max-turns 8` | An endless query-think-query loop |
| Budget cap | `--max-budget-usd 0.25` | A runaway bill |
| Timeout | 180 s, enforced by the wrapper | A hung session blocking the scheduler |
| Structured output | `--json-schema` (status, rows_checked, issues[]) | Prose that a script can't parse |
| SQL guard | the step 7 hook still applies | The check "helpfully" fixing the bad rows |

**Single source of truth:** the script reads the validity rules from
**§7 of `docs/semantic-layer.md`** at runtime and puts them into the prompt.
Change a rule in the doc, and the next scheduled run applies it.

**The exit code comes from the wrapper, not from the model:**
| Exit | Meaning |
|---|---|
| `0` | PASS: every row valid |
| `1` | FAIL: data-quality issues found |
| `2` | ERROR: the check itself can't be trusted (timeout, no/invalid JSON, a report that says FAIL with zero issues, `claude` not found) |

**Why a separate code for "the check broke"?** The most dangerous unattended
failure is a check that *silently* stops working and looks green. Separating
"data is bad" (1) from "I couldn't check" (2) means neither can pass for the
other, and neither is ever `0`.

**Every run leaves a trace:** one JSON line per run in `logs/dq_check.log`,
including errors. A failed 6 am run still has evidence of what went wrong.

### 8b. Results

**Normal run:** found **all 4 seeded problems**, nothing else, exit **1**:
| usage_id | Account | Rule broken |
|---|---|---|
| 13 | ACC-1002 | Seat count non-negative (-5) |
| 14 | ACC-1003 | Date present (NULL) |
| 15 | ACC-1004 | Seat count present (NULL) |
| 16 | ACC-9999 | Known account (not in `accounts`) |

11 seconds, 5 turns, $0.011.

**Failure-path test:** forced a 2-second timeout (`DQ_TIMEOUT_S=2`): `ERROR`,
exit **2**, logged. A broken check fails loudly.

**Bonus evidence:** the check's own SQL went through the step 7 hook (three
ALLOW lines in `logs/hook.log`). The guard protects unattended runs too.

### How to explain step 8 in 30 seconds
> "The data-quality check is a headless Claude session on the cheapest model,
> allowed exactly one tool, read-only SQL. It has a turn cap, a budget cap and
> a timeout, and it must answer in a fixed JSON shape. The rules come straight
> from the semantic layer, so docs and checks can't drift apart. The wrapper,
> not the model, decides the exit code: 0 clean, 1 bad data, 2 the check
> itself failed. It found exactly the four planted problems for about a cent."

### Questions you might be asked
- **"Why use an LLM for this at all? SQL could do it."** For five fixed
  rules, plain SQL would work. The value of the agent is that the rules are
  *read from the documentation*: add a rule in plain English to §7 and the
  check enforces it with no code change. The wrapper's strict validation keeps
  that flexibility from becoming unreliability.
- **"What if the model says PASS but there are problems?"** The schema forces
  it to list issues, and the wrapper rejects inconsistent reports. A model
  that missed a row entirely would still be a risk. A deterministic SQL
  cross-check is listed as a next step.
- **"Why exit 2 and not 1 on a timeout?"** So a monitoring system can tell
  "the data is bad" from "the robot is broken". They need different people.

---

## Step 9: On a schedule, proven unattended, then removed

**Goal (from the spec):** put the check on a schedule, let it run **on its
own at the scheduled time**, keep the timestamped log entry as proof, then
**unregister the job** and say so. Leaving it running isn't extra credit:
it keeps firing and costing money.

**Concept: Task Scheduler.** Windows' built-in equivalent of `cron`. A task
says *what* to run, *when*, and *as whom*.

### 9a. The launcher: [`scripts/run_dq_scheduled.cmd`](../scripts/run_dq_scheduled.cmd)

A scheduled task doesn't get your interactive shell's setup, so a script that
works in your terminal can fail at 6 am. The launcher sets everything
explicitly:
| Line | Why |
|---|---|
| `set DQ_INVOKED_BY=task-scheduler` | Each log entry says who started it. That's how we *prove* it was the scheduler, not us. |
| `cd /d "%~dp0.."` | The task's default working directory is `System32`, not the repo |
| full path to `python.exe` | The task's PATH may not include Python |
| `>> logs\dq_scheduler_stdout.log 2>&1` | If Python itself fails to start, there's still a trace |
| `exit /b %RC%` | Passes the check's exit code back to Task Scheduler |

### 9b. What happened

| When | Event |
|---|---|
| ~15:59 | Task `NorthwindDQ` registered: daily, first run 16:14, "interactive only" (runs as the user, while logged in) |
| **16:14:00** | **Task Scheduler started it with nobody at the keyboard** |
| 16:14:13 | Done: FAIL, 4 issues, exit 1, $0.003, 13.4 s |
| after | `schtasks` reported `Last Result: 1`, so the exit code reached the scheduler itself |
| after | **Task deleted** (`schtasks /Delete /TN NorthwindDQ /F`). A query confirms it no longer exists. Its next run would have been 19/11 16:14. |

**The proof** is in `logs/dq_check.log`:
```
{"timestamp": "2026-11-18T16:14:00+02:00", "check": "usage_daily", "model": "claude-haiku-5-5",
 "invoked_by": "task-scheduler", ..., "issue_count": 4, ..., "result": "FAIL", "exit_code": 1, "duration_s": 13.4}
```
The raw output of the same run is in `logs/dq_scheduler_stdout.log`.

**Why did the unattended run just work?** The failures that usually bite at
6 am were found and fixed *earlier*, while testing headless mode:
- **Folder trust** (step 3 prep): headless mode ignored allow rules in an
  untrusted folder.
- **Working directory and PATH:** handled explicitly by the launcher.

The unattended run *confirmed* those fixes. It's still the only run that
proves them.

**Limitation (honest):** "interactive only" means it runs only while the user
is logged in. A real production job would run as a service account, "whether
user is logged on or not", on a machine that doesn't sleep.

### How to explain step 9 in 30 seconds
> "I scheduled the check in Windows Task Scheduler through a launcher that
> sets its own working directory, Python path and a 'task-scheduler' label,
> because scheduled jobs don't inherit your shell. At 16:14 it ran by itself
> and found the four problems, and Task Scheduler recorded exit code 1, so a
> monitor would see the failure. Then I deleted the task: an unattended job
> that nobody needs anymore is just a recurring cost and a security surface."

### Questions you might be asked
- **"How do you know you didn't run it yourself?"** The entry says
  `invoked_by: task-scheduler`, which only the launcher sets. Its timestamp
  is exactly the scheduled minute (16:14:00), and Task Scheduler's own
  `Last Run Time` matches.
- **"Why remove it?"** Every run costs API calls and holds database access.
  Knowing to turn off what you started is part of shipping unattended
  software.
- **"What would production need?"** An always-on host or a cloud scheduler,
  a service account, alerting on exit codes 1 and 2 (e.g. email or Slack),
  and log rotation.

---

## Step 10: The Streamlit dashboard

**Goal (from the spec):** a small Streamlit app that reads the database and
shows the metrics, MRR, paying customers, trials and revenue over time, with
numbers that are **right**. "A dashboard that sums the wrong column is more
dangerous than no dashboard, because polish manufactures trust."

**Concept: one source of rules.** The agents follow `docs/semantic-layer.md`.
The dashboard must follow the *same* rules, or the two will disagree and
nobody will trust either. So every rule lives in one file and the screen code
has none.

### 10a. The files

| File | What it does |
|---|---|
| [`dashboard/metrics.py`](../dashboard/metrics.py) | **All** the SQL. Each rule is written once as a named fragment (`NOT_INTERNAL`, `MONTHLY_AMOUNT`, `LIVE_AT_MONTH_END`, `PAYING`, `PAID`), copied from semantic-layer sections 4 and 5, and the queries are built from those fragments. |
| [`dashboard/app.py`](../dashboard/app.py) | Draws only. It never filters, sums or normalizes. |
| [`.streamlit/secrets.toml.example`](../.streamlit/secrets.toml.example) | A template with no password, committed so others know the format |
| `.streamlit/secrets.toml` | The real login. Git-ignored, created by the human. **Claude is deny-listed from it.** |
| [`requirements.txt`](../requirements.txt) | streamlit, psycopg, pandas, pyyaml |

### 10b. What's on the screen

- **Month selector** (snapshot at month end). Data covers Jan to Mar 2026,
  and the app says so instead of pretending March is "now" (gotcha 13).
- **KPI tiles:** MRR, ARR, paying customers, accounts on trial and cash
  collected, with change vs the previous month. Each tile has a hover help
  that states its definition.
- **Two bar charts:** MRR at month end and cash collected in the month. They
  are deliberately *separate* charts, not one chart with two axes, and a
  caption explains why they differ (annual contracts are billed once but
  count at 1/12 a month).
- **"Who makes up MRR"** per account, with a total that must equal the tile.
- **Data quality:** the 4 bad `usage_daily` rows are *shown, not fixed*,
  using the same section 7 rules as the scheduled check.
- **"How these numbers are computed"**: the rules in plain words plus the SQL.

### 10c. Safety built in

- **Read-only session:** each query runs in a `READ ONLY` transaction
  (`conn.read_only = True`), so even though the login is the full-access
  `postgres` user, the server rejects any write coming from the dashboard.
  *Status:* built in, not yet tested live (the test needs the human's
  login, so the human runs it). A dedicated read-only database role would
  be the stronger fix (see limitations).
- **Currency guard:** if a non-USD row ever appears, the app refuses to show
  mixed totals (section 4.4) instead of silently adding dollars to euros.
- **No password in errors:** connection errors are shown with the password
  masked.

### 10d. What went wrong on the way (and the fix)

| Problem | Cause | Fix |
|---|---|---|
| Direct host unreachable | `db.<ref>.supabase.co` only has an IPv6 address; this network has no IPv6 route | Use the **Session pooler** host (IPv4) with user `postgres.<ref>` |
| `password authentication failed` | Wrong password in `secrets.toml` | The human corrected it in the file; Claude never saw it |
| Claude's diagnostic script was **refused** | It opened `secrets.toml` itself, which the permissions forbid | Correct refusal. Instead the app's own error message was improved, and diagnosis went through what the app *displays*, never the file. Evidence that the deny rule works for Python scripts too, not just the Read tool. |

### 10e. Verification: the dashboard agrees with the eval

The dashboard's SQL was first run read-only through the agent path, then the
app itself was run headless (Streamlit `AppTest`) against the live database:

| On screen | Dashboard | Reference |
|---|---|---|
| March MRR | $1,394.00 | eval q1, c1-c3 ✅ |
| Vertex Logistics, March | $800.00 (per-account table) | eval q2 ✅ |
| March paying customers | 4 | eval q3 ✅ |
| March accounts on trial | 2 | eval q5 ✅ |
| Cash collected Jan-Mar | $13,428.09 | eval q4 ✅ |
| February MRR | $1,539.00 | semantic-layer worked example ✅ |
| Per-account total | $1,394.00 | equals the MRR tile ✅ |
| Bad `usage_daily` rows | 4 (ids 13-16) | `scripts/dq_check.py` ✅ |

Three independent paths now give the same numbers: the agent with the
semantic layer, the agent-run SQL, and the dashboard.

**Screenshots** (taken by the human from the running app, March selected):
- [`dashboard.png`](images/dashboard.png): title, month selector, KPI tiles
- [`dashboard2.png`](images/dashboard2.png): cash, the MRR and cash charts (with a hover tooltip)
- [`dashboard3.png`](images/dashboard3.png): MRR by account, the data-quality table

**How to run it:**
```
pip install -r requirements.txt
streamlit run dashboard/app.py      # then open http://localhost:8501
```

### How to explain step 10 in 30 seconds
> "The dashboard reads the database through Supabase's pooler and shows MRR,
> customers, trials and cash by month. All of its SQL is in one file built
> from the semantic layer's rules, so it can't drift from what the agents
> use, and I checked that every figure matches the eval answers. It runs
> read-only, refuses to mix currencies, and shows the bad usage rows instead
> of hiding or fixing them."

### Questions you might be asked
- **"Why not let the agent compute the numbers live?"** A dashboard must be
  fast, cheap and identical on every refresh. Plain SQL is deterministic; an
  agent call isn't. The agent is for *new* questions, the dashboard for the
  standing ones.
- **"How do you know the numbers are right?"** They match the graded eval
  answers and the worked example, and the per-account rows add up to the
  tile.
- **"Why is the database password not in the repo?"** It's in a git-ignored
  `secrets.toml`; only a template is committed. In production it would be a
  dedicated read-only database role, not `postgres`.
- **"Why are there two charts instead of one?"** MRR and cash measure
  different things on different timing. Putting them on two y-axes in one
  chart invites false comparisons.

---

## Step 11: README and publishing

**Goal (from the spec):** a README that "does the work when you are not in
the room": what it is (in business terms), a screenshot near the top, the
architecture, how to run it, why each component exists, and honest
limitations. Then a public GitHub repo.

### 11a. The README: [`README.md`](../README.md)

| Section | Choice and why |
|---|---|
| Opening paragraph | The business problem (undocumented numbers, analysts disagreeing), not "a course project" |
| Screenshots | All three side by side, right under the intro. That's the fastest proof it works. The caption states the March numbers and that they match the eval. |
| Architecture | A **Mermaid** diagram, which GitHub draws from text, so it stays editable and diffable. It shows the two paths to the database (agent via MCP behind three locks; dashboard via the pooler, read-only) and that both use the same rules. |
| Component table | For each of the 7 components: where, what, and **what goes wrong without it**. That last column is the "why it exists" the spec asks for. |
| Results | Eval, hook, schedule and dashboard, each with a link to its evidence file |
| How to run | Clone, connect (including the folder-trust and `/mcp` traps we hit), ask, eval, check, dashboard, tests |
| Limitations | Seven honest ones, each with what I'd build next |

### 11b. Pre-publish scan

Before anything goes public, the **whole git history** (not just the latest
commit) was scanned, because deleting a secret in a later commit doesn't
remove it from history.

| Check | Result |
|---|---|
| Passwords, API keys, JWTs, `sb_secret_`, `service_role`, connection strings with passwords, GitHub tokens, private keys | none in any of the 15 commits |
| `.env`, `secrets.toml`, `*.pem`, `*.key`, `settings.local.json` ever committed | never |
| Personal email inside files | none |
| Commit author email | the git author email is on every commit, which is public on GitHub. That's the human's decision (see 11c). |

### 11c. Publishing *(in progress)*

Needs the GitHub CLI (`winget install GitHub.cli`, then `gh auth login`,
done by the human because it's their account). `git push` is in the `ask`
list in `.claude/settings.json`, so Claude has to get explicit approval
before pushing anything.

### How to explain step 11 in 30 seconds
> "The README is written for someone who'll never talk to me: what the
> business problem is, a screenshot of the working dashboard, a diagram of
> how agent, guards, check and dashboard connect, how to run each part, and
> for every component what would break without it. Before publishing, I
> scanned the entire git history for secrets, because a password deleted in
> a later commit is still public in the earlier one."

### Questions you might be asked
- **"Why scan history, not just the files?"** Git keeps every version.
  Anyone can check out an old commit, so a removed secret is still leaked.
- **"Why is the answer key in a public repo?"** It ships with the
  assignment and the grader needs it. What matters is that the *agent* can't
  read it during the eval, which the deny rules enforce.
- **"Why Mermaid instead of an image?"** It's text: reviewable in a diff,
  editable without a design tool, and GitHub renders it.

---

<!-- Next entry: Step 11c - publish result -->
