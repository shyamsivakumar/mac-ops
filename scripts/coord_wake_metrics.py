import argparse, collections, datetime, glob, json
import os, re, sqlite3, statistics, subprocess

WAKE = frozenset("alarm_raised round_cap merge_held close_failed launch_failed recut".split())
OFFSETS = {"EST": -5, "EDT": -4, "PST": -8, "PDT": -7, "PT": -8, "UTC": 0}
LAUNCH_RE = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d:\d\d) (\w+) \| tick \| (.*)$")
TICK_RE = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d:\d\d) (\w+) \| tick \(launchd\): (.*)$")
RUN_RE = re.compile(r"exit=(\d+) reply=(.*)")
ALARM_402 = re.compile(r"\b402\b")
ACTED_RE = re.compile(r"\b(restored|re-cut|resent)\b")
COUNT_RE = re.compile(r"\d+ (launch|queue|send|gates?)|1 park")
ZERO_RE = re.compile(r"\b0 (sends|launches|gates)")
POS_RE = re.compile(r"(?<![#\w.])([1-9]\d*) (queue items?|sends?|launch(?:es)?(?: by hand)?|gates?(?: by (?:me|hand|this tick))?|merges?(?: by me)?|repo (?:code )?writes?|parks?|cards?(?: added| changed)?|decisions? raised|restacks?|resends?)\b")


def epoch(day, hhmm, label):
    offset = OFFSETS.get(label)
    stamp = datetime.datetime(*map(int, day.split("-")), *map(int, hhmm.split(":")), tzinfo=datetime.timezone.utc)
    return None if offset is None else stamp.timestamp() - offset * 3600


def bound(text):
    if not text:
        return None
    stamp = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    return (stamp if stamp.tzinfo else stamp.replace(tzinfo=datetime.timezone.utc)).timestamp()


def inside(ts, since, until):
    return (since is None or ts >= since) and (until is None or ts < until)


def loads(line):
    try:
        return json.loads(line)
    except ValueError:
        return None


def read_lines(path):
    try:
        with open(path, errors="replace") as handle:
            return handle.read().splitlines()
    except OSError:
        return []


def summary(values):
    return {"n": len(values), "median": round(statistics.median(values), 1), "p90": round(sorted(values)[round(0.9 * (len(values) - 1))], 1)} if values else None


