"""Script result commands; importing this module performs no work."""
import json
import subprocess
import sys


def reconcile(records, now):
    actions = []
    for record in records:
        if record.get("state") in ("PASS", "FAIL"):
            continue
        result = record.get("result")
        if result in ("PASS", "FAIL"):
            record["state"] = result
        elif now > record["deadline"]:
            record["state"] = "FAIL"
        else:
            continue
        if record["state"] == "FAIL":
            actions.append({"action": "recut", "repo": record["repo"],
                            "issue": record["issue"]})
    return actions


def run_script(repo, issue, sha, timeout, command, artifact):
    try:
        completed = subprocess.run(command, timeout=timeout, check=False)
        status = "PASS" if completed.returncode == 0 else "FAIL"
        reason = artifact if status == "PASS" else f"exit {completed.returncode}"
    except subprocess.TimeoutExpired:
        status, reason = "FAIL", "timeout"
    except OSError as exc:
        status, reason = "FAIL", f"launch error: {exc}"
    subprocess.run(["gh", "issue", "comment", str(issue), "--repo", repo,
                    "--body", f"RESULT: {status} {sha} {reason}"],
                   timeout=60, check=True)
    return int(status != "PASS")


def audit_main(now):
    records = json.load(sys.stdin)
    actions = reconcile(records, now)
    print(json.dumps({"records": records, "actions": actions}))
    return 0
