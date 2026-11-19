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

import gh_gateway

PROOF_NAME = "check-proof.md"
DEFAULT_PROOF = f"evidence/{PROOF_NAME}"

FOUND = "found"
MISSING = "missing"
UNREADABLE = "unreadable"


def path_for(key, issue):
    """The proof file path of one ticket.

    The path carries the ticket key and number, so two pull requests that
    are open at the same time never write the same file. A pull request
    with no ticket has no ticket path, so it uses the builder's default
    path, the one the check writes when it is given no other.
    """
    if not key or issue is None:
        return DEFAULT_PROOF
    return f"evidence/{key}-{issue}/{PROOF_NAME}"


def fetch(repo, path, head):
    """Read the proof file at head.

    The state says what the read found: the file (`found`), no such file
    (`missing`), or a read that failed (`unreadable`). A read that failed
    is not a confirmed absence, so the two are never the same answer. A
    file that exists but carries nothing is a failed read too: only a
    confirmed 404 is a missing file.
    """
    if not path:
        return MISSING, None
    try:
        run = gh_gateway.run(["gh", "api", f"repos/{repo}/contents/{path}?ref={head}"],
                             timeout=60)
    except subprocess.TimeoutExpired:
        return UNREADABLE, "the read timed out"
    except OSError as exc:
        return UNREADABLE, str(exc)
    if run.returncode:
        if "404" in run.stderr or "Not Found" in run.stderr:
            return MISSING, None
        return UNREADABLE, run.stderr.strip().splitlines()[0] if run.stderr.strip() else "GitHub returned an error"
    try:
        blob = json.loads(run.stdout)
    except ValueError:
        return UNREADABLE, "GitHub returned no JSON"
    if "content" not in blob:
        return UNREADABLE, "GitHub returned no content for the file"
    if blob.get("encoding") not in (None, "base64"):
        return UNREADABLE, "GitHub returned a file this reader cannot decode"
    try:
        text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
    except (ValueError, UnicodeDecodeError):
        return UNREADABLE, "GitHub returned a file this reader cannot decode"
    if not text.strip():
        return UNREADABLE, "the file is empty"
    return FOUND, text


def section(state, text, path):
    """The brief lines that carry the proof file to the reviewer."""
    if state == FOUND:
        return (f"Proof file `{path}` at this head:\n\n```\n{(text or '').strip()}\n```\n\n"
                "Read it before the diff. Every check it lists must be `passed`; a `failed` or "
                "`not run` check is a finding. It names the commit it checked: confirm that "
                "commit is this head or an ancestor of it, and that the diff between them only "
                "adds the proof file.")
    if state == UNREADABLE:
        return (f"Proof file `{path}` could not be read ({text}). That is a failed read, not a "
                "confirmed absence: say so in one line, and treat the checks as unproven.")
    return (f"Proof file: this pull request carries none at `{path}`. Say so in one line; "
            "a missing proof file alone does not block.")