def stamp_lines(lines, pattern, since, until):
    for line in lines:
        match = pattern.match(line)
        if match and (ts := epoch(*match.group(1, 2, 3))) is not None and inside(ts, since, until):
            yield ts, match.group(4)


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ("journal", "launcher-log", "ticks-log", "inbox-dir", "since", "until", "github-prs", "repo", "reconcile-github", "json"):
        parser.add_argument("--" + name, action="store_true" if name in ("reconcile-github", "json") else "store")
    args = parser.parse_args(argv)
    since, until = bound(args.since), bound(args.until)
    missing = []
    journal = os.path.expanduser(args.journal or os.environ.get("COORD_JOURNAL_DIR") or "~/.local/state/coordinator/journal")
    launcher = os.path.expanduser(args.launcher_log or "~/Library/Logs/coordinator/tick.log")
    ticks = os.path.expanduser(args.ticks_log or "~/Code/coordinator/loop/ticks.log")
    state = os.path.expanduser(args.inbox_dir or os.environ.get("COORD_INBOX_DIR") or "~/.local/state/coordinator")
    for name, path in (("launcher-log", launcher), ("ticks-log", ticks)):
        if not os.path.exists(path):
            missing.append(name)

    files = sorted(glob.glob(os.path.join(journal, "events-*.jsonl"))) if os.path.isdir(journal) else ([journal] if os.path.exists(journal) else [])
    if not files and not os.path.isdir(journal):
        missing.append("journal")
    events = [row for path in files for row in map(loads, read_lines(path)) if isinstance(row, dict) and isinstance(row.get("ts"), (int, float)) and inside(row["ts"], since, until)]
    wake = [row for row in events if row.get("event") in WAKE]
    wake_ts = sorted(row["ts"] for row in wake)

    runs, failed, alerts, skipped, locked = [], 0, 0, 0, 0
    for ts, message in stamp_lines(read_lines(launcher), LAUNCH_RE, since, until):
        run = RUN_RE.match(message)
        failed += 1 if message.startswith("pi exited") and ALARM_402.search(message) else 0
        alerts += 1 if message.startswith("alert sent to") else 0
        skipped += 1 if message.startswith("skip:") else 0
        locked += 1 if message.startswith("skipped:") else 0
        if run:
            runs.append((ts, int(run.group(1)), run.group(2)))
    runs.sort()
    run_ts = [run[0] for run in runs]
    noop = sum(1 for run in runs if run[1] == 0 and run[2].startswith("NOOP"))
    buckets = {"failed": 0, "no_events": 0, "no_action": 0, "action": 0, "skipped": skipped, "lock_skipped": locked}
    for index, (ts, code, reply) in enumerate(runs):
        lower = runs[index - 1][0] if index else ts - 1800
        hit = "failed" if code else ("no_events" if not any(lower < stamp <= ts for stamp in wake_ts) else ("no_action" if reply.startswith("NOOP") else "action"))
        buckets[hit] += 1
    runs_per_day = round(len(runs) * 86400.0 / max(run_ts[-1] - run_ts[0], 3600.0), 1) if runs else 0

    keys = [(row.get("event"), row.get("repo"), row.get("pr"), row.get("head"), (row.get("data") or {}).get("alarm")) for row in wake]
    duplicate = round((len(keys) - len(set(keys))) / len(keys), 3) if keys else None
    low = since if since is not None else (min(wake_ts) if wake_ts else 0.0)
    high = until if until is not None else (max(wake_ts) if wake_ts else 0.0)
    journal_per_day = round(len(wake) * 86400.0 / max(high - low, 3600.0), 1) if wake else 0
    waits = [(min(c for c in run_ts if c > stamp) - stamp) / 60.0 for stamp in wake_ts if any(c > stamp for c in run_ts)]

    volume_inbox, latency_inbox, opened, windowed, inbox_ts = {}, {}, set(), [], []
    database = os.path.join(state, "inbox.db")
    if not os.path.exists(database):
        missing.append("inbox-dir")
    else:
        connection = sqlite3.connect("file:%s?mode=ro" % database, uri=True)
        rows = connection.execute("SELECT id, ts, kind, tier, pr, status, repo FROM inbox").fetchall()
        joins = connection.execute("SELECT inbox.tier, inbox.ts, outbox.sent_ts FROM inbox JOIN outbox ON outbox.run_id = inbox.run_id WHERE outbox.sent_ts IS NOT NULL").fetchall()
        connection.close()
        inbox_ts = [row[1] for row in rows]
        opened = {(row[6], row[4]) for row in rows if row[2] == "pr_opened"}
        kept = [row for row in rows if inside(row[1], since, until)]
        windowed = [(row[1], row[5]) for row in kept]
        volume_inbox = dict(collections.Counter("%s/%s" % (row[2], row[3]) for row in kept))
        for tier, ts, sent in [row for row in joins if inside(row[1], since, until)]:
            latency_inbox.setdefault(str(tier), []).append((sent - ts) / 60.0)

    tick_rows = []
    for ts, rest in stamp_lines(read_lines(ticks), TICK_RE, since, until):
        head = re.split(r";|\. Board| Board \d| Jobs alive", rest, maxsplit=1)[0]
        tick_rows.append((ts, head, bool(POS_RE.search(head)) or bool(ACTED_RE.search(head))))
    now = max(run_ts + [row["ts"] for row in events] + inbox_ts + [row[0] for row in tick_rows] or [0.0])
    stuck = sum(1 for ts, status in windowed if (status != "done" and now - ts > 7200) or status == "failed")
    counted = [row for row in tick_rows if COUNT_RE.match(row[1]) or ZERO_RE.search(row[1])]
    idle = sum(1 for row in counted if not row[2])

    prs = None
    repo = args.repo or "shyamsivakumar/mac-ops"
    if args.reconcile_github:
        prs = json.loads(subprocess.check_output(["gh", "pr", "list", "-R", repo, "--state", "all", "--limit", "1000", "--json", "number,createdAt"], text=True))
    elif args.github_prs:
        prs = json.loads("".join(read_lines(args.github_prs)) or "[]") if os.path.exists(args.github_prs) else None
        if prs is None:
            missing.append("github-prs")
    truncated = prs is not None and len(prs) >= 1000
    never = None if prs is None or truncated else sorted(pr["number"] for pr in prs if inside(bound(pr["createdAt"]), since, until) and (repo, pr["number"]) not in opened)

    output = {
        "runs": len(runs), "failed": failed, "noop": noop, "alerts": alerts, "runs_per_day": runs_per_day,
        "buckets": buckets,
        "volume": {"journal": dict(collections.Counter(row["event"] for row in wake)), "journal_per_day": journal_per_day, "inbox": volume_inbox},
        "latency": {"clock_wait_min": summary(waits), "inbox_min": {tier: summary(values) for tier, values in latency_inbox.items()}},
        "lost": {"fallback_acted": sum(1 for row in events if row.get("event") == "fallback_acted"), "stuck": stuck, "never_enqueued": never, "never_enqueued_truncated": truncated},
        "duplicate_rate": {"journal": duplicate},
        "summaries": {"count_format": len(counted), "no_action": idle, "share": round(idle / len(counted), 3) if counted else None},
        "missing": missing,
    }
    print(json.dumps(output) if args.json else json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
