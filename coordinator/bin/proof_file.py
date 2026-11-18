"""The proof file a pull request carries, read for the gate brief.

The builder's check writes a proof file: every check it ran, the command
that ran it, and whether that check passed, failed or did not run. The
builder commits the file with the change. The gate brief carries the file
to the reviewer, so the reviewer reads the record of the checks instead of
the builder's one claimed line in the pull request body.
"""
import base64
import json
import subprocess

PROOF_NAME = "check-proof.md"


def path_for(key, issue):
    """The proof file path of one ticket, or None when there is no ticket.

    The path carries the ticket key and number, so two pull requests that
    are open at the same time never write the same file.
    """
    if not key or issue is None:
        return None
    return f"evidence/{key}-{issue}/{PROOF_NAME}"


def fetch(repo, path, head):
    """Return the text of the proof file at head, or None when there is none.

    A pull request that carries no proof file is not an error: the brief
    says so and the reviewer decides what a missing record means.
    """
    if not path:
        return None
    try:
        run = subprocess.run(["gh", "api", f"repos/{repo}/contents/{path}?ref={head}"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if run.returncode:
        return None
    try:
        blob = json.loads(run.stdout)
    except ValueError:
        return None
    content = blob.get("content")
    if not content:
        return None
    try:
        return base64.b64decode(content).decode("utf-8", "replace")
    except (ValueError, UnicodeDecodeError):
        return None


def section(text, path):
    """The brief lines that carry the proof file to the reviewer."""
    if not text:
        where = f" at `{path}`" if path else ""
        return (f"Proof file: this pull request carries none{where}. Say so in one line; "
                "a missing proof file alone does not block.")
    return (f"Proof file `{path}` at this head:\n\n```\n{text.strip()}\n```\n\n"
            "Read it before the diff. Every check it lists must be `passed`; a `failed` or "
            "`not run` check is a finding. It names the commit it checked: confirm that "
            "commit is this head or an ancestor of it, and that the diff between them only "
            "adds the proof file.")
