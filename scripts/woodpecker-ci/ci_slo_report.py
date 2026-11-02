#!/usr/bin/env python3
"""MO-118: cross-repo CI SLO report from the Woodpecker SQLite DB.

Per repo + workflow over the last 24h: queue wait / run / total at p50 and p95,
plus each failure classified code / infra / flaky from step logs.

Runs on the M1 (live volume) or any host that can SSH to it.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import shlex
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

INFRA_RE = re.compile(
    r"(?ms)(docker\.sock|Cannot connect to the Docker|maximum elapsed time exceeded|"
    r"graceful_stop|connection refused|i/o timeout|TLS handshake|"
    r"pull access denied|No such image|no space left|OOMKilled|"
    r"network is unreachable|temporary failure in name resolution|"
    r"dial tcp|context deadline exceeded|reaped by MO-117|"
    r"backoff: maximum elapsed|rpc error|Unavailable desc|"
    r"error during connect|closing transport|agent.*(offline|gone)|"
    r"killed by timeout|pipeline timeout|signal: killed|"
    r"^Canceled$|\bCanceled\b|\bcanceled by\b|cancel previous|superseded|"
    r"clone:git:|fatal: could not read|Authentication failed|"
    r"early EOF|RPC failed|The requested URL returned error)",
    re.IGNORECASE,
)
FLAKY_RE = re.compile(
    r"(\bflaky\b|ECONNRESET|socket hang up|ETIMEDOUT|"
    r"429 Too Many|rate limit|TimeoutWaitingFor|"
    r"intermittent|timed out after \d+ms.*retry)",
    re.IGNORECASE,
)
CODE_RE = re.compile(
    r"(AssertionError|ERR_ASSERTION|assert\.|EXPECT\(|XCTAssert|"
    r"npm ERR!|error TS\d+|FAILED \(failures=|Test Suites:.*failed|"
    r"FAIL\s+\S+|pytest\.|Error: fast check failed|"
    r"swift(test|build).*error:|Compilation error|lint failed)",
    re.IGNORECASE,
)


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def fmt_secs(v):
    if v is None:
        return "-"
    if v < 60:
        return f"{v:.0f}s"
    m, s = divmod(round(v), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def now_pt():
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo("America/Los_Angeles"))
    return datetime.now(timezone.utc)


def run_sql_json(sql: str, *, host: str | None, stack: str) -> list:
    """Run read-only SQL; return parsed JSON rows (sqlite3 -json)."""
    b64 = base64.b64encode(sql.encode()).decode()
    root_q = shlex.quote(stack)
    b64_q = shlex.quote(b64)
    remote = f"""
set -eu
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
export PATH
ROOT={root_q}
# shellcheck disable=SC1091
. "$ROOT/scripts/common.sh"
sql=$(printf '%s' {b64_q} | base64 -D 2>/dev/null || printf '%s' {b64_q} | base64 -d)
# Feed SQL on stdin so pipes/newlines in the query never hit the shell parser.
printf '%s\\n' "$sql" | docker run --rm -i -v woodpecker-ci-server-data:/d:ro alpine:3.22 \\
  sh -c 'apk add -q sqlite >/dev/null && sqlite3 -readonly -json file:/d/woodpecker.sqlite?mode=ro'
