"""Why each open ticket is not moving: one line per open issue in lane repos."""
import json
import os
import re
import subprocess

TICKETS_CONFIG = os.environ.get("COORDQ_TICKETS_CONFIG", os.path.expanduser("~/.coordinator/tickets.json"))
with open(TICKETS_CONFIG) as handle:
    CFG = json.load(handle)["repos"]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=200).stdout


for repo in CFG:
    if any(x in repo for x in ("cairn", "qabot", "strata")):
        continue
    issues = json.loads(run(["gh", "issue", "list", "-R", repo, "--state", "open", "--limit", "200", "--json", "number,title,labels"]) or "[]")
    if not issues:
        continue
    prs = json.loads(run(["gh", "pr", "list", "-R", repo, "--state", "open", "--json", "number,body"]) or "[]")
    pr_refs = {}
    for p in prs:
        for r in re.findall(r"\bRefs #(\d+)", p.get("body") or ""):
            pr_refs.setdefault(int(r), []).append(p["number"])
    numbers = {i["number"] for i in issues}
    owner, name = repo.split("/")
    q = "query{repository(owner:\"%s\",name:\"%s\"){issues(states:OPEN,first:100){nodes{number blockedBy(first:20){nodes{number state}}}}}}" % (owner, name)
    blocked = {}
    try:
        for n in json.loads(run(["gh", "api", "graphql", "-f", f"query={q}"]))["data"]["repository"]["issues"]["nodes"]:
            blocked[n["number"]] = [b["number"] for b in n["blockedBy"]["nodes"] if b["state"] == "OPEN"]
    except (ValueError, KeyError, TypeError):
        pass
    counts = {}
    for i in issues:
        stage = next((l["name"][6:] for l in i["labels"] if l["name"].startswith("stage:")), "none")
        b = blocked.get(i["number"], [])
        if i["number"] in pr_refs:
            state = f"has PR {pr_refs[i['number']]}"
        elif stage in ("hold", "backlog"):
            state = stage
        elif b:
            state = "blocked by " + ",".join(f"#{x}" for x in b)
        elif stage == "none":
            state = "ORPHAN started, no PR"
        else:
            state = "READY"
        counts[state.split(" ")[0]] = counts.get(state.split(" ")[0], 0) + 1
        print(f"{CFG[repo]['key']:5} #{i['number']:<5} {stage:8} {state[:40]:40} {i['title'][:60]}")
    print(f"== {repo}: {counts}\n")
