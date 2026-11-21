#!/usr/bin/env python3
"""Flag failed Coordinator runs from traces with deterministic rules; no LLM."""

import argparse
import collections
import datetime
import glob
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
HOME = Path.home()
TEXT_LOGS = [
    HOME / "Code/coordinator/loop/ticks.log",
    HOME / "Code/coordinator/loop/decisions.md",
    HOME / "Library/Logs/coordinator/lanes.log",
    HOME / "Code/coordinator/queue/gatekeep.log",
    HOME / "Code/coordinator/queue/gatekeep-stuck.txt",
]
GH_USAGE = HOME / "Library/Logs/coordinator/gh-usage.jsonl"
PI_GLOBS = [
    str(HOME / ".pi/agent/sessions/*/*.jsonl"),
    str(HOME / ".pi/agent-coordinator/sessions/*/*.jsonl"),
]

RULES = {
    "rate_limit": re.compile(
        r"rate.?limit|\b429\b|API floor|optional reads stopped", re.I
    ),
    "context_overflow": re.compile(
        r"context (length|window|overflow)|maximum context|too many tokens|prompt is too long",
        re.I,
    ),
    "retry": re.compile(r"\bretry(ing)?\b|\bretried\b|attempt \d+ of \d+", re.I),
    "tool_failure": re.compile(
        r"Traceback|ITEM ERROR|request failed|\bexit=[1-9]|command failed", re.I
    ),
}
SECRET = re.compile(
    r"([a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@|authorization:\s*\S+(\s+\S+)?|(password|passwd|secret|token|api[_-]?key)[\"']?\s*[=:]\s*\S+|"
    r"\b(ghp|gho|ghs|github_pat|sk|xox[bp])[-_][A-Za-z0-9_-]{8,}|\bBearer\s+\S+)",
    re.I,
)
STAMP = re.compile(r"(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d(?::\d\d)?)(?:\.\d+)?(Z?)")
UTC = datetime.timezone.utc
LOS_ANGELES = ZoneInfo("America/Los_Angeles")
LOOP_MIN = 3
ERRORS_MIN = 5
BURST_PER_MINUTE = 60
SKIPPED = collections.Counter()


def failure_category(body):
    return next((rule for rule, rx in RULES.items() if rx.search(body)), "unclassified")


def redact(text):
    return SECRET.sub("[redacted]", text)[:300]


def parse_ts(text):
    m = STAMP.search(text)
    if not m:
        return None
    clock = m.group(2) if m.group(2).count(":") == 2 else m.group(2) + ":00"
    zone = UTC if m.group(3) else LOS_ANGELES
    naive = datetime.datetime.fromisoformat(f"{m.group(1)}T{clock}")
    return naive.replace(tzinfo=zone).timestamp()


def row(source, rule, start, end, excerpt, key):
    iso = lambda t: (
        None
        if t is None
        else datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat()
    )
    run_id = hashlib.sha1(f"{source}|{rule}|{key}".encode()).hexdigest()[:12]
    return {
        "run_id": run_id,
        "source": str(source),
        "start": iso(start),
        "end": iso(end),
        "rule": rule,
        "excerpt": redact(excerpt),
    }


def merge(source, hits):
    rows, current = [], None
    for rule, ts, line_no, text in hits:
        if current and current["rule"] == rule and line_no - current["last"] <= 2:
            current["last"], current["end"] = line_no, ts or current["end"]
            continue
        if current:
            rows.append(
                row(
                    source,
                    current["rule"],
                    current["start"],
                    current["end"],
                    current["text"],
                    current["first"],
                )
            )
        current = {
            "rule": rule,
            "start": ts,
            "end": ts,
            "first": line_no,
            "last": line_no,
            "text": text,
        }
    if current:
        rows.append(
            row(
                source,
                current["rule"],
                current["start"],
                current["end"],
                current["text"],
                current["first"],
            )
        )
    return rows


def mine_text(path, since):
    if not path.exists():
        SKIPPED["missing text log"] += 1
        return []
    if path.stat().st_mtime < since:
        return []
    hits, last_ts, seen_stamp, repeats, prev = [], None, False, 0, None
    for n, line in enumerate(path.read_text(errors="replace").splitlines()):
        ts = parse_ts(line)
        seen_stamp |= ts is not None
        last_ts = ts or last_ts
        if seen_stamp and (last_ts or 0) < since:
            continue
        line = line.strip()
        for rule, rx in RULES.items():
            if rx.search(line):
                hits.append((rule, last_ts, n, line))
                break
        shape = STAMP.sub("", line)
        repeats = repeats + 1 if shape and shape == prev else 1
        prev = shape
        if repeats == LOOP_MIN:
            hits.append(("loop", last_ts, n, f"same line {LOOP_MIN}+ times: {line}"))
    return merge(path, sorted(hits, key=lambda h: (h[2], h[0])))