"""
    if host:
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", host, "bash", "-s"],
            input=remote,
            text=True,
            capture_output=True,
            check=False,
        )
    else:
        proc = subprocess.run(
            ["bash", "-s"],
            input=remote,
            text=True,
            capture_output=True,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"SQL failed (rc={proc.returncode}): {proc.stderr.strip() or proc.stdout}"
        )
    out = (proc.stdout or "").strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"SQL JSON parse failed: {exc}: {out[:200]}") from exc
    if not isinstance(data, list):
        raise TypeError(f"SQL JSON expected a list, got {type(data).__name__}")
    return data


def classify_failure(error: str, log_text: str) -> str:
    err = (error or "").strip()
    # Step/workflow error alone is decisive for cancel / agent / docker kills.
    if err and INFRA_RE.search(err):
        return "infra"
    blob = f"{err}\n{log_text or ''}"
    if INFRA_RE.search(blob):
        return "infra"
    if FLAKY_RE.search(blob) and not CODE_RE.search(blob):
        return "flaky"
    if CODE_RE.search(blob):
        return "code"
    if FLAKY_RE.search(blob):
        return "flaky"
    if err:
        return (
            "infra"
            if "error" in err.lower() and "assert" not in err.lower()
            else "code"
        )
    return "code"


def parse_workflows(rows: list):
    parsed = []
    for row in rows:
        parsed.append(
            {
                "repo": row.get("full_name") or "",
                "workflow": row.get("name") or "",
                "number": int(row.get("number") or 0),
                "pipeline_status": row.get("status") or "",
                "created": int(row.get("created") or 0),
                "pipeline_started": int(row.get("p_started") or 0),
                "pipeline_finished": int(row.get("p_finished") or 0),
                "started": int(row.get("w_started") or 0),
                "finished": int(row.get("w_finished") or 0),
                "state": row.get("state") or "",
            }
        )
    return parsed


def timing_for(row):
    created = row["created"]
    started = row["started"]
    finished = row["finished"]
    if not created or not started:
        return None
    wait = max(0, started - created)
    if not finished or finished < started:
        return None
    run = max(0, finished - started)
    total = max(0, finished - created)
    return wait, run, total


def load_failure_logs(host, stack, since_epoch):
    # One row per failed workflow: include w.error and any failed step type
    # (clone / commands / plugin / service), not only commands.
    sql = f"""
SELECT w.id AS workflow_id,
       r.full_name AS repo,
       w.name AS workflow,
       p.number AS number,
       w.state AS state,
       IFNULL(w.error, '') AS workflow_error,
       IFNULL((
         SELECT group_concat(
                  IFNULL(s.type, '') || ':' || IFNULL(s.name, '') || ':' || IFNULL(s.error, ''),
                  char(10)
                )
         FROM steps s
         WHERE s.pipeline_id = w.pipeline_id
           AND s.ppid = w.pid
           AND s.state IN ('failure', 'killed', 'error')
       ), '') AS step_errors,
       IFNULL((
         SELECT s.id
         FROM steps s
         WHERE s.pipeline_id = w.pipeline_id
           AND s.ppid = w.pid
           AND s.state IN ('failure', 'killed', 'error')
         ORDER BY CASE s.type
           WHEN 'commands' THEN 0
           WHEN 'clone' THEN 1
           WHEN 'plugin' THEN 2
           ELSE 3
         END, s.id
         LIMIT 1
       ), 0) AS step_id,
       IFNULL((
         SELECT s.name
         FROM steps s
         WHERE s.pipeline_id = w.pipeline_id
           AND s.ppid = w.pid
           AND s.state IN ('failure', 'killed', 'error')
         ORDER BY CASE s.type
           WHEN 'commands' THEN 0
           WHEN 'clone' THEN 1
           WHEN 'plugin' THEN 2
           ELSE 3
         END, s.id
         LIMIT 1
       ), '') AS step_name
FROM workflows w
JOIN pipelines p ON p.id = w.pipeline_id
JOIN repos r ON r.id = p.repo_id
WHERE p.created > {int(since_epoch)}
  AND w.state IN ('failure', 'killed', 'error')
ORDER BY w.id;
"""
    rows = run_sql_json(sql, host=host, stack=stack)
    step_ids = []
    meta = []
    for row in rows:
        sid = int(row.get("step_id") or 0)
        meta.append(
            {
                "workflow_id": int(row.get("workflow_id") or 0),
                "repo": row.get("repo") or "",
                "workflow": row.get("workflow") or "",
                "number": int(row.get("number") or 0),
                "state": row.get("state") or "",
                "workflow_error": row.get("workflow_error") or "",
                "step_errors": row.get("step_errors") or "",
                "step_name": row.get("step_name") or "",
                "step_id": sid,
            }
        )
        if sid:
            step_ids.append(sid)

    logs_by_step = defaultdict(list)
    if step_ids:
        id_list = ",".join(str(i) for i in sorted(set(step_ids)))
        log_sql = f"""
