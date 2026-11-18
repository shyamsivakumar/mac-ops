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


def prompt_change(paths):
    """True when any changed path is prompt text.

    A list GitHub could not give (None) is not a prompt change: the rule only
    ever adds a hold to a pull request whose paths it can read, so an
    unreadable list never blocks a merge.
    """
    return any(is_prompt_path(path) for path in paths or ())
