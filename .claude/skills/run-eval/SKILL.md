---
name: run-eval
description: Run the Northwind semantic-layer evaluation end to end. Asks the 8 questions in eval/questions.yaml against Supabase (each in a fresh headless session), saves the numbers, grades them with run_eval.py, and compares against the baseline. Use when asked to "run the eval", "re-run the eval", "grade the semantic layer", or after any change to docs/semantic-layer.md or CLAUDE.md.
argument-hint: "[label]  (default: after)"
---

# Run the eval

Measures whether the agent answers Northwind's business questions correctly
and consistently **given the current semantic layer**. Run it after every
change to `docs/semantic-layer.md` or `CLAUDE.md`. That's how you find out
whether the change helped.

## Rules (non-negotiable)

- **Never open `eval/golden.yaml`.** The grader reads it, and you don't.
- **Never answer the questions yourself in this session.** Every question must
  be asked in its own fresh headless session, which `ask_questions.py` does.
  Answers from this session would see each other and the conversation, and the
  consistency test (c1-c3) would measure nothing.
- **Never edit a results file by hand**, even when a number is obviously
  wrong. A wrong number is the finding.

## Steps

The label is `$ARGUMENTS`, or `after` if none was given.

1. **Ask the questions.** From the repo root:
   ```
   python eval/ask_questions.py --label <label> --out eval/results.yaml
   ```
   Takes a few minutes (8 sessions, 4 in parallel, about $1). It prints one
   line per question and writes:
   - `eval/results.yaml`: numbers only, the file the grader reads
   - `eval/runs/<label>/<id>.json`: each session's full answer (evidence)

   If it exits non-zero, a question produced no `ANSWER:` line. Open that
   question's JSON, report what happened, and **do not** fill the gap by hand.

2. **Grade it**, from inside `eval/` (the grader uses relative paths):
   ```
   cd eval
   python run_eval.py results.yaml > scorecard.txt
   python run_eval.py results-before.yaml results.yaml > scorecard-compare.txt
   ```
   Show the user both scorecards.

3. **Read the answers, not just the score.** For each question, open
   `eval/runs/<label>/<id>.json` and check `answer_text`:
   - Did it cite the semantic layer's definition?
   - Did it still hedge ("if you exclude X it would be Y")? Hedging means the
     layer left a decision open.
   - For any FAIL: which rule in `docs/semantic-layer.md` was missing, unclear,
     or ignored?

4. **Report** in this shape:
   - Accuracy before → after, consistency before → after
   - Each failure and the missing rule behind it
   - Remaining hedges and the decision each one shows is still open
   - Suggested edits to `docs/semantic-layer.md`. Suggest them; don't apply them
     unless asked, then re-run this skill.
