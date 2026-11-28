#!/usr/bin/env python3
"""Deny rules for shell commands that `permissions.deny` cannot express (mac-ops #530).

PreToolUse hook for Claude Code (Bash, and the Read, Edit, Write, MultiEdit,
NotebookEdit, Grep and Glob tools for the Ascend tree), and the single
implementation the pi deny guards call for every bash command. The rules are read from the structure of
the command (the simple commands the shell would run), never from its text,
so a PR body, an `hc` message or a heredoc that mentions a rule is not a
command that breaks it:

Each rule belongs to a family, and FAMILY_MODES (from deny-rules.json) says
whether the family asks the owner or is denied outright:

- ask: `gh pr merge` outside personal repos (github.com/shyamsivakumar/*), a push to main or master of a repo outside github.com/shyamsivakumar/,
  secret values printed by gcloud or heroku (`gcloud secrets versions access`,
  `heroku config`, `config:get`, a `--format` that shows a secret), and commands
  that touch the Ascend tree from a session that did not start there. Every
  other gcloud, bq and heroku command runs.
  Claude Code shows the owner a prompt; a headless run turns the ask into a
  deny by itself. When the permission mode is not a known interactive one
  (bypassPermissions, dontAsk, anything new) no prompt is guaranteed, so the
  answer is deny. An internal error on a command that names a guarded tool is
  a deny ("guard error").
- deny, even with approval: a push to main or master of a personal repo (github.com/shyamsivakumar/*) or
  whose remote cannot be resolved, force-push in any form, remote and cloud deletes
  (including `gh api`, `curl` and `http` DELETE requests), removal commands
  aimed at secret files or the Ascend tree, and `git stash` in any form
  except `list` and `show`.

A session whose project dir (CLAUDE_PROJECT_DIR) is inside the Ascend tree gets
no Ascend check. Every ask and deny is appended to the audit log.

Exit 0 with a decision blocks or asks; exit 0 with no output allows.
Installed by scripts/install_deny_rules.py; do not edit the installed copy.
"""

import glob
import json
import os
import re
import subprocess
import sys
import time

