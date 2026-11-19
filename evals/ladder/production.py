#!/usr/bin/env python3
import argparse
import json
import random
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

COORDINATOR = Path.home() / "Code" / "coordinator"
HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache" / "production.json"
MIN_PRS = 5
BOOTSTRAPS = 2000
VERDICT = re.compile(r"VERDICT:\s*(PASS|FAIL)\s*\W*\s*$")
GATE_KEY = re.compile(r"gate:(?P<repo>.+)#(?P<pr>\d+):(?P<head>[0-9a-f]{40})$")


def run_json(command, stdin=None):
    done = subprocess.run(command, input=stdin, capture_output=True, text=True, timeout=120)
    return json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None


def thread_read(thread_id):
    return run_json(["t3mcp", "call", "t3_thread_read", "-"],
                    json.dumps({"threadId": thread_id, "limit": 3, "runLimit": 5, "maxCharsPerItem": 20000}))


def parse_verdict(text):
    found = VERDICT.search((text or "").strip()[-300:])
    return found[1] if found else "UNKNOWN"


def builder_label(read):
    thread = read["thread"]
    executed = next((r["executedModel"] for r in read.get("recentRuns", []) if r.get("executedModel")), None)
    return f"{thread.get('providerInstanceId')}/{executed or thread.get('model')}"


class Live:
    def __init__(self):
        self.queue = json.loads((COORDINATOR / "queue" / "queue.json").read_text())
        self.receipts = json.loads((COORDINATOR / "queue" / "dispatch-receipts.json").read_text())
        self.ledger = json.loads((COORDINATOR / "loop" / "lanes-ledger.json").read_text())
        try:
            self.cache = json.loads(CACHE.read_text())
        except (OSError, ValueError):
            self.cache = {}

    def cached(self, key, fetch, keep=lambda value: value is not None):
        if key not in self.cache:
            value = fetch()
            if not keep(value):
                return value
            self.cache[key] = value
        return self.cache[key]

    def save_cache(self):
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(self.cache))

    def pulls(self, repo):
        order = {key: i for i, key in enumerate(self.receipts)}
        grouped = defaultdict(list)
        for key in sorted(self.queue["gatedHeads"], key=lambda k: order.get(k, len(order))):
            found = GATE_KEY.match(key)
            if found and found["repo"] == repo:
                grouped[int(found["pr"])].append(self.receipts.get(key))
        return grouped

    def pr_info(self, repo, number):
        def fetch():
            pull = run_json(["gh", "api", f"repos/{repo}/pulls/{number}"])
            if not pull:
                return None
            refs = re.findall(r"\bRefs #(\d+)\b", pull.get("body") or "")
            return {"created": pull["created_at"][:10], "merged": bool(pull.get("merged_at")),
                    "closed": pull["state"] == "closed", "issue": int(refs[0]) if refs else None}
        info = self.cached(f"pr:{repo}#{number}", fetch, lambda v: v and v["closed"])
        return info

    def ticket_type(self, repo, issue):
        def fetch():
            data = run_json(["gh", "api", f"repos/{repo}/issues/{issue}"])
            if data is None:
                return None
            return next((l["name"][5:] for l in data["labels"] if l["name"].startswith("type:")), "untyped")
        return self.cached(f"type:{repo}#{issue}", fetch) or "unknown"

    def builder(self, repo, issue):
        prefix = f"ticket:{repo}#{issue}:a"
        attempts = [k for k in self.receipts if k.startswith(prefix)]
        if not attempts:
            return "unknown"
        thread_id = self.receipts[max(attempts, key=lambda k: int(k[len(prefix):]))]
        return self.cached(f"builder:{thread_id}", lambda: (lambda r: builder_label(r) if r else None)(thread_read(thread_id))) or "unknown"

    def verdict(self, thread_id):
        if not thread_id:
            return "UNKNOWN"
        def fetch():
            read = thread_read(thread_id)
            if not read:
                return None
            texts = [i["text"] for i in read["items"] if i.get("type") == "assistant_message" and i.get("text")]
            return parse_verdict(texts[-1]) if texts else "UNKNOWN"
        value = self.cached(f"verdict:{thread_id}", fetch, lambda v: v in ("PASS", "FAIL"))
        return value or "UNKNOWN"

    def ledger_rounds(self, repo, number):
        return (self.ledger.get(f"rounds:{repo}#{number}") or {}).get("count")


class Fixture:
    def __init__(self, path):
        self.data = json.loads(Path(path).read_text())

    def pulls(self, repo):
        return {p["pr"]: p["gates"] for p in self.data["prs"] if p["repo"] == repo}

    def _pr(self, repo, number):
        return next(p for p in self.data["prs"] if p["repo"] == repo and p["pr"] == number)

    def pr_info(self, repo, number):
        p = self._pr(repo, number)
        return {"created": p["created"], "merged": p["merged"], "closed": p["closed"], "issue": number}

    def ticket_type(self, repo, issue):
        return self._pr(repo, issue)["type"]

    def builder(self, repo, issue):
        return self._pr(repo, issue)["model"]

    def verdict(self, gate):
        return parse_verdict(gate) if gate else "UNKNOWN"

    def ledger_rounds(self, repo, number):
        return None

    def save_cache(self):
        pass


