"""
dq_check.py - unattended data-quality check for Northwind's usage_daily table.

Runs ONE headless Claude session that queries Supabase (read-only), applies the
validity rules from docs/semantic-layer.md section 7, and returns structured
JSON. This wrapper validates that JSON, logs the run, and sets the exit code.

    python scripts/dq_check.py            # from anywhere; paths are absolute

Exit codes (decided by this wrapper, never by the model's wording):
    0  PASS  - every row valid
    1  FAIL  - data-quality issues found (details on stdout and in the log)
    2  ERROR - the check itself could not be trusted (timeout, no/invalid
               output, inconsistent answer, claude missing). A broken check must
               never look like a passing one.

Guardrails on the headless session (see the Headless lesson):
    model         claude-haiku-5-5   cheap; this runs every day
    tools         none built-in; only mcp__supabase__execute_sql allowed
    permissions   --permission-mode dontAsk (anything not allowed is denied,
                  nothing waits for a human); the SQL guard hook still applies
    turn cap      --max-turns 8
    budget cap    --max-budget-usd 0.25
    timeout       180 s wall clock, enforced here
    output        --json-schema (validated by Claude Code) + re-checked here

Every run appends one JSON line to logs/dq_check.log - including failures, so
an unattended run that broke still leaves evidence.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LAYER = REPO / "docs" / "semantic-layer.md"
LOG = REPO / "logs" / "dq_check.log"

MODEL = "claude-haiku-5-5"
MAX_TURNS = 8
BUDGET_USD = 0.25
TIMEOUT_S = int(os.environ.get("DQ_TIMEOUT_S", "180"))  # override only to test the failure path

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["PASS", "FAIL"]},
        "rows_checked": {"type": "integer"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule": {"type": "string"},
                    "usage_id": {"type": ["integer", "null"]},
                    "account_code": {"type": ["string", "null"]},
                    "detail": {"type": "string"},
                },
                "required": ["rule", "usage_id", "account_code", "detail"],
            },
        },
    },
    "required": ["status", "rows_checked", "issues"],
}


def rules_from_semantic_layer():
    """Section 7 of the semantic layer is the single source of truth."""
    text = LAYER.read_text(encoding="utf-8")
    m = re.search(r"## 7\..*?(?=\n## \d|\Z)", text, flags=re.S)
    if not m:
        raise RuntimeError("section 7 not found in docs/semantic-layer.md")
    return m.group(0)


def build_prompt(rules):
    return f"""You are an unattended data-quality check for the Northwind Cloud database.
Use only the execute_sql tool, read-only (SELECT only). Do not modify any data.

Check EVERY row of the table `usage_daily` against these validity rules,
taken from the project's semantic layer:

{rules}

Notes:
- `accounts.account_code` is the list of known accounts.
- Report one issue per (row, broken rule). Use usage_id to identify the row; for
  the duplicate rule, report each duplicated row.
- rows_checked = total number of rows in usage_daily.
- status = "FAIL" if there is at least one issue, otherwise "PASS".
- Do not fix anything. Only report.
"""


def find_claude():
    found = shutil.which("claude")
    if found:
        return found
    # Task Scheduler may run with a thinner PATH than an interactive shell.
    fallback = Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "claude.exe"
    return str(fallback) if fallback.exists() else None


def write_log(entry):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run():
    started = time.monotonic()
    entry = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "check": "usage_daily",
        "model": MODEL,
        "invoked_by": os.environ.get("DQ_INVOKED_BY", "manual"),
    }

    def finish(code, **fields):
        entry.update(fields)
        entry["exit_code"] = code
        entry["duration_s"] = round(time.monotonic() - started, 1)
        write_log(entry)
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return code

    claude = find_claude()
    if not claude:
        return finish(2, result="ERROR", error="claude executable not found")

    try:
        prompt = build_prompt(rules_from_semantic_layer())
    except (OSError, RuntimeError) as e:
        return finish(2, result="ERROR", error=f"could not load rules: {e}")

    cmd = [
        claude, "-p", prompt,
        "--model", MODEL,
        "--tools", "",
        "--allowedTools", "mcp__supabase__execute_sql",
        "--permission-mode", "dontAsk",
        "--max-turns", str(MAX_TURNS),
        "--max-budget-usd", str(BUDGET_USD),
        "--no-session-persistence",
        "--output-format", "json",
        "--json-schema", json.dumps(SCHEMA),
    ]
    try:
        proc = subprocess.run(cmd, cwd=REPO, capture_output=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return finish(2, result="ERROR", error=f"timed out after {TIMEOUT_S}s")

    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace").strip()
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return finish(2, result="ERROR", error="claude returned no JSON",
                      claude_exit=proc.returncode, stderr=stderr[:500],
                      stdout=stdout[:500])

    entry["cost_usd"] = data.get("total_cost_usd")
    entry["num_turns"] = data.get("num_turns")
    if data.get("is_error") or data.get("subtype") != "success":
        return finish(2, result="ERROR",
                      error=f"session ended with {data.get('subtype')}",
                      detail=str(data.get("result"))[:500])

    report = data.get("structured_output")
    if report is None:  # fall back to the text result
        try:
            report = json.loads(data.get("result") or "")
        except json.JSONDecodeError:
            return finish(2, result="ERROR", error="no structured output",
                          detail=str(data.get("result"))[:500])

    # Re-check the report ourselves; don't trust the model's own verdict.
    issues = report.get("issues")
    status = report.get("status")
    if not isinstance(issues, list) or status not in ("PASS", "FAIL"):
        return finish(2, result="ERROR", error="report missing status/issues", report=report)
    if (status == "FAIL") != (len(issues) > 0):
        return finish(2, result="ERROR",
                      error=f"inconsistent report: status {status} with {len(issues)} issues",
                      report=report)

    entry["rows_checked"] = report.get("rows_checked")
    entry["issue_count"] = len(issues)
    entry["issues"] = issues
    return finish(1 if issues else 0, result=status)


if __name__ == "__main__":
    sys.exit(run())
