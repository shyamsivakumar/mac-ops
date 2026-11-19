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

Both rules read the shell command's structure, never its text. The command is
split into the simple commands the shell would run (quoted text stays inside
its word, heredoc bodies are skipped), and a rule fires only on a real
`git push` or `gh pr merge` command. A push is judged by the destination ref
of its refspecs, so a PR body, an `hc` message or a commit message that names
a protected branch or describes these rules is not a push to it.

Exit 0 with a deny decision blocks the call; exit 0 with no output allows.
The rule list is the single deny list from mac-ops runtime/agents/deny-rules.json;
scripts/install_deny_rules.py installs this file. Do not edit the installed
copy by hand; reinstall from mac-ops instead.
"""

import json
import os
import re
import sys

REQUIRED_FLAG = "--match-head-commit"
PIN_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
# The merge flags that take a value. The word after one of these is that
# flag's value, so it is never a merge argument of its own.
MERGE_VALUE_FLAGS = {
    "--body",
    "-b",
    "--body-file",
    "-F",
    "--subject",
    "-t",
    "--author-email",
}
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
COMMAND_NAMES = WRAPPERS | SHELLS | {"git", "gh", "eval"}
SEPARATOR_CHARS = ";&|\n()`"
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
FORCE_FLAGS = {"--force", "-f", "--force-with-lease", "--force-if-includes"}
PROTECTED = {"main", "master"}
FORCE_REASON = "mac-ops deny rules (#530): force-push in any form is denied"
PROTECTED_REASON = (
    "mac-ops deny rules (#530): pushing to main or master is denied for any "
    "remote; push a task branch instead"
)
MAX_NESTING = 4


def deny(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def skip_heredoc_bodies(text, index, heredocs):
    for delimiter, strip_tabs in heredocs:
        while index < len(text):
            end = text.find("\n", index)
            line = text[index : len(text) if end < 0 else end]
            index = len(text) if end < 0 else end + 1
            if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                break
    return index


def heredoc_delimiter(text, index):
    delimiter = ""
    quote = ""
    while index < len(text) and (quote or text[index] not in " \t\n;&|()<>"):
        char = text[index]
        if quote:
            if char == quote:
                quote = ""
            else:
                delimiter += char
        elif char in "\"'":
            quote = char
        else:
            delimiter += char
        index += 1
    return delimiter, index


def substitution_end(text, index):
    depth = 1
    quote = ""
    heredocs = []
    length = len(text)
    while index < length:
        char = text[index]
        if quote:
            if char == "\\" and quote == '"':
                index += 1
            elif char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "\\":
            index += 1
        elif text.startswith("<<", index) and not text.startswith("<<<", index):
            cursor = index + 2
            strip_tabs = text.startswith("-", cursor)
            cursor += 1 if strip_tabs else 0
            while cursor < length and text[cursor] in " \t":
                cursor += 1
            delimiter, index = heredoc_delimiter(text, cursor)
            heredocs.append((delimiter, strip_tabs))
            continue
        elif char == "\n" and heredocs:
            index = skip_heredoc_bodies(text, index + 1, heredocs)
            heredocs = []
            continue
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return length


def shell_commands(text):
    """The simple commands in `text`, each as the words the shell would pass.

    Quoted text stays inside its word, so a protected branch named inside a
    PR body or a message is never a word of the command that carries it.
    Heredoc bodies are skipped; separators (`;`, `&`, `|`, newline, `(`, `)`,
    backtick) end a command.
    """
    commands = []
    words = []
    word = ""
    started = False
    quote = ""
    heredocs = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if quote:
            if char == quote:
                quote = ""
            elif quote == '"' and text.startswith("$(", index):
                end = substitution_end(text, index + 2)
                commands.extend(shell_commands(text[index + 2 : end]))
                word += text[index : end + 1]
                index = end + 1
                continue
            elif quote == '"' and char == "`" and text.find("`", index + 1) > 0:
                end = text.find("`", index + 1)
                commands.extend(shell_commands(text[index + 1 : end]))
                word += text[index : end + 1]
                index = end + 1
                continue
            elif (
                char == "\\"
                and quote == '"'
                and index + 1 < length
                and text[index + 1] in '"\\$`'
            ):
                word += text[index + 1]
                index += 1
            else:
                word += char
            index += 1
            continue
        if char in "\"'":
            quote = char
            started = True
        elif char == "\\" and index + 1 < length:
            if text[index + 1] != "\n":
                word += text[index + 1]
                started = True
            index += 1
        elif char == "#" and not started:
            while index < length and text[index] != "\n":
                index += 1
            continue
        elif text.startswith("<<", index) and not text.startswith("<<<", index):
            if started:
                words.append(word)
                word = ""
                started = False
            cursor = index + 2
            strip_tabs = text.startswith("-", cursor)
            cursor += 1 if strip_tabs else 0
            while cursor < length and text[cursor] in " \t":
                cursor += 1
            delimiter, index = heredoc_delimiter(text, cursor)
            heredocs.append((delimiter, strip_tabs))
            continue
        elif char == "&" and started and word[-1] in "<>":
            word += char
        elif char in " \t":
            if started:
                words.append(word)
                word = ""
                started = False
        elif char in SEPARATOR_CHARS:
            if started:
                words.append(word)
                word = ""
                started = False
            if words:
                commands.append(words)
                words = []
            if char == "\n" and heredocs:
                index = skip_heredoc_bodies(text, index + 1, heredocs)
                heredocs = []
                continue
        else:
            word += char
            started = True
        index += 1
    if started:
        words.append(word)
    if words:
        commands.append(words)
    return commands


def real_command(words):
    """The command's words after env assignments and wrapper commands.

    `heavy`, `timeout`, `sudo` and the like run the command that follows
    them, so a push or merge behind one is still a push or merge.
    """
    index = 0
    while index < len(words):
        word = words[index]
        if ASSIGNMENT_RE.match(word):
            index += 1
            continue
        if os.path.basename(word) not in WRAPPERS:
            break
        index += 1
        while index < len(words):
            argument = words[index]
            takes_value = (
                words[index - 1].startswith("-")
                and os.path.basename(argument) not in COMMAND_NAMES
            )
            if (
                argument.startswith("-")
                or ASSIGNMENT_RE.match(argument)
                or DURATION_RE.match(argument)
                or takes_value
            ):
                index += 1
            else:
                break
    return words[index:]


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
    for words in shell_commands(text):
        words = real_command(words)
        if not words:
            continue
        script = shell_script(words)
        if script is not None and depth < MAX_NESTING:
            yield from real_commands(script, depth + 1)
        yield words


def pinned_commit(tokens):
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


def merge_decision(commands, environ=None):
    for words in commands:
        if os.path.basename(words[0]) != "gh" or words[1:3] != ["pr", "merge"]:
            continue
        if not is_gate(environ) or not pinned_commit(words[3:]):
            return deny(REASON)
    return None


def destination_ref(token):
    ref = token.lstrip("+")
    ref = ref.split(":", 1)[1] if ":" in ref else ref
    ref = ref.lstrip("^")
    if ref.startswith("refs/heads/"):
        ref = ref.removeprefix("refs/heads/")
    return ref


def push_arguments(words):
    index = 1
    while index < len(words):
        word = words[index]
        if not word.startswith("-"):
            return words[index + 1 :] if word == "push" else None
        index += 2 if word in GIT_VALUE_OPTIONS else 1
    return None


def push_verdict(arguments):
    """Deny a force-push, and a push whose destination ref is protected.

    The first bare word after `push` is the repository argument when another
    word follows it: it names a remote or a URL, never a destination branch,
    so a task-branch push to a remote called `main` is not a push to main.
    A lone bare word is read as a refspec, so `git push main` stays refused:
    it would write whatever branch is checked out.
    """
    bare = []
    has_repo_option = False
    options_done = False
    forced = False
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if not options_done and argument == "--":
            options_done = True
        elif not options_done and argument.startswith("-"):
            name = argument.split("=", 1)[0]
            if (
                name.startswith("--force")
                or name in FORCE_FLAGS
                or re.fullmatch(r"-[A-Za-z]+", argument)
                and "f" in argument[1:]
            ):
                forced = True
            if name in PUSH_VALUE_OPTIONS:
                has_repo_option = has_repo_option or name == "--repo"
                index += 0 if "=" in argument else 1
        else:
            bare.append(argument)
        index += 1
    if forced or any(token.startswith("+") and len(token) > 1 for token in bare):
        return deny(FORCE_REASON)
    refspecs = bare if has_repo_option or len(bare) <= 1 else bare[1:]
    if any(destination_ref(token) in PROTECTED for token in refspecs):
        return deny(PROTECTED_REASON)
    return None


def push_decision(commands):
    for words in commands:
        if os.path.basename(words[0]) != "git":
            continue
        arguments = push_arguments(words)
        if arguments is None:
            continue
        verdict = push_verdict(arguments)
        if verdict:
            return verdict
    return None


def thread_decision(tool_input, environ=None):
    if is_gate(environ):
        return None
    if GATE_INSTANCE in json.dumps(tool_input, sort_keys=True):
        return deny(THREAD_REASON)
    return None


def decision(command, environ=None):
    commands = list(real_commands(command))
    return merge_decision(commands, environ) or push_decision(commands)


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
