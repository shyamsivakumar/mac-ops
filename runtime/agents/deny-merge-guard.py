#!/usr/bin/env python3
"""Deny rules for shell commands that `permissions.deny` cannot express (mac-ops #530).

PreToolUse hook for Claude Code, and the single implementation the pi deny
guards call for every bash command. The rules are read from the structure of
the command (the simple commands the shell would run), never from its text,
so a PR body, an `hc` message or a heredoc that mentions a rule is not a
command that breaks it:

- A `git push` is decided only from the destinations written in the command.
  It is refused when it names no explicit destination branch, when a
  destination is `main` or `master`, and when it is a force-push in any form.
- A command whose working directory is inside the Ascend tree is refused.

Exit 0 with a deny decision blocks the call; exit 0 with no output allows.
Installed by scripts/install_deny_rules.py; do not edit the installed copy.
"""

import json
import os
import re
import sys

PREFIX = "mac-ops deny rules (#530): "
FORCE_REASON = "force-push in any form is denied"
PROTECTED_REASON = "pushing to main or master is denied; push a task branch instead"
NO_DESTINATION_REASON = (
    "this push names no explicit destination branch; name the branch, "
    "for example `git push -u origin <task-branch>`"
)
PROTECTED = {"main", "master"}
BULK_FLAGS = {"--all", "--branches", "--mirror"}
GIT_VALUE_OPTIONS = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
    "--super-prefix",
    "--config-env",
}
PUSH_VALUE_OPTIONS = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_]\w*=")
DURATION_RE = re.compile(r"^[\d.]+[smhd]?$")
WRAPPERS = {
    "sudo",
    "command",
    "exec",
    "time",
    "nohup",
    "env",
    "nice",
    "builtin",
    "heavy",
    "timeout",
    "caffeinate",
}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
COMMAND_NAMES = WRAPPERS | SHELLS | {"git", "eval"}
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}"}
SEPARATORS = ";&|\n()`"
MAX_NESTING = 4
ASCEND_ROOTS = ["~/Code/slash-eureka"]
ASCEND_REASON = "reads and edits under ~/Code/slash-eureka (Ascend) are denied"
DIRECTORY_CHANGERS = {"cd", "pushd"}


def deny(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": PREFIX + reason,
        }
    }


def heredoc_start(text, i):
    i += 2
    strip_tabs = text.startswith("-", i)
    i += strip_tabs
    while i < len(text) and text[i] in " \t":
        i += 1
    delimiter, quote = "", ""
    while i < len(text) and (quote or text[i] not in " \t\n;&|()<>"):
        if quote:
            if text[i] == quote:
                quote = ""
            else:
                delimiter += text[i]
        elif text[i] in "\"'":
            quote = text[i]
        else:
            delimiter += text[i]
        i += 1
    return (delimiter, strip_tabs), i


def skip_heredoc_bodies(text, i, pending):
    for delimiter, strip_tabs in pending:
        while i < len(text):
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            line = text[i:end]
            i = min(end + 1, len(text))
            if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                break
    return i


def parse(text, i=0, nested=False):
    """The simple commands in `text` as word lists, and the index where parsing stopped.

    Quoted text stays inside its word and heredoc bodies are skipped. With
    `nested`, parsing stops after the `)` that closes a `$(` substitution.
    """
    commands, words, cur, quote, depth, pending = [], [], None, "", 0, []
    n = len(text)
    while i < n:
        ch = text[i]
        if quote:
            if ch == quote:
                quote = ""
            elif quote == '"' and text.startswith("$(", i):
                inner, i = parse(text, i + 2, True)
                commands += inner
                cur += "$()"
                continue
            elif quote == '"' and ch == "`" and text.find("`", i + 1) > 0:
                end = text.find("`", i + 1)
                commands += parse(text[i + 1 : end])[0]
                cur += "`"
                i = end + 1
                continue
            elif (
                ch == "\\"
                and quote == '"'
                and text[i + 1 : i + 2]
                and text[i + 1] in '"\\$`'
            ):
                i += 1
                cur += text[i]
            else:
                cur += ch
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            cur = cur or ""
        elif ch == "\\" and i + 1 < n:
            if text[i + 1] != "\n":
                cur = (cur or "") + text[i + 1]
            i += 1
        elif ch == "#" and cur is None:
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("<<", i) and not text.startswith("<<<", i):
            if cur is not None:
                words.append(cur)
                cur = None
            heredoc, i = heredoc_start(text, i)
            pending.append(heredoc)
            continue
        elif ch == "&" and cur and cur[-1] in "<>":
            cur += ch
        elif ch in " \t":
            if cur is not None:
                words.append(cur)
                cur = None
        elif ch in SEPARATORS:
            if cur is not None:
                words.append(cur)
                cur = None
            if words:
                commands.append(words)
                words = []
            if ch == ")" and nested and depth == 0:
                return commands, i + 1
            depth = depth + 1 if ch == "(" else max(depth - (ch == ")"), 0)
            if ch == "\n" and pending:
                i = skip_heredoc_bodies(text, i + 1, pending)
                pending = []
                continue
        else:
            cur = (cur or "") + ch
        i += 1
    if cur is not None:
        words.append(cur)
    if words:
        commands.append(words)
    return commands, n


