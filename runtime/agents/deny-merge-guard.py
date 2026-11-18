#!/usr/bin/env python3
"""Deny rules Claude Code's `permissions.deny` cannot express (mac-ops #530).

PreToolUse hook on the Bash tool. `permissions.deny` in the same settings file
matches command prefixes, so it cannot say "deny gh pr merge unless the caller
is a gate and the pin is a merge argument", nor can it name every remote a
push might target. This hook carries both rules:

- `gh pr merge` is denied unless the caller is a gate and the pin is given as
  a merge argument. The role comes from the environment the gate was launched
  with, never from the command text, so a builder cannot claim it by typing.
- a push to a protected branch (`main`, `master`) is denied for every remote,
  and a force-push is denied in any form.

Exit 0 with a deny decision blocks the call; exit 0 with no output allows.
The rule list is the single deny list from mac-ops runtime/agents/deny-rules.json;
scripts/install_deny_rules.py installs this file. Do not edit the installed
copy by hand; reinstall from mac-ops instead.
"""
import json
import os
import re
import shlex
import sys

MERGE_RE = re.compile(r"\bgh\s+pr\s+merge\b")
REQUIRED_FLAG = "--match-head-commit"
PIN_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
# The merge flags that take a value. The word after one of these is that
# flag's value, so it is never a merge argument of its own.
MERGE_VALUE_FLAGS = {"--body", "-b", "--body-file", "-F", "--subject", "-t", "--author-email"}
SHELL_SEPARATORS = re.compile(r"[;&|\n]+")
ROLE_ENV = "MAC_OPS_ROLE"
ROLE_VALUE = "gate"
# The provider instance that carries the gate role (installed with the rules).
# Launching a thread on it hands the gate role to that thread, so only a gate
# caller may name it.
GATE_INSTANCE = "claudeAgentGate"
THREAD_TOOLS = ("thread_launch", "thread_send", "create_threads")
THREAD_REASON = (
    "mac-ops deny rules (#530): launching a thread on the gate instance is "
    "denied for builders; the gate role is handed out by the trusted launcher"
)
REASON = (
    "mac-ops deny rules (#530): gh pr merge is denied for builders; only a "
    "gate thread, with the pinned --match-head-commit head as a merge "
    "argument, may merge"
)

PUSH_RE = re.compile(
    r"\bgit(?:\s+(?:-C\s+(?:\"[^\"]*\"|'[^']*'|\S+)|-c\s+\S+|--[\w-]+=\S+))*\s+push\b(.*)",
    re.S,
)
FORCE_FLAGS = {
    "--force",
    "-f",
    "--force-with-lease",
    "--force-if-includes",
}
PROTECTED = {"main", "master"}
FORCE_REASON = "mac-ops deny rules (#530): force-push in any form is denied"
PROTECTED_REASON = (
    "mac-ops deny rules (#530): pushing to main or master is denied for any "
    "remote; push a task branch instead"
)


def deny(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def merge_words(segment):
    """The merge invocation's words, with quoted text kept as one word.

    A split on whitespace turns the inside of a quoted argument into words of
    its own, so a flag and a commit id written inside a PR subject read as a
    merge argument. The shell keeps a quoted argument whole, so the pin is
    read from the words the shell would pass to `gh`.
    """
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return []


def pinned_commit(segment):
    """The commit the merge segment pins, or "" when it is not an argument."""
    tokens = merge_words(segment)
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == REQUIRED_FLAG:
            value = tokens[index + 1] if index + 1 < len(tokens) else ""
            return value if PIN_RE.match(value) else ""
        if token.startswith(REQUIRED_FLAG + "="):
            value = token[len(REQUIRED_FLAG) + 1 :]
            return value if PIN_RE.match(value) else ""
        index += 2 if token in MERGE_VALUE_FLAGS else 1
    return ""


def is_gate(environ=None):
    return (environ if environ is not None else os.environ).get(ROLE_ENV) == ROLE_VALUE


def merge_decision(command, environ=None):
    """Deny an unpinned merge, and any merge by a caller that is not a gate."""
    if not MERGE_RE.search(command):
        return None
    if not is_gate(environ):
        return deny(REASON)
    for segment in SHELL_SEPARATORS.split(command):
        if MERGE_RE.search(segment) and not pinned_commit(segment):
            return deny(REASON)
    return None


def destination_ref(token):
    """The destination branch a push argument writes to."""
    ref = token.split(":", 1)[1] if ":" in token else token
    ref = ref.lstrip("+").lstrip("^")
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/") :]
    return ref


def push_decision(command):
    """Deny a force-push, and a push to main or master on any remote.

    The first bare word after `push` is the repository argument: it names a
    remote or a URL, never a destination branch. Comparing it as a refspec
    refused a valid task-branch push to a remote called `main` or `master`
    (`git push main task-530`), so only the words after it are destinations.
    A lone `main`/`master` names no destination of its own, so it stays
    refused: the push would write whatever branch is checked out.
    """
    match = PUSH_RE.search(command)
    if not match:
        return None
    words = [token.strip("\"'") for token in match.group(1).split()]
    words = [token for token in words if token]
    for token in words:
        if token in FORCE_FLAGS or token.startswith("+") and len(token) > 1:
            return deny(FORCE_REASON)
    bare = [token for token in words if not token.startswith("-")]
    for position, token in enumerate(bare):
        # The first bare word is the repository argument (a remote name or a
        # URL) when another word follows it, and a bare word is not a refspec.
        if position == 0 and ":" not in token and len(bare) > 1:
            continue
        if destination_ref(token) in PROTECTED:
            return deny(PROTECTED_REASON)
    return None


def thread_decision(tool_input, environ=None):
    """Deny a builder's launch of a thread that would carry the gate role."""
    if is_gate(environ):
        return None
    if GATE_INSTANCE in json.dumps(tool_input, sort_keys=True):
        return deny(THREAD_REASON)
    return None


def decision(command, environ=None):
    return merge_decision(command, environ) or push_decision(command)


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    if tool_name == "Bash":
        result = decision(str(tool_input.get("command") or ""))
    elif any(name in tool_name for name in THREAD_TOOLS):
        result = thread_decision(tool_input)
    else:
        result = None
    if result:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