SELECT step_id AS step_id, CAST(data AS TEXT) AS line_text FROM (
  SELECT step_id, data, line,
         ROW_NUMBER() OVER (PARTITION BY step_id ORDER BY line DESC) AS rn
  FROM log_entries
  WHERE step_id IN ({id_list})
)
WHERE rn <= 60
ORDER BY step_id, rn;
"""
        try:
            log_rows = run_sql_json(log_sql, host=host, stack=stack)
        except (RuntimeError, TypeError) as exc:
            sys.stderr.write(
                f"ci_slo_report: batched logs failed ({exc}); using error text only\n"
            )
            log_rows = []
        for lr in log_rows:
            try:
                sid = int(lr.get("step_id") or 0)
            except (TypeError, ValueError):
                continue
            if sid:
                logs_by_step[sid].append(lr.get("line_text") or "")

    failures = []
    for m in meta:
        err_blob = "\n".join(x for x in (m["workflow_error"], m["step_errors"]) if x)
        log_text = "\n".join(logs_by_step.get(m["step_id"], []))
        cause = classify_failure(err_blob, log_text)
        failures.append(
            {
                "workflow_id": m["workflow_id"],
                "repo": m["repo"],
                "workflow": m["workflow"],
                "number": m["number"],
                "state": m["state"],
                "step": m["step_name"],
                "cause": cause,
                "error": err_blob[:300],
            }
        )
    return failures


def aggregate(rows, failures):
    buckets = defaultdict(
        lambda: {
            "wait": [],
            "run": [],
            "total": [],
            "n": 0,
            "incomplete": 0,
            "states": defaultdict(int),
        }
    )
    for row in rows:
        key = (row["repo"], row["workflow"])
        b = buckets[key]
        b["states"][row["state"] or "unknown"] += 1
        t = timing_for(row)
        if t is None:
            b["incomplete"] += 1
            continue
        wait, run, total = t
        b["wait"].append(wait)
        b["run"].append(run)
        b["total"].append(total)
        b["n"] += 1

    # One failure record per workflow (already aggregated in load_failure_logs).
    fail_by_key = defaultdict(lambda: {"code": 0, "infra": 0, "flaky": 0, "items": []})
    seen_wf = set()
    for f in failures:
        if f["workflow_id"] in seen_wf:
            continue
        seen_wf.add(f["workflow_id"])
        key = (f["repo"], f["workflow"])
        fail_by_key[key][f["cause"]] += 1
        fail_by_key[key]["items"].append(f)

    report_rows = []
    for key in sorted(buckets.keys()):
        b = buckets[key]
        for name in ("wait", "run", "total"):
            b[name].sort()
        fr = fail_by_key.get(key, {"code": 0, "infra": 0, "flaky": 0, "items": []})
        pending = int(b["states"].get("pending", 0)) + int(
            b["states"].get("running", 0)
        )
        report_rows.append(
            {
                "repo": key[0],
                "workflow": key[1],
                "n": b["n"],
                "incomplete": b["incomplete"],
                "pending_or_running": pending,
                "wait_p50": percentile(b["wait"], 50),
                "wait_p95": percentile(b["wait"], 95),
                "run_p50": percentile(b["run"], 50),
                "run_p95": percentile(b["run"], 95),
                "total_p50": percentile(b["total"], 50),
                "total_p95": percentile(b["total"], 95),
                "states": dict(b["states"]),
                "failures": {
                    "code": fr["code"],
                    "infra": fr["infra"],
                    "flaky": fr["flaky"],
                },
                "meets_15m_p95": (percentile(b["total"], 95) or 0) <= 900
                if b["n"]
                else False,
                "zero_infra": fr["infra"] == 0,
            }
        )
    return report_rows


def render_markdown(report_rows, failures, generated_at, window_hours):
    lines = []
    lines.append(f"# CI SLO report ({generated_at})")
    lines.append("")
    lines.append(
        f"Source: Woodpecker SQLite on M1. Window: last {window_hours}h. "
        "Times are queue wait / run / total (push→final) for finished workflows. "
        "Bar: p95 total ≤ 15m and zero infra failures. "
        "`inc` = unfinished / missing timestamps; failure counts are per workflow."
    )
    lines.append("")
    lines.append(
        "| Repo | Workflow | n | inc | wait p50 | wait p95 | run p50 | run p95 | total p50 | total p95 | ≤15m | infra | code | flaky |"
    )
    lines.append(
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: |"
    )
    for r in report_rows:
        short = r["repo"].split("/")[-1]
        ok = "yes" if r["meets_15m_p95"] else "NO"
        lines.append(
            "| {repo} | {wf} | {n} | {inc} | {w50} | {w95} | {r50} | {r95} | {t50} | {t95} | {ok} | {infra} | {code} | {flaky} |".format(
                repo=short,
                wf=r["workflow"],
                n=r["n"],
                inc=r["incomplete"],
                w50=fmt_secs(r["wait_p50"]),
                w95=fmt_secs(r["wait_p95"]),
                r50=fmt_secs(r["run_p50"]),
                r95=fmt_secs(r["run_p95"]),
                t50=fmt_secs(r["total_p50"]),
                t95=fmt_secs(r["total_p95"]),
                ok=ok,
                infra=r["failures"]["infra"],
                code=r["failures"]["code"],
                flaky=r["failures"]["flaky"],
            )
        )
    lines.append("")
    infra_n = sum(1 for f in failures if f["cause"] == "infra")
    code_n = sum(1 for f in failures if f["cause"] == "code")
    flaky_n = sum(1 for f in failures if f["cause"] == "flaky")
    lines.append(
        f"Failed workflows in window: {len(failures)} "
        f"(code={code_n}, infra={infra_n}, flaky={flaky_n})."
    )
    if failures:
        lines.append("")
        lines.append("## Failures")
        lines.append("")
        lines.append("| Repo | Workflow | # | State | Cause | Step | Error (trim) |")
        lines.append("| --- | --- | ---: | --- | --- | --- | --- |")
        for f in failures[:80]:
            err = (f.get("error") or "").replace("|", "/").replace("\n", " ")[:120]
            lines.append(
                f"| {f['repo'].split('/')[-1]} | {f['workflow']} | {f['number']} | "
                f"{f['state']} | {f['cause']} | {f.get('step') or '-'} | {err or '-'} |"
            )
        if len(failures) > 80:
            lines.append("")
            lines.append(
                f"_… {len(failures) - 80} more failures omitted from markdown._"
            )
    lines.append("")
    lines.append("Owner: mac-ops MO-118 (`scripts/woodpecker-ci/ci_slo_report.py`).")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--host",
        default=os.environ.get("M1_HOST", "m1"),
        help="SSH host for the M1 (empty = run locally)",
    )
    ap.add_argument(
        "--stack",
        default=os.environ.get(
            "WOODPECKER_STACK", "/Users/shyamsivakumar/Code/woodpecker-ci"
        ),
    )
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--json-out", default="")
    ap.add_argument("--md-out", default="")
    ap.add_argument(
        "--local", action="store_true", help="Query the DB on this machine (no SSH)"
    )
    args = ap.parse_args(argv)

    host = None if args.local else (args.host or None)
    since = int(datetime.now(timezone.utc).timestamp()) - args.hours * 3600

    wf_sql = f"""
