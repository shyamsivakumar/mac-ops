"""The changed paths that decide a pull request waits for Shyam.

Shyam's rule: a prompt, skill or playbook change never auto-merges. On
2026-11-17 the gate merged such a pull request (mac-ops #542) because nothing
in the gate path looked at the paths it changed. The list lives here once,
and both the gate brief builder and the lane driver read it, so the two
cannot disagree about which pull requests stop at the verdict.

A path is prompt text when its file name is one of the prompt files or when
one of its directories is a prompt directory. The match is by path, never by
the words in the diff or the ticket.
"""

# File names, compared without case. The coordinator's agent rules, the bar,
# the brief and the answer format the gate reads, the playbook, the reviewer
# prompt and every skill file.
PROMPT_FILE_NAMES = (
    "agent-rules.md",
    "answer_format.py",
    "gate_bar.py",
    "gate_policy.py",
    "playbook.md",
    "code-reviewer.md",
    "skill.md",
)
# Directories that hold prompt text: any path under them is prompt text.
PROMPT_DIRS = ("skills", "prompts")


def is_prompt_path(path):
    """True when one changed path carries prompt, skill or playbook text."""
    parts = [part.lower() for part in str(path or "").split("/") if part]
    if not parts:
        return False
    if parts[-1] in PROMPT_FILE_NAMES:
        return True
    return any(part in PROMPT_DIRS for part in parts[:-1])


# The three answers a changed-path read gives. UNKNOWN is a list GitHub could
# not give, and it never reads as CLEAR: a clear answer authorizes the merge
# the gate brief orders for an ordinary pull request.
HOLD, CLEAR, UNKNOWN = "hold", "clear", "unknown"


def entry_paths(entry):
    """Both names of one changed file of a pull request.

    A rename carries the name it left as `previous_filename`. Moving
    `prompts/reviewer.md` to `archive/reviewer.md` removed prompt text, so
    the name it left is prompt text too, and a read that checks only the new
    name would let that pull request merge.
    """
    if not isinstance(entry, dict):
        return []
    return [path for path in (entry.get("filename"), entry.get("previous_filename")) if path]


def entries_paths(entries):
    """Every path a list of changed-file entries names, old names included."""
    return [path for entry in entries or () for path in entry_paths(entry)]


def prompt_change(paths):
    """True when one known path list carries prompt, skill or playbook text.

    A list GitHub could not give is not a path list, so it raises here rather
    than reading as clear. Callers that may not have a list use `prompt_scan`.
    """
    if paths is None:
        raise ValueError("a path list GitHub could not give is unknown, not clear; use prompt_scan")
    return any(is_prompt_path(path) for path in paths)


def list_is_complete(entries, changed_files):
    """False when the changed-file list may leave a file out.

    GitHub's pull-request files endpoint returns at most 3,000 files, so a
    list shorter than the pull request's own changed-file count may have
    dropped the one prompt file. A count that is not known cannot be
    compared, and only a known count can show the list is short.
    """
    if not isinstance(changed_files, int):
        return True
    return len(entries or ()) >= changed_files


def prompt_scan(paths):
    """HOLD, CLEAR or UNKNOWN for one changed-path list.

    An unreadable list (None) is UNKNOWN, never CLEAR: its caller retries or
    defers the gate, because CLEAR lets the pull request merge.
    """
    if paths is None:
        return UNKNOWN
    return HOLD if prompt_change(paths) else CLEAR
