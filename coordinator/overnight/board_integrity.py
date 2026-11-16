import json
import re
import sys


def defects(snapshot):
    found = []
    for repo, data in sorted(snapshot["repos"].items()):
        issues = {i["number"]: i for i in data["issues"]}
        keys = {}
        parked = set()
        for number, issue in sorted(issues.items()):
            if issue["state"].upper() != "OPEN":
                continue
            ref = f"{repo}#{number}"
            stages = [l["name"][6:] for l in issue["labels"] if l["name"].startswith("stage:")]
            if len(stages) != 1:
                found.append(f"{ref}: expected exactly one stage")
            if any(s in ("backlog", "hold") for s in stages):
                parked.add(number)
            match = re.match(r"^([A-Z][A-Z0-9]*-[1-9][0-9]*)(?=[:\s]|$)", issue["title"])
            if not match or not match[1].startswith(data["key"] + "-"):
                found.append(f"{ref}: malformed key")
            else:
                keys.setdefault(match[1], []).append(number)
        for key, numbers in sorted(keys.items()):
            if len(numbers) > 1:
                found.append(f"{repo}: duplicate key {key}: {numbers}")
        for ticket in snapshot["tickets"]:
            if ticket["repo"] == repo and ticket["stage"] == "started":
                issue = issues.get(ticket["number"])
                if issue and issue["state"].upper() == "OPEN" and "stage:started" not in [l["name"] for l in issue["labels"]]:
                    found.append(f"{repo}#{ticket['number']}: started lost stage:started")
        for pr in data["prs"]:
            refs = {int(n) for n in re.findall(r"\bRefs #(\d+)\b", pr.get("body") or "")}
            if pr["state"].upper() == "OPEN":
                for parked_number in sorted(refs & parked):
                    for number, issue in sorted(issues.items()):
                        blockers = issue.get("blockedBy", {"nodes": [], "totalCount": 0})
                        if blockers["totalCount"] != len(blockers["nodes"]):
                            raise ValueError("truncated blockers")
                        if issue["state"].upper() == "OPEN" and any(b["number"] == parked_number and b.get("repository", {}).get("nameWithOwner", repo) == repo for b in blockers["nodes"]):
                            found.append(f"{repo}#{number}: blocked by parked #{parked_number} with open PR #{pr['number']}")
            if pr["state"].upper() == "MERGED":
                for number in sorted(refs):
                    if number in issues and issues[number]["state"].upper() == "OPEN":
                        found.append(f"{repo}#{number}: merged PR #{pr['number']} issue still open")
    return sorted(found)


def main():
    findings = defects(json.load(sys.stdin))
    for finding in findings:
        print(finding)
    return int(bool(findings))
