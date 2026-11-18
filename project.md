# Final Project: Build an Agentic Data Platform

Every exercise in this course handed you steps. This one hands you a database and a standard.

You are the first data hire at Northwind Cloud, a B2B SaaS company. There is a production database, nobody has documented what its numbers mean, and analysts keep asking the same questions by hand. Your job is not to answer those questions once. It is to **build the platform that answers them** - documented, enforced, and running on a schedule without you.

That is the whole course in one repo: a semantic layer so the agent knows what the business means, skills so procedures are repeatable, hooks so rules are enforced rather than requested, a headless script on a timer so the thing runs itself, and a dashboard so anyone can see the numbers.

---

## What you are given

| File | What it is |
|---|---|
| `schema.sql` | The Northwind Cloud database. Run it in Supabase and the whole thing exists. Readable table names - this is not a decoding puzzle. |
| `eval/questions.yaml` | Eight questions. The only one of these files you point Claude at. |
| `eval/golden.yaml` | The answer key. Read it when you grade, not before. |
| `eval/run_eval.py` | The grader. Compares a saved run to the answer key and prints a scorecard. |
| `eval/results-template.yaml` | The shape your saved run must take. |

---

## Using your own data instead

If you would rather build this against a database from your actual job, do it - the standard is the same and the result is more useful to you. Two adjustments:

- **You write the answer key.** Choose five questions with known-correct answers plus three phrasings of one question, and save them in the same shape as `golden.yaml`.
- **Your data-quality check checks your data.** Pick the three or four problems that actually matter in your tables.

Do not put anything confidential in a public repo. If the data is sensitive, obfuscate names and round numbers before committing anything - and if that is not possible, use Northwind Cloud instead.

---

## The seven components

How you build each one is yours to figure out. The order below is roughly the order that works, but you own the sequencing.

### 1. The repo and the connection

A Supabase project with `schema.sql` loaded, connected to Claude through MCP, and a GitHub repo with `.gitignore` written **before** the first commit. Permissions in `.claude/settings.json` chosen deliberately - this agent can reach a live database, so decide what it may and may not do, and write down why.

### 2. The semantic layer

`docs/semantic-layer.md`: the tables and their grain, the join keys, the metric definitions, the status vocabulary, the gotchas, the glossary. `CLAUDE.md` points at it rather than restating it.

The test of this document is not length. It is whether someone who has never seen the database can compute MRR correctly from it alone.

### 3. The evaluation

Ask the eight questions in `eval/questions.yaml` against the database, save the numbers in `results.yaml`, run the grader, and commit the scorecard.

Then do the part the grader cannot: for anything that failed, say what rule was missing from your layer. A diagnosed failure is worth more than a lucky pass - if you score 5/5 on the first run, say what you think the eval is *not* testing.

### 4. The skill

At least one working skill in `.claude/skills/`, for a procedure you actually repeat. Candidates that earn their keep here:

- **Run the eval** - asks the eight questions, fills in `results.yaml`, runs the grader
- **Sanity-check a number** - independently recomputes a figure and says whether to trust it
- **Refresh the dashboard data** - or whatever step you found yourself repeating by hand

### 5. The guards (hook)

At least one hook that **enforces** something instead of asking for it. The obvious one, given that this agent holds live database credentials, is a `PreToolUse` guard that blocks destructive SQL before it reaches Supabase.

Then prove it works: try the forbidden thing in a fresh session and capture what happened. An unproven guard is decoration.

### 6. The robot (headless + scheduling)

A `claude -p` script that runs unattended, checks the `usage_daily` table for data-quality problems, returns structured output, and exits non-zero when something is wrong. Every guardrail from the Headless lesson applies: a restricted toolset, an explicit permission mode, a turn cap, a timeout, a cheap model.

Then put it on a schedule and let it prove itself - a log file with a real timestamped entry in it.

> **This registers a real recurring job on your machine.** It keeps firing - and keeps costing API calls - until you remove it. Once you have the log entry that proves it ran, unregister it and say so in the README. Leaving it running is not extra credit; knowing to turn it off is part of shipping something unattended.

Let it run on its own at least once, at the scheduled time, before you call this done. A supervised run and a 6am run are not the same test - the failures that matter here only appear when nobody is watching, and a check that has only ever been run by hand has not been tested.

There are four deliberate problems seeded in `usage_daily`. A working check finds them and fails.

### 7. The dashboard

A small Streamlit app that reads the database and puts your metrics on a screen: MRR, paying customers, trials, revenue over time - whatever tells the story of this business.

The point is not the charts. It is that the numbers on screen have to be **right**, which means the app applies the same rules your semantic layer wrote down: annual contracts normalized, trials excluded, internal accounts filtered out. A dashboard that sums the wrong column is more dangerous than no dashboard, because polish manufactures trust.

Screenshot it. This is the image that goes in the README, and the one you post when you want to show what you built.

---

## What you hand in

A public GitHub repo. The name is yours.

**The platform**

- [ ] Supabase connected through MCP, `.claude/settings.json` with deliberate permissions
- [ ] `CLAUDE.md` that routes to the semantic layer
- [ ] `docs/semantic-layer.md` - definitions, grain, joins, vocabulary, gotchas
- [ ] At least one working skill in `.claude/skills/`
- [ ] At least one hook that enforces a rule, **with evidence it fired**
- [ ] A headless script with guardrails that returns structured output and a meaningful exit code
- [ ] That script on a schedule, with a log file proving it ran unattended - then the schedule removed
- [ ] A Streamlit dashboard reading the database, with correct numbers, plus a screenshot in the README

**The evidence**

- [ ] `results.yaml` and the saved scorecard
- [ ] A short write-up of what failed and what rule was missing (or, at 5/5, what the eval does not cover)
- [ ] One plan produced in plan mode before a substantial step

**The repo itself**

- [ ] Commits that tell the story in order, not one `final` commit
- [ ] No secrets committed, ever
- [ ] A `README.md` that makes someone want to keep reading

---

## The README

This is the part that does the work when you are not in the room. It should cover, briefly:

- **What this is** - one paragraph, in business terms, not "a final project for a course"
- **A screenshot of the dashboard**, near the top. It is the fastest way to show that the thing works
- **The architecture** - what the components are and how they fit. A diagram earns its place here
- **How to run it** - clone, connect, run the check, start the dashboard
- **What each component does and why it exists** - especially the hook and the scheduled check: what would go wrong without them
- **What you would build next** - the honest limitations. This reads as competence, not weakness

Write it for a technical person who has five minutes and has never heard of this course.