def collect(source, repos, since):
    jobs = [(repo, number, gates) for repo in repos for number, gates in source.pulls(repo).items()]

    def one(job):
        repo, number, gates = job
        info = source.pr_info(repo, number)
        if not info or (since and info["created"] < since):
            return None
        issue = info["issue"]
        return {"repo": repo, "pr": number,
                "model": source.builder(repo, issue) if issue else "unknown",
                "type": source.ticket_type(repo, issue) if issue else "unknown",
                "verdicts": [source.verdict(g) for g in gates],
                "abandoned": info["closed"] and not info["merged"],
                "ledger_rounds": source.ledger_rounds(repo, number)}

    with ThreadPoolExecutor(8) as pool:
        return [r for r in pool.map(one, jobs) if r]


def bootstrap(flags, rng):
    if not flags:
        return None
    rates = sorted(sum(rng.choices(flags, k=len(flags))) / len(flags) for _ in range(BOOTSTRAPS))
    return [round(rates[int(0.05 * BOOTSTRAPS)], 3), round(rates[int(0.95 * BOOTSTRAPS) - 1], 3)]


def summarise(records):
    rng = random.Random(0)
    groups = defaultdict(list)
    for r in records:
        groups[(r["model"], "all")].append(r)
        groups[(r["model"], r["type"])].append(r)
    rows = []
    for (model, kind), prs in sorted(groups.items()):
        first = [r["verdicts"][0] == "PASS" for r in prs if r["verdicts"] and r["verdicts"][0] != "UNKNOWN"]
        rounds = [r["verdicts"].index("PASS") + 1 for r in prs if "PASS" in r["verdicts"]]
        rows.append({
            "model": model, "type": kind, "prs": len(prs), "too_few": len(prs) < MIN_PRS,
            "first_gate_known": len(first), "first_gate_unknown": len(prs) - len(first),
            "first_gate_pass_rate": round(sum(first) / len(first), 3) if first else None,
            "first_gate_pass_ci90": bootstrap(first, rng),
            "rounds_to_pass_mean": round(statistics.mean(rounds), 2) if rounds else None,
            "rounds_to_pass_median": statistics.median(rounds) if rounds else None,
            "abandoned_share": round(sum(r["abandoned"] for r in prs) / len(prs), 3)})
    return rows


def markdown(rows, args, total):
    cell = lambda v: "-" if v is None else str(v)
    lines = [f"# Builder model production signal, {date.today()}", "",
             f"{total} PRs, each counted once. Repos: {args.repo or 'all'}. Since: {args.since or 'start'}.", "",
             "Builder model assignment is not random: harder work may go to different models. "
             "Compare models only within a ticket type.", "",
             "Unknown or missing gate verdicts are never counted as a pass. The pass rate "
             "covers PRs whose first gate verdict is known; the unknown column counts the rest. "
             "Rounds to PASS count gated heads up to the first PASS. Abandoned means closed unmerged.", "",
             "| model | type | PRs | first-gate pass | 90% interval | unknown | mean rounds | median rounds | abandoned |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        note = " (too few)" if r["too_few"] else ""
        lines.append(f"| {r['model']} | {r['type']} | {r['prs']}{note} | {cell(r['first_gate_pass_rate'])} | "
                     f"{cell(r['first_gate_pass_ci90'])} | {r['first_gate_unknown']} | "
                     f"{cell(r['rounds_to_pass_mean'])} | {cell(r['rounds_to_pass_median'])} | {r['abandoned_share']} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Read-only builder model report from coordinator data.")
    parser.add_argument("--since", help="only PRs created on or after YYYY-MM-DD")
    parser.add_argument("--repo", action="append", help="owner/name, repeatable (default: every gated repo)")
    parser.add_argument("--fixture", help="replay a fixture file instead of live coordinator data")
    parser.add_argument("--out", default=str(HERE / "reports"))
    args = parser.parse_args()
    source = Fixture(args.fixture) if args.fixture else Live()
    repos = args.repo or sorted({r for r in (
        [p["repo"] for p in source.data["prs"]] if args.fixture
        else [GATE_KEY.match(k)["repo"] for k in source.queue["gatedHeads"] if GATE_KEY.match(k)])})
    records = collect(source, repos, args.since)
    source.save_cache()
    rows = summarise(records)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"production-{date.today()}"
    stem.with_suffix(".json").write_text(json.dumps({"since": args.since, "repos": repos, "prs": records, "rows": rows}, indent=2) + "\n")
    stem.with_suffix(".md").write_text(markdown(rows, args, len(records)))
    print(f"{len(records)} PRs -> {stem}.md")


if __name__ == "__main__":
    sys.exit(main())
