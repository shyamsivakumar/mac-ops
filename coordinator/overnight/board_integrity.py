import json
import re
import sys

STAGE_PREFIX = "stage:"
# The hold label reads as a stage on the board but is its own family: a held
# ticket keeps its stage beside the hold, so the hold never counts as the one
# stage label a ticket needs.
HOLD_LABEL = "stage:hold"


def stage_labels(issue):
    """The stage values of an open issue, in lower case, without the hold family.

    The labels are read in lower case because GitHub keeps the spelling a
    label was created with, so `Stage:Backlog` carries the same stage as
    `stage:backlog` and must read the same here.
    """
    names = [label["name"].lower() for label in issue["labels"]]
    return [name[len(STAGE_PREFIX):] for name in names
            if name.startswith(STAGE_PREFIX) and name != HOLD_LABEL]


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
            names = [label["name"].lower() for label in issue["labels"]]
            stages = stage_labels(issue)
            if len(stages) != 1:
                found.append(f"{ref}: expected exactly one stage label, found {len(stages)}")
            if "backlog" in stages or HOLD_LABEL in names:
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
                if not issue or issue["state"].upper() != "OPEN":
                    continue
                # Label names are compared in lower case, the way the delivery
                # path compares them, so `Stage:Started` is the started stage
                # and not a lost one.
                if "stage:started" not in [label["name"].lower() for label in issue["labels"]]:
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