def mine_gh_usage(since):
    if not GH_USAGE.exists() or GH_USAGE.stat().st_mtime < since:
        return []
    per_minute = collections.Counter()
    for line in GH_USAGE.read_text().splitlines():
        try:
            ts = json.loads(line)["ts"]
        except (ValueError, KeyError, TypeError):
            SKIPPED["bad gh-usage record"] += 1
            continue
        if ts >= since:
            per_minute[int(ts // 60)] += 1
    hits = [
        ("rate_limit", m * 60, m, f"{c} gh calls in one minute")
        for m, c in sorted(per_minute.items())
        if c >= BURST_PER_MINUTE
    ]
    return merge(GH_USAGE, hits)


def mine_pi(path, since, max_seconds):
    stamps, calls, errors, flags, assistant_errors = [], [], [], [], []
    for line in path.read_text(errors="replace").splitlines():
        try:
            rec = json.loads(line)
            stamp = rec.get("timestamp")
            if isinstance(stamp, str):
                stamp = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError):
            SKIPPED["bad pi record"] += 1
            continue
        if isinstance(stamp, float):
            stamps.append(stamp)
        msg = rec.get("message") or {}
        if msg.get("role") == "assistant":
            calls += [
                (c["name"], json.dumps(c.get("arguments"), sort_keys=True))
                for c in msg["content"]
                if c.get("type") == "toolCall"
            ]
            if msg.get("errorMessage"):
                category = failure_category(msg["errorMessage"])
                flags.append(("tool_failure", f"assistant error: {category}"))
                assistant_errors.append((category, f"assistant error: {category}"))
        if msg.get("role") == "toolResult" and msg.get("isError"):
            body = " ".join(
                c.get("text", "") for c in msg["content"] if c.get("type") == "text"
            )
            category = failure_category(body)
            errors.append((category, f"{msg.get('toolName')} failed: {category}"))
    if not stamps or stamps[-1] < since:
        return None
    if len(errors) >= ERRORS_MIN:
        flags.append(("tool_failure", f"{len(errors)} failed tool calls, first: {errors[0][1]}"))
    for i in range(len(calls) - LOOP_MIN + 1):
        if len(set(calls[i : i + LOOP_MIN])) == 1:
            flags.append(("loop", f"{calls[i][0]} called {LOOP_MIN}+ times in a row"))
            break
    for rule in ("rate_limit", "context_overflow", "retry"):
        hit = next((e for c, e in assistant_errors + errors if c == rule), None)
        if hit:
            flags.append((rule, hit))
    if stamps[-1] - stamps[0] > max_seconds:
        flags.append(
            (
                "long_run",
                f"{(stamps[-1] - stamps[0]) / 60:.0f} minutes, {len(calls)} tool calls",
            )
        )
    return [
        row(path, rule, stamps[0], stamps[-1], text, rule) for rule, text in dict(reversed(flags)).items()
    ], (stamps[0], stamps[-1], len(calls))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", required=True, help="YYYY-MM-DD, UTC")
    ap.add_argument(
        "--max-minutes",
        type=int,
        default=60,
        help="pi session duration that counts as a long run",
    )
    ap.add_argument(
        "--samples",
        type=int,
        default=5,
        help="normal pi sessions to sample as success_sample",
    )
    ap.add_argument("--seed", type=int, default=742)
    ap.add_argument("--out-dir", default=str(HERE / "traces"))
    args = ap.parse_args()
    since = (
        datetime.datetime.fromisoformat(args.since)
        .replace(tzinfo=datetime.timezone.utc)
        .timestamp()
    )

    rows = []
    for path in TEXT_LOGS:
        rows += mine_text(path, since)
    rows += mine_gh_usage(since)
    clean = []
    for path in sorted(p for g in PI_GLOBS for p in map(Path, glob.glob(g))):
        mined = mine_pi(path, since, args.max_minutes * 60)
        if mined is None:
            continue
        flagged, (start, end, calls) = mined
        if flagged:
            rows += flagged
        else:
            clean.append(
                row(
                    path,
                    "success_sample",
                    start,
                    end,
                    f"{calls} tool calls, no rule fired",
                    "ok",
                )
            )
    rows += random.Random(args.seed).sample(clean, min(args.samples, len(clean)))

    out = (
        Path(args.out_dir)
        / f"flagged-{datetime.datetime.now().astimezone().date().isoformat()}.jsonl"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    for rule, n in sorted(collections.Counter(r["rule"] for r in rows).items()):
        print(f"{rule}: {n}")
    print(f"pi sessions without a flag: {len(clean)}")
    for reason, n in sorted(SKIPPED.items()):
        print(f"skipped {reason}: {n}")
    print(f"wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
