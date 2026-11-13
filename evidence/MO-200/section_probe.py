"""Print the `Blocked by` section the ticket CLI reads, and the reasons it gives.

Usage: python3 evidence/MO-200/section_probe.py <path-to-ticket-cli> <issue-number> <repo>

The CLI itself stops on some of these tickets earlier, at the label check, so
this calls the same functions the `ticket start` path calls.
"""
import json
import subprocess
import sys
import types


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = path
    exec(compile(open(path).read(), path, "exec"), module.__dict__)
    return module


def main():
    cli, number, repo = sys.argv[1], sys.argv[2], sys.argv[3]
    mod = load(cli, "cli")
    cfg = json.load(open("coordinator/config/tickets.json"))
    issue = json.loads(subprocess.check_output(
        ["gh", "issue", "view", number, "-R", repo,
         "--json", "number,title,body,state,labels,comments,url,blockedBy"]))
    if hasattr(mod, "blocked_by_section"):
        section = mod.blocked_by_section(issue["body"])
    else:
        section = mod.body_section(issue["body"], "Blocked by")
    print("body section:", repr(section))
    print("reasons:", mod.section_blocker_reasons(cfg, repo, issue))


if __name__ == "__main__":
    main()
