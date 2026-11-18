"""
ask_questions.py - the "run" half of the eval: ask every question in
questions.yaml against Supabase, each in its own FRESH headless Claude session,
and save the numbers in the results.yaml shape for run_eval.py to grade.

Usage (from the repo root):
    python eval/ask_questions.py --label before
    python eval/ask_questions.py --label after --out eval/results.yaml

Writes:
    eval/runs/<label>/<id>.json   raw transcript summary per question (evidence)
    eval/results-<label>.yaml     the numbers only (or --out path)

Isolation rules (why the flags look the way they do):
  - One `claude -p` per question with --no-session-persistence: no question can
    see another's answer, so c1-c3 are independent measurements.
  - The same toolset for every run (Supabase read tools + Read), so a before
    and after run differ only in what the docs say, not in what the agent can do.
  - Files that would leak rules or answers are denied: the spec (spells out the
    MRR rules), everything under eval/ (previous runs and the answer key), the
    build journal and the README (they discuss findings). The repo's
    .claude/settings.json deny rules apply on top of these.
"""

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
QUESTIONS = REPO / "eval" / "questions.yaml"

MODEL = "claude-sonnet-5-5"
MAX_TURNS = 15
TIMEOUT_S = 300
WORKERS = 4

# Asked after every question so the number can be extracted mechanically.
# It says nothing about HOW to compute the answer.
FORMAT_SUFFIX = (
    "\n\nEnd your reply with exactly one final line in the form\n"
    "ANSWER: <number>\n"
    "using a bare number only (no currency symbols, units or thousands separators)."
)

ALLOWED = [
    "mcp__supabase__list_tables",
    "mcp__supabase__execute_sql",
    "Read",
]
DENIED = [
    "Read(./project.md)",
    "Read(./README.md)",
    "Read(./eval/**)",
    "Read(./docs/build-journal.md)",
    "Read(./docs/plans/**)",
    "Read(./logs/**)",
    "Read(./dashboard/**)",
    "Read(./scripts/**)",
]

ANSWER_RE = re.compile(r"ANSWER:\s*(.+)", re.IGNORECASE)
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def ask(qid, question):
    cmd = [
        "claude", "-p", question + FORMAT_SUFFIX,
        "--model", MODEL,
        "--tools", "Read",
        "--allowedTools", *ALLOWED,
        "--disallowedTools", *DENIED,
        "--permission-mode", "dontAsk",
        "--max-turns", str(MAX_TURNS),
        "--no-session-persistence",
        "--output-format", "json",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=REPO, capture_output=True, text=True,
            encoding="utf-8", timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return qid, {"error": f"timeout after {TIMEOUT_S}s"}, None

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return qid, {"error": "no JSON output", "stdout": proc.stdout,
                     "stderr": proc.stderr}, None

    text = data.get("result", "") or ""
    numbers = None
    lines = ANSWER_RE.findall(text)
    if lines:
        cleaned = lines[-1].replace(",", "").replace("$", "")
        found = [float(n) for n in NUMBER_RE.findall(cleaned)]
        if found:
            numbers = found[0] if len(found) == 1 else found

    record = {
        "id": qid,
        "question": question,
        "model": MODEL,
        "answer_text": text,
        "extracted": numbers,
        "num_turns": data.get("num_turns"),
        "cost_usd": data.get("total_cost_usd"),
        "is_error": data.get("is_error"),
        "permission_denials": data.get("permission_denials"),
        "stderr": proc.stderr.strip() or None,
    }
    return qid, record, numbers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="run name, e.g. before / after")
    ap.add_argument("--out", help="results path (default eval/results-<label>.yaml)")
    args = ap.parse_args()

    qs = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))
    items = [(q["id"], q["question"]) for q in qs["accuracy"] + qs["consistency"]]

    run_dir = REPO / "eval" / "runs" / args.label
    run_dir.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        outcomes = list(pool.map(lambda it: ask(*it), items))

    results, total_cost = {}, 0.0
    for qid, record, numbers in outcomes:
        (run_dir / f"{qid}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        results[qid] = numbers
        total_cost += record.get("cost_usd") or 0
        print(f"{qid}: {numbers}   ({record.get('error') or 'ok'})")

    out = REPO / args.out if args.out else REPO / "eval" / f"results-{args.label}.yaml"
    header = (
        f"# run: {args.label} | model: {MODEL} | "
        f"{datetime.now().isoformat(timespec='seconds')} | "
        f"one fresh session per question (eval/ask_questions.py)\n"
    )
    body = "".join(f"{qid}: {'' if v is None else v}\n" for qid, v in results.items())
    out.write_text(header + body, encoding="utf-8")

    print(f"\nsaved {out.relative_to(REPO)}  |  raw answers in "
          f"{run_dir.relative_to(REPO)}  |  cost ${total_cost:.3f}")
    if any(v is None for v in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
