# Eval findings

## Result

| Run | Semantic layer | Accuracy | Consistency | Cost | Avg turns |
|---|---|---|---|---|---|
| `results-before.yaml` | none | 5/5 | PASS | $1.05 | 3.9 |
| `results.yaml` (after) | `docs/semantic-layer.md` + `CLAUDE.md` | 5/5 | PASS | $0.63 | 3.25 |

Model: `claude-sonnet-5-5`. One fresh headless session per question
(`eval/ask_questions.py`), with the spec, eval files and answer key denied.
Raw answers: `eval/runs/before/`, `eval/runs/after/`. Scorecards:
`scorecard-before.txt`, `scorecard.txt`, `scorecard-compare.txt`.

## No failure to diagnose, so here's what the score hides

Both runs scored 5/5, but the runs weren't equivalent. **Without** the layer,
the agent got there by guessing the conventional SaaS rules, and it said so,
offering a competing number three times:

| Question | Baseline guessed | Alternative it offered | Rule that now settles it |
|---|---|---|---|
| q1 MRR | `past_due` counts | a lower MRR without it | §3: `past_due` is a live contract, collections ≠ churn |
| q3 Paying customers | live contract = paying | a lower count if "paying" = paid a March invoice | §5: distinct accounts with a live non-trial term at month end |
| q4 Cash | includes tax | the net-of-tax total | §5: cash = tax-inclusive `total_amount` of `paid` invoices |

**With** the layer, every answer cited `docs/semantic-layer.md`, named the
definition it applied, and gave one number. That's the actual improvement:
**right for a stated reason** instead of **right by convention**. It also ran
in fewer turns and cost 40% less, because the agent stopped exploring the
schema to rediscover rules.

## What this eval does not test

1. **History.** Every question is about March or Q1, and in March the
   `status` column happens to agree with the dates. A question about
   **February** would expose the classic trap: filtering on
   `status in ('active','past_due')` drops Harbor Freight (churned *now*, live
   all February) and understates MRR. The eval can't tell a date-driven
   definition from a status-driven one.
2. **Mid-month changes.** Cobalt upgraded on Feb 15. "Cobalt's MRR in
   February" separates a month-end snapshot (one term) from "every term that
   overlapped the month" (both terms, double-counted). No eval question
   touches this.
3. **Model variation.** Only one strong model was measured. A cheaper model
   (e.g. the Haiku the scheduled job uses) leans harder on written rules. Not
   measured, by choice, to keep cost down.
4. **Repeatability.** Each question ran once per configuration. Three agreeing
   phrasings are a small sample, and a model can be consistent and still drift
   across days.
5. **Multi-currency.** All Northwind data is USD, so the "never sum across
   currencies" rule is never exercised.
6. **Data quality.** No question reads `usage_daily`, where the dirty rows live.
   An analyst asking "average active seats in March" would silently include
   a negative count. That's covered by the scheduled check, not by this eval.
7. **Ambiguity that should be refused.** No question is unanswerable from the
   data (e.g. "MRR in November 2026", after the data ends). The layer says to
   say so (gotcha 13), and nothing tests it.

## Questions I'd add next

| Question | Why it discriminates |
|---|---|
| "What was our MRR in January 2026?" | Clean month, a control |
| "How many paying customers did we have at the end of February 2026?" | Status-vs-dates trap (churned customer was still paying) |
| "What was Cobalt Studio's MRR in February 2026?" | Snapshot vs overlap (upgrade double-count) |
| "What is our MRR right now?" | Should flag that data ends March 2026 |
| "What was revenue excluding tax in Q1 2026?" | Checks the agent switches to the *other* defined metric |

Note: the layer's worked example uses February, so February questions would
need their own answer key and the worked example moved to a month not under
test.
