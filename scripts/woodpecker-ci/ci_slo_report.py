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
    r"^Canceled$|\bCanceled\b|\bcanceled by\b|cancel previous|superseded)",
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
    r"FAIL\s+\S+|pytest\.|Error: fast check failed|exit code [1-9]|"
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


def run_sql(sql: str, *, host: str | None, stack: str) -> str:
    """Run read-only SQL against woodpecker.sqlite. host=None means local M1."""
    b64 = base64.b64encode(sql.encode()).decode()
    remote = f"""
set -eu
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
export PATH
ROOT={stack!r}
. "$ROOT/scripts/common.sh"
sql=$(printf '%s' {b64!r} | base64 -D 2>/dev/null || printf '%s' {b64!r} | base64 -d)
query_db "$sql"
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
    return proc.stdout


def classify_failure(error: str, log_text: str) -> str:
    blob = f"{error or ''}\n{log_text or ''}"
    if INFRA_RE.search(blob):
        return "infra"
    if FLAKY_RE.search(blob) and not CODE_RE.search(blob):
        return "flaky"
    if CODE_RE.search(blob):
        return "code"
    if FLAKY_RE.search(blob):
        return "flaky"
    # Empty logs with a docker-ish step.error already caught; bare failures → code.
    if (error or "").strip():
        return (
            "infra"
            if "error" in error.lower() and "assert" not in error.lower()
            else "code"
        )
    return "code"


def parse_workflows(raw: str):
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 10:
            continue
        (
            full_name,
            workflow,
            number,
            p_status,
            created,
            p_started,
            p_finished,
            w_started,
            w_finished,
            w_state,
        ) = parts[:10]
        rows.append(
            {
                "repo": full_name,
                "workflow": workflow,
                "number": int(number),
                "pipeline_status": p_status,
                "created": int(created or 0),
                "pipeline_started": int(p_started or 0),
                "pipeline_finished": int(p_finished or 0),
                "started": int(w_started or 0),
                "finished": int(w_finished or 0),
                "state": w_state,
            }
        )
    return rows


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
    # One query for failed command steps, one batched log tail (last 60 lines
    # per step via window), so we do not SSH once per failure.
    sql = f"""
SELECT w.id, r.full_name, w.name, p.number, w.state,
       IFNULL(s.error,''), IFNULL(s.name,''), IFNULL(s.id,0)
FROM workflows w
JOIN pipelines p ON p.id = w.pipeline_id
JOIN repos r ON r.id = p.repo_id
LEFT JOIN steps s ON s.pipeline_id = w.pipeline_id
  AND s.ppid = w.pid
  AND s.type = 'commands'
  AND s.state IN ('failure','killed','error')
WHERE p.created > {since_epoch}
  AND w.state IN ('failure','killed','error')
ORDER BY w.id;
"""
    raw = run_sql(sql, host=host, stack=stack)
    step_ids = []
    meta = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 8:
            continue
        wid, repo, workflow, number, state, error, step_name, step_id = parts[:8]
        sid = int(step_id or 0)
        meta.append(
            (int(wid), repo, workflow, int(number), state, error, step_name, sid)
        )
        if sid:
            step_ids.append(sid)

    logs_by_step = defaultdict(list)
    if step_ids:
        id_list = ",".join(str(i) for i in sorted(set(step_ids)))
        log_sql = f"""
SELECT step_id, CAST(data AS TEXT) FROM (
  SELECT step_id, data, line,
         ROW_NUMBER() OVER (PARTITION BY step_id ORDER BY line DESC) AS rn
  FROM log_entries
  WHERE step_id IN ({id_list})
)
WHERE rn <= 60
ORDER BY step_id, rn;
"""
        try:
            log_raw = run_sql(log_sql, host=host, stack=stack)
        except RuntimeError as exc:
            # Older SQLite without window functions: fall back to error text only.
            sys.stderr.write(
                f"ci_slo_report: batched logs failed ({exc}); using step.error only\n"
            )
            log_raw = ""
        for line in log_raw.splitlines():
            if "|" not in line:
                continue
            sid_s, text = line.split("|", 1)
            try:
                logs_by_step[int(sid_s)].append(text)
            except ValueError:
                continue

    failures = []
    for wid, repo, workflow, number, state, error, step_name, sid in meta:
        log_text = "\n".join(logs_by_step.get(sid, []))
        cause = classify_failure(error, log_text)
        failures.append(
            {
                "workflow_id": wid,
                "repo": repo,
                "workflow": workflow,
                "number": number,
                "state": state,
                "step": step_name,
                "cause": cause,
                "error": (error or "")[:300],
            }
        )
    return failures


def aggregate(rows, failures):
    buckets = defaultdict(
        lambda: {"wait": [], "run": [], "total": [], "n": 0, "states": defaultdict(int)}
    )
    for row in rows:
        t = timing_for(row)
        if t is None:
            continue
        wait, run, total = t
        key = (row["repo"], row["workflow"])
        b = buckets[key]
        b["wait"].append(wait)
        b["run"].append(run)
        b["total"].append(total)
        b["n"] += 1
        b["states"][row["state"]] += 1

    fail_by_key = defaultdict(lambda: {"code": 0, "infra": 0, "flaky": 0, "items": []})
    for f in failures:
        key = (f["repo"], f["workflow"])
        fail_by_key[key][f["cause"]] += 1
        fail_by_key[key]["items"].append(f)

    report_rows = []
    for key in sorted(buckets.keys()):
        b = buckets[key]
        for name in ("wait", "run", "total"):
            b[name].sort()
        fr = fail_by_key.get(key, {"code": 0, "infra": 0, "flaky": 0, "items": []})
        report_rows.append(
            {
                "repo": key[0],
                "workflow": key[1],
                "n": b["n"],
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
                "meets_15m_p95": (percentile(b["total"], 95) or 0) <= 900,
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
        "Times are queue wait / run / total (push→final). "
        "Bar: p95 total ≤ 15m and zero infra failures."
    )
    lines.append("")
    lines.append(
        "| Repo | Workflow | n | wait p50 | wait p95 | run p50 | run p95 | total p50 | total p95 | ≤15m | infra | code | flaky |"
    )
    lines.append(
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: |"
    )
    for r in report_rows:
        short = r["repo"].split("/")[-1]
        ok = "yes" if r["meets_15m_p95"] else "NO"
        lines.append(
            "| {repo} | {wf} | {n} | {w50} | {w95} | {r50} | {r95} | {t50} | {t95} | {ok} | {infra} | {code} | {flaky} |".format(
                repo=short,
                wf=r["workflow"],
                n=r["n"],
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
        f"Failures in window: {len(failures)} "
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
SELECT r.full_name, w.name, p.number, p.status,
       p.created, IFNULL(p.started,0), IFNULL(p.finished,0),
       IFNULL(w.started,0), IFNULL(w.finished,0), w.state
FROM workflows w
JOIN pipelines p ON p.id = w.pipeline_id
JOIN repos r ON r.id = p.repo_id
WHERE p.created > {since}
ORDER BY r.full_name, w.name, p.created;
"""
    raw = run_sql(wf_sql, host=host, stack=args.stack)
    rows = parse_workflows(raw)
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
    except RuntimeError as e:
        print(f"ci_slo_report: {e}", file=sys.stderr)
        raise SystemExit(1)
