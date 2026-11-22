#!/usr/bin/env python3
"""Check labeled decisions against GitHub and the factory journal into outcomes.jsonl."""

import argparse, contextlib, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOURNAL = Path("~/.local/state/coordinator/journal").expanduser()
SRW = "shyamsivakumar/strategy-replay-workbench"
FFBT = "shyamsivakumar/fantasy-football-toolkit"
REPOS = {"mac-ops": "shyamsivakumar/mac-ops", "SRW": SRW, "strategy-replay-workbench": SRW,
         "FFBT": FFBT, "fantasy-football-toolkit": FFBT, "tunerise": "shyamsivakumar/tunerise",
         "Concerning": "digitized/Concerning"}
MAC_CONTEXTS = {"srw/agent-check"}
ROLLBACK_EVENTS = {"rollback", "rolled_back", "incident"}
SUBJECT_PATTERNS = (
    (re.compile(r"(shyamsivakumar/[\w.-]+)#(\d+)"), lambda m: (m[1], int(m[2]))),
    (re.compile(r"#(\d+) in (shyamsivakumar/[\w.-]+)"), lambda m: (m[2], int(m[1]))),
    (re.compile(r"\b(mac-ops|tunerise|Concerning|FFBT|SRW)\b[^#\n]{0,25}#(\d+)"), lambda m: (REPOS[m[1]], int(m[2]))),
    (re.compile(r"(SRW|FFBT)-(\d+)$"), lambda m: (REPOS[m[1]], int(m[2]))))
RECUT = re.compile(r"re-?cut")

def norm(s): return " ".join(str(s).split()).casefold()

def epoch(value):
    return float(value) if isinstance(value, (int, float)) else datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()

def parse_subject(label):
    for field in ("item_text", "id"):
        text = str(label.get(field) or "")
        for pattern, build in SUBJECT_PATTERNS:
            match = pattern.search(text)
            if match:
                return build(match)
    return None

def gh_json(args):
    done = subprocess.run(["gh", *args], capture_output=True, text=True)
    return json.loads(done.stdout) if done.returncode == 0 else None

def read_jsonl(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        with contextlib.suppress(json.JSONDecodeError):
            rows.append(json.loads(line))
    return rows

def read_journal(journal_dir):
    return [row for path in sorted(Path(journal_dir).glob("events-*.jsonl")) for row in read_jsonl(path)]

def revert_check(gh, cache, repo, sha, since):
    if repo not in cache:
        pages = gh(["api", "--paginate", "--slurp", f"repos/{repo}/commits?sha=main&since={since}&per_page=100"]) or []
        cache[repo] = [commit for page in pages for commit in page]
    hits = [c["sha"] for c in cache[repo] if f"This reverts commit {sha}" in ((c.get("commit") or {}).get("message") or "")]
    return (True, {"revert_sha": hits[0]}) if hits else (False, {})

def status_check(gh, repo, sha):
    statuses = [s for s in (gh(["api", f"repos/{repo}/commits/{sha}/status"]) or {}).get("statuses") or [] if s.get("context") in MAC_CONTEXTS]
    contexts = {"contexts": sorted({s["context"] for s in statuses})}
    pending = not statuses or any(s.get("state") == "pending" for s in statuses)
    return (None if pending else any(s.get("state") in ("failure", "error") for s in statuses)), contexts

def touches(row, repo, pr, ticket):
    return row.get("repo") == repo and ((pr is not None and row.get("pr") == pr) or (ticket is not None and row.get("ticket") == ticket))

def rollback_check(journal, repo, pr, ticket, ts):
    events = [r for r in journal if r.get("event") in ROLLBACK_EVENTS]
    hits = [r["ts"] for r in events if touches(r, repo, pr, ticket) and r.get("ts", 0) > ts]
    return (True, {"journal_ts": max(hits)}) if hits else ((False, {}) if events else (None, {}))

def recut_check(journal, repo, pr, ticket, ts):
    recuts = [r["ts"] for r in journal if r.get("event") == "recut" and touches(r, repo, pr, None) and r.get("ts", 0) > ts]
    closed = [r["ts"] for r in journal if r.get("event") == "ticket_closed" and touches(r, repo, None, ticket)]
    started = [r["ts"] for r in journal if r.get("event") == "ticket_started" and touches(r, repo, None, ticket)
               and r.get("ts", 0) > ts and closed and r["ts"] > max(closed)]
    if recuts or started:
        return True, {"journal_ts": max(recuts + started)}
    seen = [r.get("ts", 0) for r in journal if touches(r, repo, pr, ticket)]
    return (False, {"journal_ts": max(seen)}) if seen else (None, {})

def fetch(labels_dir, out_path, journal_dir, gh=gh_json, now=None):
    journal = read_journal(journal_dir)
    commits, rows = {}, []
    labels = read_jsonl(Path(labels_dir) / "labels.jsonl")
    since = min((l["ts"] for l in labels if "ts" in l), default=None)
    for label in labels:
        if (subject := parse_subject(label)) is None:
            continue
        repo, n = subject
        ts = epoch(label["ts"])
        view = gh(["pr", "view", str(n), "-R", repo, "--json", "state,mergedAt,mergeCommit,title"])
        ticket, pr = (None, n) if view is not None else (n, next((r["pr"] for r in journal if r.get("repo") == repo and r.get("ticket") == n and r.get("pr")), None))
        merged = bool(view) and view.get("state") == "MERGED" and bool(view.get("mergedAt")) and epoch(view["mergedAt"]) >= ts
        sha = ((view or {}).get("mergeCommit") or {}).get("oid")
        reverted, revert_ev = revert_check(gh, commits, repo, sha, since) if merged else (None, {})
        broke, broke_ev = status_check(gh, repo, sha) if merged else (None, {})
        rollback, rollback_ev = rollback_check(journal, repo, pr, ticket, ts)
        recut, recut_ev = (None, {}) if RECUT.search(norm(label.get("answer"))) else recut_check(journal, repo, pr, ticket, ts)
        rows.append({
            "id": label["id"], "repo": repo, "pr": pr, "ticket": ticket, "reverted": reverted, "main_broke": broke,
            "rollback_or_incident": rollback, "recut": recut, "checked_at": (now or datetime.now(timezone.utc)).isoformat(),
            "evidence": {"merge_sha": sha, **revert_ev, **broke_ev, **rollback_ev, **recut_ev}})
    Path(out_path).write_text("".join(json.dumps(row) + "\n" for row in rows))
    return rows

def cli(argv):
    parser = argparse.ArgumentParser(prog="outcomes.py")
    p = parser.add_subparsers(dest="command", required=True).add_parser("fetch")
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--journal", type=Path, default=JOURNAL)
    args = parser.parse_args(argv)
    rows = fetch(args.labels, args.out, args.journal)
    print(f"rows={len(rows)}")
    for key in ("reverted", "main_broke", "rollback_or_incident", "recut"):
        values = [row[key] for row in rows]
        print(f"{key}: true={values.count(True)} false={values.count(False)} null={values.count(None)}")
    return 0

def main(argv=None):
    return cli(sys.argv[1:] if argv is None else list(argv))

if __name__ == "__main__": sys.exit(main())