PREFIX = "mac-ops deny rules (#530): "
MERGE_REASON = "gh pr merge needs the owner's approval; merges belong to the lane and the merge pass"
FORCE_REASON = "force-push in any form is denied"
DELETE_REASON = "remote and cloud deletes are denied"
PROTECTED_REASON = "pushing to main or master needs the owner's approval; push a task branch instead"
PERSONAL_REASON = (
    "pushing to main or master of a personal repo (github.com/shyamsivakumar/*) is denied, "
    "and so is a push whose remote cannot be resolved; push a task branch instead"
)
NO_DESTINATION_REASON = (
    "this push names no explicit destination branch; name the branch, "
    "for example `git push -u origin <task-branch>`"
)
STASH_REASON = "git stash shares one stash list across every worktree of a repository, so concurrent sessions pop each other's edits; use a throwaway worktree or a commit on your task branch instead"
STASH_READ_ONLY = {"list", "show"}
PROTECTED = {"main", "master"}
REMOTE_NAME_RE = re.compile(r"[\w.-]+")
REMOTE_URL_RE = re.compile(
    r"(?:(?:https?|ssh|git)://(?:[^/]*@)?(?P<host>[^/:@]+)(?::\d*)?/?|[^@/:\s]+@(?P<scp_host>[^/:@]+):)/?(?P<owner>[^/]+)/",
    re.I,
)
PERSONAL_HOST = "github.com"
PERSONAL_OWNER = "shyamsivakumar"
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
GH_VALUE_OPTIONS = {"-R", "--repo", "--hostname"}
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
    "xargs",
}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
COMMAND_NAMES = WRAPPERS | SHELLS | {"git", "gh", "eval", "rm", "rmdir", "unlink", "trash", "find"}
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}"}
SEPARATORS = ";&|\n()`"
MAX_NESTING = 4
ASCEND_ROOTS = ["~/Code/slash-eureka"]
SECRET_DIRS = ["~/.ssh"]
SECRET_FILE_RE = "(?:^|/)\\.(?:env(?:\\.[\\w.-]+)?|netrc|npmrc|pypirc)$|(?:^|/)auth\\.json$|(?:^|/)id_(?:rsa|dsa|ed25519|ecdsa)(?:\\.[\\w-]+)*$|(?:^|/)[\\w.-]+\\.(?:pem|key)$|(?:^|/)credentials(?:\\.json)?$|(?:^|/)(?:[\\w.-]*[._-])?tokens?(?:\\.[\\w-]+)*\\.(?:json|txt|ya?ml)$|(?:^|/)\\.ssh(?:/|$)"
FAMILY_MODES = {"merge": "ask", "push_protected": "ask", "push_personal": "deny", "secret_files": "deny", "cloud_secret": "ask", "ascend": "ask", "force_push": "deny", "remote_delete": "deny", "protected_removal": "deny", "push_destination": "deny", "stash": "deny"}
ASCEND_REASON = "commands that touch ~/Code/slash-eureka (Ascend) need the owner's approval"
SECRET_REASON = "commands on secret files (.env, auth.json, keys, tokens, ~/.ssh) are denied"
CLOUD_REASON = "printing secret values with gcloud or heroku needs the owner's approval"
REMOVAL_REASON = "removing secret files or anything under ~/Code/slash-eureka is denied"
DIRECTORY_CHANGERS = {"cd", "pushd"}
READ_ONLY_COMMANDS = {"ls"} | DIRECTORY_CHANGERS
REMOVERS = {"rm", "rmdir", "unlink", "trash"}
EXEC_FLAGS = {"-exec", "-execdir", "-ok", "-okdir"}
GLOB_CHARS = r"[*?\[{]"
CLOUD_CLIS = {"gcloud", "bq", "heroku"}
INTERACTIVE_MODES = {"default", "acceptEdits", "plan", "auto"}
SECRET_FORMAT_RE = r"(?i)payload|secret|password|token|private_key|\bkey\b"
DELETE_TOOLS = {"curl", "http", "https"}
GUARDED_TEXT_RE = r"\b(?:gh|git|gcloud|bq|heroku|curl|http|rm|rmdir|unlink|trash|find)\b|slash-eureka|\.env|\.ssh|auth\.json"
COMMAND_SHOWN = 300
PROGRAM_RE = re.compile(r"[A-Za-z0-9_.+-]{1,40}")
PATH_KEYS = ("file_path", "notebook_path", "path")
PATH_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Grep", "Glob"}
AUDIT_PATH = "~/.local/state/mac-ops/deny-audit.jsonl"
COMMAND_LIMIT = 200


