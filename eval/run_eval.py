"""
run_eval.py - grade a saved semantic-layer run against the golden answer key.

This is the small, deterministic "harness" half of an evaluation. It does NOT
call a model and does NOT touch the database. It reads two files:

  1. golden.yaml   - the gold answers (the answer key). Grader-side only; the
                     system under test is pointed at questions.yaml instead,
                     which carries the same questions with no answers.
  2. results.yaml  - the numbers YOUR run produced (you fill this in from the
                     answers Claude gave against Supabase).

...then compares them number-by-number with a tolerance and prints a scorecard.

Why this shape:
  - The grader never saw how the answers were produced - it only sees the saved
    numbers. That separation between "the run" and "the grade" is what makes an
    eval honest.
  - The same separation runs the other way: the answer key never reaches the
    system being measured. Questions go out in questions.yaml; gold stays here.

Run it:            python run_eval.py
Grade a named run: python run_eval.py results-before.yaml
Compare two runs:  python run_eval.py results-before.yaml results-after.yaml
Needs:             pip install pyyaml
"""

import sys
import yaml

GOLDEN_FILE = "golden.yaml"
DEFAULT_RESULTS = "results.yaml"


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        sys.exit(
            f"Missing {path}. Produce a run first and save its numbers there - "
            f"see the project spec for the shape of the file."
        )


def as_list(value):
    """results.yaml may hold a single number or a list of them. Normalize."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return [value]
    return list(value)


def numbers_match(gold_numbers, got_numbers, tolerance):
    """The two number sets must match EXACTLY - same count, and every gold
    number paired with a got number within tolerance. Order does not matter,
    so currency rows in any order still pass.

    The count check is the important half. Matching gold-into-got only would
    mean a run that answered with the right numbers PLUS extra ones scored a
    PASS: "MRR is 1224.00 USD, or 34681.00 across all subscriptions" contains
    the gold and would pass, even though half of it is the very trap q1 exists
    to catch. An eval that forgives extra numbers is an eval that quietly stops
    collapsing when you break a rule."""
    if got_numbers is None or len(gold_numbers) != len(got_numbers):
        return False
    remaining = list(got_numbers)
    for g in gold_numbers:
        hit = next((x for x in remaining if abs(x - g) <= tolerance), None)
        if hit is None:
            return False
        remaining.remove(hit)
    return True


def grade_accuracy(golden, results):
    rows, passed = [], 0
    for item in golden["accuracy"]:
        qid = item["id"]
        got = as_list(results.get(qid))
        if got is None:
            rows.append((qid, "NO RESULT", "-", item["gold"]))
            continue
        ok = numbers_match(item["gold_numbers"], got, item.get("tolerance", 0))
        passed += ok
        rows.append((qid, "PASS" if ok else "FAIL", got, item["gold"]))
    return rows, passed


def grade_consistency(golden, results):
    """All consistency phrasings must return the same number set."""
    block = golden["consistency"]
    items = block["questions"]
    tolerance = block.get("tolerance", 0)

    sets = []
    for item in items:
        got = as_list(results.get(item["id"]))
        sets.append(tuple(sorted(got)) if got else None)

    if any(s is None for s in sets):
        return "INCOMPLETE", items, sets

    first = sets[0]
    agree = all(
        len(s) == len(first)
        and all(abs(a - b) <= tolerance for a, b in zip(s, first))
        for s in sets
    )
    return ("PASS" if agree else "FAIL"), items, sets


def score(golden, results_file, quiet=False):
    """Grade one run. Returns (accuracy_passed, accuracy_total, consistency)."""
    results = load(results_file)

    rows, passed = grade_accuracy(golden, results)
    total = len(golden["accuracy"])
    verdict, items, sets = grade_consistency(golden, results)

    if not quiet:
        print(f"\n=== {results_file} ===")
        print("\n  Accuracy (q1-q5)")
        for qid, v, got, gold in rows:
            print(f"    {qid}: {v:9}  got={got}  gold={gold}")
        print(f"\n    Accuracy: {passed}/{total} = {100 * passed / total:.0f}%")

        print("\n  Consistency (c1-c3)")
        print(f"    Verdict: {verdict}")
        for item, s in zip(items, sets):
            print(f"      {item['id']}: {s}")
        if verdict == "FAIL":
            print(
                "    The phrasings diverged - your Metrics/Terms/Gotchas aren't "
                "pinning the metric down. Fix the document, not the chat."
            )

    return passed, total, verdict


def main():
    golden = load(GOLDEN_FILE)
    args = sys.argv[1:]

    if len(args) <= 1:
        score(golden, args[0] if args else DEFAULT_RESULTS)
        print()
        return

    # Two runs: grade both, then show what changed.
    before_file, after_file = args[0], args[1]
    b_passed, total, b_cons = score(golden, before_file)
    a_passed, _, a_cons = score(golden, after_file)

    print("\n=== Before -> After ===")
    print(f"  Accuracy:    {b_passed}/{total} -> {a_passed}/{total}"
          f"   ({100 * b_passed / total:.0f}% -> {100 * a_passed / total:.0f}%)")
    print(f"  Consistency: {b_cons} -> {a_cons}")

    delta = a_passed - b_passed
    if delta > 0:
        print(f"\n  +{delta} question(s) fixed. Say which change did it, and why.")
    elif delta < 0:
        print(f"\n  {delta} question(s) regressed. Something you changed made it worse.")
    else:
        print("\n  No change in accuracy. If you expected one, the fix did not land.")
    print()


if __name__ == "__main__":
    main()