SELECT r.full_name AS full_name, w.name AS name, p.number AS number, p.status AS status,
       p.created AS created, IFNULL(p.started,0) AS p_started, IFNULL(p.finished,0) AS p_finished,
       IFNULL(w.started,0) AS w_started, IFNULL(w.finished,0) AS w_finished, w.state AS state
FROM workflows w
JOIN pipelines p ON p.id = w.pipeline_id
JOIN repos r ON r.id = p.repo_id
WHERE p.created > {int(since)}
ORDER BY r.full_name, w.name, p.created;
"""
    raw_rows = run_sql_json(wf_sql, host=host, stack=args.stack)
    rows = parse_workflows(raw_rows)
    failures = load_failure_logs(host, args.stack, since)
    report_rows = aggregate(rows, failures)

    generated = now_pt()
    generated_s = generated.strftime("%Y-%m-%d %H:%M %Z")
    md = render_markdown(report_rows, failures, generated_s, args.hours)
    payload = {
        "generated_at": generated.isoformat(),
        "window_hours": args.hours,
        "since_epoch": since,
        "rows": report_rows,
        "failures": failures,
        "owner": "mac-ops/MO-118",
    }

    sys.stdout.write(md)
    if not md.endswith("\n"):
        sys.stdout.write("\n")

    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as f:
            f.write(md if md.endswith("\n") else md + "\n")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, TypeError) as e:
        print(f"ci_slo_report: {e}", file=sys.stderr)
        raise SystemExit(1)
