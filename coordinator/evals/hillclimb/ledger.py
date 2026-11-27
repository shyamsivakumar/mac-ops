#!/usr/bin/env python3
"""Hill climb accept/reject ledger (item 7, part 1).

Builds local accept/reject rows from repos owned by shyamsivakumar. Every row
carries a `source` line so it can be deleted. Output stays under
~/Code/coordinator/evals/hillclimb/ledger/ and never enters a repository.
"""

import argparse
import collections
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~")
OUT = f"{HOME}/Code/coordinator/evals/hillclimb/ledger"
LABELS = f"{HOME}/Code/coordinator/evals/hillclimb/labels.jsonl"
TICKS = f"{HOME}/Code/coordinator/loop/ticks.log"
LANES = f"{HOME}/Code/coordinator/loop/lanes.log"
RECEIPTS = f"{HOME}/Code/coordinator/.overnight/receipts"
JOURNALS = f"{HOME}/.local/state/coordinator/journal"
SESSIONS = f"{HOME}/.claude/projects"
OWNER = "shyamsivakumar"
TEXT_MAX = 300

ASCEND = re.compile(
    r"ascend|useascend|slash-eureka|\bAUH\b|action-underwriting|data-ops|datahub|"
    r"(?:Code|projects|worktrees)[/-]dbt\b|\bdbt-work\b",
    re.IGNORECASE,
)
SECRET = re.compile(
    r"([a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@|authorization:\s*\S+(\s+\S+)?|"
    r"(password|passwd|secret|token|api[_-]?key)[\"']?\s*[=:]\s*\S+|"
    r"\b(ghp|gho|ghs|ghu|github_pat|sk|xox[bpas]|AKIA|AIza|ya29)[-_]?[A-Za-z0-9_-]{8,}|"
    r"\bBearer\s+\S+|-----BEGIN [A-Z ]*PRIVATE KEY|\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.|"
    r"(?<![\w/])(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])(?![0-9a-f]{32,64}\b)[A-Za-z0-9]{32,}(?![\w/]))",
    re.IGNORECASE,
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
SCAN_NAMES = ("ascend", "secret", "email")

REJECT_REPLY = re.compile(
    r"^\s*(no\b|nope|stop\b|don'?t\b|do not\b|wrong|revert|undo|that'?s not|not what|why did you|"
    r"you (didn'?t|forgot|missed)|\[request interrupted)",
    re.IGNORECASE,
)
ACCEPT_REPLY = re.compile(
    r"^\s*(yes|yep|yeah|y|ok|okay|go|go ahead|do it|approved?|ship it|looks good|lgtm|proceed|"
    r"merge it|sounds good|perfect|great)\b",
    re.IGNORECASE,
)
TICK_TOKEN = re.compile(r"^(merged|closed|gateok|gatefail|nudge)[a-z-]*:(.+)$")
TICK_ACCEPT = {"merged", "gateok"}
PROJECT_ALIASES = {
    "srw": "strategy-replay-workbench",
    "mac-ops": "mac-ops",
    "mo": "mac-ops",
}


class Ledger:
    def __init__(self):
        self.rows = {}
        self.counts = collections.Counter()
        self.dropped = collections.defaultdict(collections.Counter)
        self.skipped = []

    def add(self, source_kind, project, kind, label, context, outcome, source, ts=None):
        row = {
            "source_kind": source_kind,
            "project": project,
            "kind": kind,
            "label": label,
            "context": clip(context),
            "outcome": clip(outcome),
            "source": source,
            "ts": ts,
        }
        blob = json.dumps(row)
        for name, pattern in zip(SCAN_NAMES, (ASCEND, SECRET, EMAIL)):
            if pattern.search(blob):
                self.dropped[source_kind][name] += 1
                return
        row["id"] = hashlib.sha1(
            f"{source}|{label}|{row['context'][:80]}".encode()
        ).hexdigest()[:16]
        if row["id"] in self.rows:
            return
        self.rows[row["id"]] = row
        self.counts[source_kind] += 1

    def skip(self, name, reason):
        self.skipped.append({"source": name, "reason": str(reason)[:200]})
        print(f"skipped {name}: {reason}", file=sys.stderr)


def clip(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()[:TEXT_MAX]


def jsonl(path):
    with open(path, errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            try:
                yield number, json.loads(line)
            except ValueError:
                continue


def gh_json(args):
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=180, check=False
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:160])
    return json.loads(result.stdout)


def personal_repos():
    repos = gh_json(
        ["repo", "list", OWNER, "--limit", "200", "--json", "name,isFork,isArchived"]
    )
    return sorted(r["name"] for r in repos if not r["isFork"] and not r["isArchived"])


def local_personal_dirs():
    allowed = set()
    for config in glob.glob(f"{HOME}/Code/*/.git/config"):
        with open(config, errors="replace") as handle:
            if re.search(rf"github\.com[:/]{OWNER}/", handle.read()):
                allowed.add(config.split("/")[-3])
    return allowed


def from_prs(ledger, repos):
    for repo in repos:
        name = f"gh:{OWNER}/{repo}"
        try:
            prs = gh_json(
                [
                    "pr",
                    "list",
                    "-R",
                    f"{OWNER}/{repo}",
                    "--state",
                    "all",
                    "--limit",
                    "400",
                    "--json",
                    "number,title,state,closedAt,url,comments,reviews",
                ]
            )
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            ledger.skip(name, error)
            continue
        for pr in prs:
            if pr["state"] == "OPEN":
                continue
            label = "accept" if pr["state"] == "MERGED" else "reject"
            source = f"{OWNER}/{repo}#{pr['number']} {pr['url']}"
            is_revert = pr["title"].lower().startswith("revert")
            ledger.add(
                "pr",
                repo,
                "revert_pr" if is_revert else "pr",
                "reject" if is_revert else label,
                pr["title"],
                pr["state"].lower(),
                source,
                pr["closedAt"],
            )
            for item in pr["comments"] + pr["reviews"]:
                if item.get("body"):
                    ledger.add(
                        "review_comment",
                        repo,
                        "review",
                        label,
                        pr["title"],
                        item["body"],
                        f"{source} comment",
                        item.get("createdAt"),
                    )


def from_reverts(ledger, repos):
    for repo in repos:
        try:
            for page in range(1, 4):
                commits = gh_json(
                    ["api", f"repos/{OWNER}/{repo}/commits?per_page=100&page={page}"]
                )
                for commit in commits:
                    message = commit["commit"]["message"]
                    if message.startswith("Revert"):
                        ledger.add(
                            "revert_commit",
                            repo,
                            "revert",
                            "reject",
                            message.split("\n")[0],
                            "reverted",
                            f"{OWNER}/{repo}@{commit['sha'][:12]}",
                            commit["commit"]["committer"]["date"],
                        )
                if len(commits) < 100:
                    break
        except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
            ledger.skip(f"gh-commits:{OWNER}/{repo}", error)


def from_gates(ledger):
    for path in sorted(glob.glob(f"{JOURNALS}/events-*.jsonl")):
        try:
            for number, event in jsonl(path):
                repo = event.get("repo") or ""
                data = event.get("data") or {}
                if event.get("event") != "gate_verdict" or not repo.startswith(
                    f"{OWNER}/"
                ):
                    continue
                if data.get("verdict") not in ("PASS", "FAIL"):
                    continue
                ledger.add(
                    "gate_journal",
                    repo.split("/")[1],
                    "gate",
                    "accept" if data["verdict"] == "PASS" else "reject",
                    f"gate on {repo}#{event.get('pr')}",
                    f"{data['verdict']} {data.get('class', '')}",
                    f"journal {os.path.basename(path)}:{number} {repo}#{event.get('pr')}@{str(event.get('head'))[:12]}",
                    event.get("ts"),
                )
        except OSError as error:
            ledger.skip(path, error)
    try:
        for path in sorted(glob.glob(f"{RECEIPTS}/*.md")):
            with open(path, errors="replace") as handle:
                text = handle.read()
            fields = dict(re.findall(r"^- (\w[\w ]*): (.*)$", text, re.MULTILINE))
            repo = fields.get("Repo", "")
            if fields.get("Gate") not in ("PASS", "FAIL") or not repo.startswith(
                f"{OWNER}/"
            ):
                continue
            ledger.add(
                "gate_receipt",
                repo.split("/")[1],
                "gate",
                "accept" if fields["Gate"] == "PASS" else "reject",
                text.split("\n")[0].lstrip("# "),
                fields.get("Stopped because") or fields.get("State"),
                f"receipt {os.path.basename(path)} {fields.get('PR', '')}",
            )
    except OSError as error:
        ledger.skip(RECEIPTS, error)


def from_labels(ledger):
    try:
        for number, label in jsonl(LABELS):
            if label.get("agree") not in (True, False):
                continue
            ledger.add(
                "board_label",
                "coordinator",
                label.get("kind", "other"),
                "accept" if label["agree"] else "reject",
                label.get("item_text"),
                f"recommended: {label.get('recommended')} | answered: {label.get('answer')}",
                f"labels.jsonl:{number} id={label.get('id')} <- {label.get('source')}",
                label.get("ts"),
            )
    except OSError as error:
        ledger.skip(LABELS, error)


def from_ticks(ledger):
    for path in (TICKS, LANES):
        try:
            with open(path, errors="replace") as handle:
                for number, line in enumerate(handle, 1):
                    parts = line.split(" | ")
                    if len(parts) < 3 or not re.match(
                        r"\d{4}-\d\d-\d\dT[\d:]+Z", parts[0]
                    ):
                        continue
                    for token in parts[1].split():
                        match = TICK_TOKEN.match(token)
                        if not match:
                            continue
                        word = token.split(":")[0]
                        base = match.group(1)
                        target = match.group(2)
                        project = PROJECT_ALIASES.get(
                            re.split(r"[#@]", target)[0].lower(), "coordinator"
                        )
                        ledger.add(
                            "ticks_nudge" if base == "nudge" else "ticks_log",
                            project,
                            base,
                            "accept" if base in TICK_ACCEPT else "reject",
                            f"{parts[0]} {word}",
                            target,
                            f"{os.path.basename(path)}:{number}",
                            parts[0],
                        )
        except OSError as error:
            ledger.skip(path, error)


def message_text(message):
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def session_pairs(path):
    previous = ""
    for number, record in jsonl(path):
        kind = record.get("type")
        if record.get("isSidechain") or kind not in ("user", "assistant"):
            continue
        text = message_text(record.get("message") or {})
        if kind == "assistant":
            previous = text or previous
        elif (
            text and not record.get("isMeta") and not text.startswith("<") and previous
        ):
            yield number, previous, text, record.get("timestamp")


def from_sessions(ledger, allowed):
    for path in sorted(glob.glob(f"{SESSIONS}/-Users-shyamsivakumar-Code-*/*.jsonl")):
        if "slash-eureka" in path:
            continue
        try:
            first = next((r.get("cwd") for _, r in jsonl(path) if r.get("cwd")), None)
        except OSError as error:
            ledger.skip(path, error)
            continue
        parts = (first or "").replace(f"{HOME}/Code/", "", 1).split("/")
        if (
            not first
            or not first.startswith(f"{HOME}/Code/")
            or parts[0] not in allowed
            or "agent-" in first
        ):
            ledger.dropped["session"]["not_personal_folder"] += 1
            continue
        session_id = os.path.basename(path)[:-6]
        try:
            for number, assistant, reply, ts in session_pairs(path):
                rejected = REJECT_REPLY.match(reply)
                if rejected or (len(reply) < 80 and ACCEPT_REPLY.match(reply)):
                    ledger.add(
                        "session",
                        parts[0],
                        "turn",
                        "reject" if rejected else "accept",
                        assistant[-TEXT_MAX:],
                        reply,
                        f"claude-session {session_id}:{number} {os.path.basename(os.path.dirname(path))}",
                        ts,
                    )
        except OSError as error:
            ledger.skip(path, error)


def extract_rules(rows, top=5, minimum=5):
    groups = collections.defaultdict(lambda: {"accept": [], "reject": []})
    for row in rows:
        groups[(row["project"], row["kind"])][row["label"]].append(row)
    rules = []
    for (project, kind), sides in sorted(groups.items()):
        if len(sides["accept"]) < minimum or len(sides["reject"]) < minimum:
            continue
        counts = {side: collections.Counter() for side in sides}
        for side, items in sides.items():
            for row in items:
                words = re.findall(
                    r"[a-z][a-z0-9_-]{3,}", f"{row['context']} {row['outcome']}".lower()
                )
                counts[side].update(set(words))
        size = {side: len(items) for side, items in sides.items()}

        def rate(side, word, counts=counts, size=size):
            return (counts[side][word] + 1) / (size[side] + 2)

        vocabulary = set(counts["accept"]) | set(counts["reject"])
        lean = {
            w: rate("reject", w) / rate("accept", w)
            for w in vocabulary
            if counts["accept"][w] + counts["reject"][w] >= 3
        }
        ranked = sorted(lean, key=lean.get)
        rules.append(
            {
                "project": project,
                "kind": kind,
                "accept": size["accept"],
                "reject": size["reject"],
                "reject_terms": ranked[::-1][:top],
                "accept_terms": ranked[:top],
            }
        )
    return rules


def verify(path):
    hits = collections.Counter()
    with open(path) as handle:
        for line in handle:
            for name, pattern in zip(SCAN_NAMES, (ASCEND, SECRET, EMAIL)):
                if pattern.search(line):
                    hits[name] += 1
    return {name: hits[name] for name in SCAN_NAMES}


def main():
    parser = argparse.ArgumentParser(
        description="Build the hill climb accept/reject ledger from personal repos, local only."
    )
    parser.add_argument("--out", default=OUT)
    parser.add_argument(
        "--dry-run", action="store_true", help="print counts and write nothing"
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        choices=["prs", "reverts", "gates", "labels", "ticks", "sessions"],
    )
    args = parser.parse_args()
    ledger = Ledger()
    try:
        repos = personal_repos()
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        ledger.skip("gh repo list", error)
        repos = []
    steps = {
        "prs": lambda: from_prs(ledger, repos),
        "reverts": lambda: from_reverts(ledger, repos),
        "gates": lambda: from_gates(ledger),
        "labels": lambda: from_labels(ledger),
        "ticks": lambda: from_ticks(ledger),
        "sessions": lambda: from_sessions(ledger, local_personal_dirs()),
    }
    for name, step in steps.items():
        if name not in args.skip:
            step()
    rows = sorted(ledger.rows.values(), key=lambda r: (r["source_kind"], r["source"]))
    summary = {
        "rows": len(rows),
        "per_source": dict(ledger.counts),
        "per_label": dict(collections.Counter(r["label"] for r in rows)),
        "dropped": {k: dict(v) for k, v in ledger.dropped.items()},
        "dropped_totals": {
            k: sum(v[k] for v in ledger.dropped.values())
            for k in ("ascend", "secret", "email", "not_personal_folder")
        },
        "skipped_sources": ledger.skipped,
        "scanner": "conservative regex set (ASCEND, SECRET, EMAIL) applied to every row before write",
    }
    if not args.dry_run:
        os.makedirs(args.out, exist_ok=True)
        path = f"{args.out}/ledger.jsonl"
        with open(path, "w") as handle:
            handle.writelines(json.dumps(r) + "\n" for r in rows)
        summary["output_scan_hits"] = verify(path)
        with open(f"{args.out}/summary.json", "w") as handle:
            json.dump(summary, handle, indent=2)
        with open(f"{args.out}/rules_draft.json", "w") as handle:
            json.dump(extract_rules(rows), handle, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