def verdict(decision, reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
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


def gh_action(words):
    """The group and action of a gh command, skipping global options such as `-R x/y`."""
    positionals, i = [], 1
    while i < len(words) and len(positionals) < 2:
        if words[i].startswith("-"):
            i += 2 if words[i] in GH_VALUE_OPTIONS else 1
        else:
            positionals.append(words[i])
            i += 1
    return positionals


def gh_repo_option(words):
    for i, word in enumerate(words):
        if word.startswith("--repo="):
            return word.split("=", 1)[1]
        if word in {"-R", "--repo"}:
            return "".join(words[i + 1 : i + 2])
    return None


def gh_repo_personal(words, here):
    """True when `-R/--repo` names a github.com/shyamsivakumar/ repo, or, without it, every push URL of `origin` does."""
    value = gh_repo_option(words)
    if value is None:
        return remote_personal("origin", here)
    if "://" in value or "@" in value:
        return personal_url(value) is True
    owner_first = value.count("/") == 1
    return personal_url("https://" + ("github.com/" if owner_first else "") + value) is True


def gh_findings(words, here):
    action = gh_action(words)
    if action == ["pr", "merge"]:
        return [] if gh_repo_personal(words, here) else [("merge", MERGE_REASON)]
    if action in (["repo", "delete"], ["release", "delete"]):
        return [("remote_delete", DELETE_REASON)]
    return []


def delete_method(words):
    for i, word in enumerate(words):
        if word in {"-X", "--method", "--request"} and words[i + 1 : i + 2]:
            if words[i + 1].upper() == "DELETE":
                return True
        elif word.upper() in {"-XDELETE", "--METHOD=DELETE", "--REQUEST=DELETE"}:
            return True
    return False


def api_findings(name, words):
    is_api = name in DELETE_TOOLS or (name == "gh" and gh_action(words)[:1] == ["api"])
    deletes = delete_method(words) or (name in {"http", "https"} and "DELETE" in words)
    return [("remote_delete", DELETE_REASON)] if is_api and deletes else []


def cloud_findings(name, words):
    rest = words[1:]
    positionals = [word for word in rest if not word.startswith("-")]
    formats = [w.split("=", 1)[1] for w in rest if w.startswith("--format=")]
    formats += [rest[i + 1] for i, w in enumerate(rest[:-1]) if w == "--format"]
    prints_secret = (
        (name == "gcloud" and {"secrets", "access"} <= set(positionals))
        or (name == "gcloud" and any(re.search(SECRET_FORMAT_RE, f) for f in formats))
        or (name == "heroku" and positionals[:1] in (["config"], ["config:get"]))
    )
    deletes = (
        (name == "gcloud" and "delete" in rest)
        or (name == "bq" and "rm" in rest)
        or (name == "heroku" and any("destroy" in word for word in rest))
    )
    found = [("cloud_secret", CLOUD_REASON)] * prints_secret
    return found + [("remote_delete", DELETE_REASON)] * deletes


def git_arguments(words):
    """The subcommand and its arguments, skipping global options such as `-C dir`."""
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in GIT_VALUE_OPTIONS else 1
    return (words[i], words[i + 1 :]) if i < len(words) else ("", [])


def push_arguments(words):
    subcommand, args = git_arguments(words)
    return args if subcommand == "push" else None


def stash_findings(args):
    if args and args[0] in STASH_READ_ONLY:
        return []
    return [("stash", STASH_REASON)]


def destination(token):
    ref = token.lstrip("+")
    ref = ref.split(":", 1)[1] if ":" in ref else ref
    return re.sub(r"^(?:refs/)?(?:heads/)?", "", ref)


def personal_url(url):
    """True for a github.com/shyamsivakumar/ URL, False for another host or owner, None when unparsable."""
    match = REMOTE_URL_RE.match(url)
    if not match:
        return None
    host = (match["host"] or match["scp_host"]).lower()
    return host == PERSONAL_HOST and match["owner"].lower() == PERSONAL_OWNER


def push_urls(repo, here):
    if not REMOTE_NAME_RE.fullmatch(repo):
        return [repo]
    done = subprocess.run(
        ["git", "-C", here, "remote", "get-url", "--push", "--all", repo],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return done.stdout.split() if done.returncode == 0 else []


def remote_elsewhere(repo, here):
    """True only when every push URL of the remote parses and none is github.com/shyamsivakumar/."""
    urls = push_urls(repo, here)
    return bool(urls) and all(personal_url(url) is False for url in urls)


def remote_personal(repo, here):
    """True only when the remote resolves and every push URL is github.com/shyamsivakumar/."""
    urls = push_urls(repo, here)
    return bool(urls) and all(personal_url(url) is True for url in urls)


def current_branch(here):
    done = subprocess.run(
        ["git", "-C", here, "symbolic-ref", "--short", "-q", "HEAD"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def git_directory(words, here):
    i = 1
    while i < len(words) and words[i].startswith("-"):
        if words[i] == "-C" and i + 1 < len(words):
            here = resolve(words[i + 1], here)
        i += 2 if words[i] in GIT_VALUE_OPTIONS else 1
    return here


def push_findings(args, here):
    """The first positional is the repository unless `--repo` names it; the rest are refspecs."""
    positionals, forced, deleting, bulk, repo_option, options_done, i = (
        [],
        False,
        False,
        False,
        False,
        False,
        0,
    )
    repo = ""
    while i < len(args):
        arg = args[i]
        if not options_done and arg == "--":
            options_done = True
        elif not options_done and arg.startswith("-"):
            name = arg.split("=", 1)[0]
            short = bool(re.fullmatch(r"-[A-Za-z]+", arg))
            forced = forced or name.startswith("--force") or (short and "f" in arg)
            deleting = deleting or name == "--delete" or (short and "d" in arg)
            bulk = bulk or name in BULK_FLAGS
            if name in PUSH_VALUE_OPTIONS:
                repo_option = repo_option or name == "--repo"
                if name == "--repo":
                    repo = arg.split("=", 1)[1] if "=" in arg else "".join(args[i + 1 : i + 2])
                i += "=" not in arg
        else:
            positionals.append(arg)
        i += 1
    refspecs = positionals if repo_option else positionals[1:]
    repo = repo or "".join(positionals[:1])
    found = []
    if forced or any(token.startswith("+") and len(token) > 1 for token in positionals):
        found.append(("force_push", FORCE_REASON))
    if deleting or any(token.startswith(":") and len(token) > 1 for token in refspecs):
        found.append(("remote_delete", DELETE_REASON))
    if bulk or not refspecs or any(token == ":" or "*" in token for token in refspecs):
        return found + [("push_destination", NO_DESTINATION_REASON)]
    for token in refspecs:
        target = destination(token)
        if target in {"HEAD", "@"}:
            target = current_branch(here)
        if target == "" or "$" in target or "`" in target:
            return found + [("push_destination", NO_DESTINATION_REASON)]
        if target in PROTECTED:
            if remote_elsewhere(repo, here):
                found.append(("push_protected", PROTECTED_REASON))
            else:
                found.append(("push_personal", PERSONAL_REASON))
            break
    return found


def in_ascend(path):
    return in_roots(path, ASCEND_ROOTS)


def resolve(word, here):
    return os.path.normpath(
        os.path.join(here, os.path.expandvars(os.path.expanduser(word)))
    )


def operands(words):
    """Words that can name a path, quoted or escaped spaces kept whole: options with `=` give their value, other options are skipped."""
    found = []
    for word in words[1:]:
        word = word.lstrip("<>")
        if word.startswith("-"):
            word = word.split("=", 1)[1] if "=" in word else ""
        if word:
            found.append(word)
    return found


def in_roots(path, roots):
    real = os.path.realpath(path)
    for root in roots:
        root = os.path.realpath(os.path.expanduser(root))
        if real == root or real.startswith(root + os.sep):
            return True
    return False


def protected_path(path, ascend_session):
    """A secret file, a secret directory, or (outside an Ascend session) the Ascend tree."""
    secret = any(re.search(SECRET_FILE_RE, p) for p in (path, os.path.realpath(path)))
    return secret or in_roots(path, SECRET_DIRS) or (not ascend_session and in_ascend(path))


def brace_expand(word):
    found = re.search(r"\{([^{}]*,[^{}]*)\}", word)
    if not found:
        return [word]
    head, tail = word[: found.start()], word[found.end() :]
    return [x for alt in found.group(1).split(",") for x in brace_expand(head + alt + tail)]


def literal_directory(path):
    prefix = re.split(GLOB_CHARS, path, maxsplit=1)[0]
    return prefix if prefix.endswith("/") else os.path.dirname(prefix)


def removal_target_protected(word, here, ascend_session):
    """A removal operand is protected when it is, when its literal directory is, or when any file its pattern matches now is."""
    path = resolve(word, here)
    if protected_path(path, ascend_session):
        return True
    if not re.search(GLOB_CHARS, path):
        return False
    if protected_path(literal_directory(path), ascend_session):
        return True
    return any(
        protected_path(match, ascend_session)
        for expanded in brace_expand(path)
        for match in glob.glob(expanded, recursive=False)
    )


def find_start_directories(words):
    starts = []
    for word in words[1:]:
        if word.startswith("-") and word not in {"-H", "-L", "-P"}:
            break
        if word in {"(", "!", ")", "-H", "-L", "-P"}:
            continue
        starts.append(word)
    return starts


def find_protected(words, here, ascend_session):
    """`find <dir> ... -delete` removes under <dir>: protected when <dir> is, or holds a protected file at the top level."""
    for word in find_start_directories(words):
        if removal_target_protected(word, here, ascend_session):
            return True
        directory = resolve(word, here)
        if os.path.isdir(directory) and any(
            protected_path(os.path.join(directory, entry), ascend_session)
            for entry in os.listdir(directory)
        ):
            return True
    return False


def removal_command(words):
    name = os.path.basename(words[0])
    if name in REMOVERS:
        return True
    return name == "find" and (
        "-delete" in words
        or any(
            words[i] in EXEC_FLAGS and os.path.basename(words[i + 1]) in REMOVERS
            for i in range(len(words) - 1)
        )
    )


def path_findings(words, here, ascend_session):
    name = os.path.basename(words[0])
    removes = removal_command(words)
    paths = [resolve(word, here) for word in operands(words)]
    secret = any(re.search(SECRET_FILE_RE, path) for path in paths)
    ascend = not ascend_session and any(in_ascend(path) for path in paths)
    if removes and (
        secret
        or ascend
        or (name == "find" and find_protected(words, here, ascend_session))
        or (name != "find" and any(removal_target_protected(w, here, ascend_session) for w in operands(words)))
    ):
        return [("protected_removal", REMOVAL_REASON)]
    found = []
    if secret and name not in READ_ONLY_COMMANDS:
        found.append(("secret_files", SECRET_REASON))
    if ascend:
        found.append(("ascend", ASCEND_REASON))
    return found


def command_findings(commands, cwd, ascend_session):
    """Every (family, reason) the commands trigger; a `cd` moves the directory later commands run in."""
    here = cwd or os.getcwd()
    found = []
    if not ascend_session and in_ascend(here):
        found.append(("ascend", ASCEND_REASON))
    for words in commands:
        name = os.path.basename(words[0])
        found += path_findings(words, here, ascend_session)
        found += api_findings(name, words)
        if name == "gh":
            found += gh_findings(words, here)
        elif name in CLOUD_CLIS:
            found += cloud_findings(name, words)
        elif name == "git":
            subcommand, args = git_arguments(words)
            if subcommand == "push":
                found += push_findings(args, git_directory(words, here))
            elif subcommand == "rm":
                found += path_findings(["rm", *args], here, ascend_session)
            elif subcommand == "stash":
                found += stash_findings(args)
        targets = operands(words)
        if name in DIRECTORY_CHANGERS and targets:
            here = resolve(targets[0], here)
    return found


def decide(command, cwd, project_dir, permission_mode):
    ascend_session = bool(project_dir) and in_ascend(project_dir)
    found = command_findings(list(real_commands(command)), cwd, ascend_session)
    return conclude(found, command, cwd, permission_mode)


def glob_base(pattern):
    prefix = re.split(r"[*?\[{]", pattern, maxsplit=1)[0]
    return prefix if prefix == pattern or prefix.endswith("/") else os.path.dirname(prefix)


def tool_paths(tool_name, tool_input, cwd):
    given = [str(tool_input[key]) for key in PATH_KEYS if tool_input.get(key)]
    if tool_input.get("pattern") and tool_name == "Glob":
        given.append(glob_base(str(tool_input["pattern"])))
    if not given and tool_name in {"Grep", "Glob"}:
        given.append(cwd or os.getcwd())
    here = cwd or os.getcwd()
    return [os.path.join(here, os.path.expandvars(os.path.expanduser(path))) for path in given]


def decide_tool(tool_name, tool_input, cwd, project_dir, permission_mode):
    """File tools touching the Ascend tree ask; the realpath makes symlinks and `..` count."""
    shown = tool_label(tool_name, tool_input)
    ascend_session = bool(project_dir) and in_ascend(project_dir)
    hits = [] if ascend_session else [p for p in tool_paths(tool_name, tool_input, cwd) if in_ascend(p)]
    found = [("ascend", ASCEND_REASON)] if hits else []
    outcome = conclude(found, shown, cwd, permission_mode)
    if outcome:
        outcome["target"] = os.path.realpath(hits[0])
    return outcome


def tool_label(tool_name, tool_input):
    """The tool name and its path arguments; file contents and edit text are never part of it."""
    paths = [str(tool_input[k]) for k in PATH_KEYS + ("pattern",) if tool_input.get(k)]
    return " ".join([tool_name, *paths])


def conclude(found, shown, cwd, permission_mode):
    interactive = permission_mode is None or permission_mode in INTERACTIVE_MODES
    if not found:
        return None
    hard = [f for f in found if FAMILY_MODES[f[0]] == "deny"]
    chosen = hard or found
    families = list(dict.fromkeys(family for family, _ in chosen))
    reasons = list(dict.fromkeys(reason for _, reason in chosen))
    if hard:
        decision, note = "deny", "denied even with approval"
    elif not interactive:
        decision, note = (
            "deny",
            f"no approval prompt is available in {permission_mode} mode",
        )
    else:
        decision, note = "ask", "approve it to run the command"
    reason = f"[{', '.join(families)}] {'; '.join(reasons)} ({note})"
    if decision == "ask":
        reason += f"\ncommand: {shown[:COMMAND_SHOWN]}\ncwd: {cwd or os.getcwd()}"
    return {"decision": decision, "families": families, "reason": reason}


def redact_path(path):
    return "[secret]" if re.search(SECRET_FILE_RE, path) else path


def program(command):
    """The program name of the first command. Nothing after it is kept: arguments can hold credentials."""
    for words in real_commands(command):
        name = os.path.basename(words[0])
        return name if PROGRAM_RE.fullmatch(name) else "unknown"
    return "unknown"


def audit(outcome, command, payload, tool_name):
    line = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime": os.environ.get("MAC_OPS_DENY_RUNTIME", "claude"),
        "session_id": payload.get("session_id"),
        "tool": tool_name,
        "family": ",".join(outcome["families"]),
        "decision": outcome["decision"],
    }
    try:
        if tool_name == "Bash":
            line["program"] = program(command)
        else:
            line["target"] = redact_path(outcome.get("target", ""))[:COMMAND_LIMIT]
        path = os.path.expanduser(AUDIT_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as log:
            log.write(json.dumps(line) + "\n")
    except (OSError, ValueError):
        pass


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    if tool_name == "ProgramName":
        print(program(str(tool_input.get("command") or "")))
        return 0
    if tool_name != "Bash" and tool_name not in PATH_TOOLS:
        return 0
    command = str(tool_input.get("command") or "") if tool_name == "Bash" else tool_label(tool_name, tool_input)
    try:
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        mode = payload.get("permission_mode")
        if tool_name == "Bash":
            outcome = decide(command, payload.get("cwd"), project_dir, mode)
        else:
            outcome = decide_tool(tool_name, tool_input, payload.get("cwd"), project_dir, mode)
    except Exception:
        if not re.search(GUARDED_TEXT_RE, command):
            return 0
        outcome = {"decision": "deny", "families": ["guard_error"], "reason": "guard error: the command could not be classified, so it is denied"}
    if outcome:
        audit(outcome, command, payload, tool_name)
        print(json.dumps(verdict(outcome["decision"], outcome["reason"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
