#!/usr/bin/env python3
"""Deny unpinned `gh pr merge` for Claude Code (mac-ops #530).

PreToolUse hook on the Bash tool. `permissions.deny` in the same settings
file cannot express "deny gh pr merge unless --match-head-commit", so the
merge rule lives here: builders never merge, while gate threads keep the
pinned `--match-head-commit` merge under Shyam's standing auto-merge rule.

Exit 0 with a deny decision blocks the call; exit 0 with no output allows.
The rule list is the single deny list from mac-ops runtime/agents/deny-rules.json;
scripts/install_deny_rules.py installs this file. Do not edit the installed
copy by hand; reinstall from mac-ops instead.
"""
import json
import re
import sys

MERGE_RE = re.compile(r"\bgh\s+pr\s+merge\b")
REQUIRED_FLAG = "--match-head-commit"
REASON = (
    "mac-ops deny rules (#530): gh pr merge is denied for builders; gates "
    "merge only with the pinned --match-head-commit head"
)


def decision(command):
    if MERGE_RE.search(command) and REQUIRED_FLAG not in command:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": REASON,
            }
        }
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input") or {}
    if not isinstance(command, dict):
        return 0
    deny = decision(str(command.get("command") or ""))
    if deny:
        print(json.dumps(deny))
    return 0


if __name__ == "__main__":
    sys.exit(main())