def real_command(words):
    """The words after env assignments, shell keywords and wrappers such as `heavy` or `timeout`."""
    i = 0
    while i < len(words):
        if ASSIGNMENT_RE.match(words[i]) or words[i] in KEYWORDS:
            i += 1
            continue
        if os.path.basename(words[i]) not in WRAPPERS:
            break
        i += 1
        while i < len(words):
            arg = words[i]
            takes_value = (
                words[i - 1].startswith("-")
                and os.path.basename(arg) not in COMMAND_NAMES
            )
            if (
                arg.startswith("-")
                or ASSIGNMENT_RE.match(arg)
                or DURATION_RE.match(arg)
                or takes_value
            ):
                i += 1
            else:
                break
    return words[i:]


def shell_script(words):
    name = os.path.basename(words[0])
    if name == "eval":
        return " ".join(words[1:])
    if name in SHELLS:
        for position, word in enumerate(words[1:], start=1):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", word) and position + 1 < len(
                words
            ):
                return words[position + 1]
    return None


def real_commands(text, depth=0):
    for raw in parse(text)[0]:
        words = real_command(raw)
        if not words:
            continue
        script = shell_script(words)
        if script is not None and depth < MAX_NESTING:
            yield from real_commands(script, depth + 1)
        yield words


def push_arguments(words):
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in GIT_VALUE_OPTIONS else 1
    return words[i + 1 :] if i < len(words) and words[i] == "push" else None


def destination(token):
    ref = token.lstrip("+")
    ref = ref.split(":", 1)[1] if ":" in ref else ref
    return re.sub(r"^(?:refs/)?(?:heads/)?", "", ref)


def push_reason(args):
    """The first positional is the repository unless `--repo` names it; the rest are refspecs."""
    positionals, forced, bulk, repo_option, options_done, i = (
        [],
        False,
        False,
        False,
        False,
        0,
    )
    while i < len(args):
        arg = args[i]
        if not options_done and arg == "--":
            options_done = True
        elif not options_done and arg.startswith("-"):
            name = arg.split("=", 1)[0]
            forced = (
                forced
                or name.startswith("--force")
                or bool(re.fullmatch(r"-[A-Za-z]+", arg) and "f" in arg)
            )
            bulk = bulk or name in BULK_FLAGS
            if name in PUSH_VALUE_OPTIONS:
                repo_option = repo_option or name == "--repo"
                i += "=" not in arg
        else:
            positionals.append(arg)
        i += 1
    refspecs = positionals if repo_option else positionals[1:]
    if forced or any(token.startswith("+") and len(token) > 1 for token in positionals):
        return FORCE_REASON
    if bulk or not refspecs or any(token == ":" or "*" in token for token in refspecs):
        return NO_DESTINATION_REASON
    for token in refspecs:
        target = destination(token)
        if target in {"", "HEAD", "@"} or "$" in target or "`" in target:
            return NO_DESTINATION_REASON
        if target in PROTECTED:
            return PROTECTED_REASON
    return None


def in_ascend(path):
    real = os.path.realpath(path)
    for root in ASCEND_ROOTS:
        root = os.path.realpath(os.path.expanduser(root))
        if real == root or real.startswith(root + os.sep):
            return True
    return False


def directory_reason(commands, cwd):
    """Refuse a command whose working directory, or any `cd` target in it, is inside the Ascend tree."""
    here = cwd or os.getcwd()
    if in_ascend(here):
        return ASCEND_REASON
    for words in commands:
        targets = [w for w in words[1:] if not w.startswith("-")]
        if os.path.basename(words[0]) in DIRECTORY_CHANGERS and targets:
            here = os.path.join(here, os.path.expandvars(os.path.expanduser(targets[0])))
            if in_ascend(here):
                return ASCEND_REASON
    return None


def command_reason(command, cwd=None):
    commands = list(real_commands(command))
    reason = directory_reason(commands, cwd)
    for words in commands:
        args = push_arguments(words) if os.path.basename(words[0]) == "git" else None
        reason = reason or (push_reason(args) if args is not None else None)
    return reason


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    if tool_name != "Bash":
        return 0
    reason = command_reason(str(tool_input.get("command") or ""), payload.get("cwd"))
    if reason:
        print(json.dumps(deny(reason)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
