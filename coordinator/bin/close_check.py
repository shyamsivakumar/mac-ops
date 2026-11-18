"""The close checklist: what the coordinator reads before it closes a ticket.

Four items, each answered from the merged pull request and its ticket:

1. scope: every changed file is inside the ticket's stated scope.
2. proof file: the pull request carries a proof file (MO-1065).
3. checks: every check the proof file lists is `passed`.
4. cost note: when the MO-1068 cost report exists, the pull request body
   carries a cost note.

A failing item sends the work back to its builder with the failing item
named, and leaves the ticket open. The checklist reads the merged pull
request through `gh`, so it answers from the same head the gate reviewed.
"""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys

# The modules below live next to this file. A caller that loads this file
# by path does not put that directory on the path.
_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

import proof_file

GH_TIMEOUT = 60
PROOF_NAME = proof_file.PROOF_NAME
COST_REPORT = "evidence/MO-1068/cost-report.md"
COST_NOTE = re.compile(r"(?im)^[ \t>*-]*(cost|cost note|kosten)[ \t]*[:\-]")
TICKET_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9]*)-(\d+)\b")
ISSUE_REF = re.compile(r"(?:refs|fixes|closes|resolves)[ \t]+#(\d+)", re.IGNORECASE)
# A token is a whole path, never the tail of a longer one: the part of
# `~/Code/inbox/note.md` after the `~` or the `/` is not a path in this
# repository, so the character before a token may not continue a path.
_NOT_IN_PATH = r"(?<![A-Za-z0-9_.*~/\\-])"
PATH_TOKEN = re.compile(_NOT_IN_PATH + r"[A-Za-z0-9_.*-]+(?:/[A-Za-z0-9_.*-]+)+")
FILE_TOKEN = re.compile(_NOT_IN_PATH + r"[A-Za-z0-9_.*-]+\.(?:py|js|mjs|cjs|json|md|sh|ts|tsx|jsx|yml|yaml|cfg|toml|txt|html|css)\b")

PASS = "pass"
FAIL = "fail"
SKIPPED = "skipped"


def scope_tokens(body):
    """The files and paths the ticket names.

    A ticket names its area in prose, so the tokens are the path-like
    words in the body: a path with a slash, or a file name with an
    extension.
    """
    tokens = set()
    for match in PATH_TOKEN.finditer(body or ""):
        token = match.group(0).strip(".,;:()[]")
        if token and "://" not in token:
            tokens.add(token)
    for match in FILE_TOKEN.finditer(body or ""):
        tokens.add(match.group(0).strip(".,;:()[]"))
    return tokens


def in_scope(path, tokens, changed=()):
    """Is one changed file inside the ticket's stated scope?

    A file is in scope when the ticket names it, names a directory that
    holds it, or names a glob that matches it. Evidence travels with the
    change, so a file under `evidence/` is in scope, and a test comes with
    the change, so a file under `tests/` is in scope.
    """
    base = os.path.basename(path)
    if path.startswith("evidence/"):
        return True, f"{path} is evidence that travels with the change"
    if path.startswith("tests/"):
        return True, f"{path} is a test that comes with the change"
    for token in tokens:
        if any(char in token for char in "*?["):
            if fnmatch.fnmatch(path, token) or fnmatch.fnmatch(base, token):
                return True, f"{path} matches {token}"
            continue
        if "/" in token:
            if path == token or path.startswith(token.rstrip("/") + "/"):
                return True, f"{path} is under {token}"
        elif base == token:
            return True, f"{path} is named by {token}"
    if path.startswith("tests/"):
        return True, f"{path} is a test that comes with the change"
    return False, ""


def names_a_file(tokens):
    """Does the ticket name a file, or a glob that can hold one?

    A directory token and a reference outside the repository (another
    repository's name, a home path) can only widen what is in scope, so a
    ticket that names only those cannot say whether a diff left its scope: it
    is skipped, not passed and not failed.
    """
    return any("*" in token or "?" in token or "[" in token
               or FILE_TOKEN.fullmatch(token) for token in tokens)


def item_scope(body, files):
    """Item 1: the diff stays inside the ticket's stated scope."""
    tokens = scope_tokens(body)
    if not tokens or not names_a_file(tokens):
        return {"item": "scope", "status": SKIPPED,
                "detail": "the ticket names no file in this repository, so the scope cannot be judged"}
    outside = [path for path in files if not in_scope(path, tokens, files)[0]]
    if outside:
        return {"item": "scope", "status": FAIL,
                "detail": "outside the ticket's stated scope: " + ", ".join(sorted(outside))}
    return {"item": "scope", "status": PASS,
            "detail": "every changed file is inside the ticket's stated scope"}


def item_proof(state, path):
    """Item 2: the pull request carries a proof file."""
    if state == proof_file.FOUND:
        return {"item": "proof file", "status": PASS, "detail": f"{path} is present"}
    if state == proof_file.MISSING:
        return {"item": "proof file", "status": FAIL,
                "detail": f"the pull request carries no proof file at {path}"}
    return {"item": "proof file", "status": FAIL,
            "detail": f"the proof file at {path} could not be read, so the checks are unproven"}


def proof_rows(text):
    """Every check the proof file lists, with the result it recorded."""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        name = cells[0]
        if not name or set(name) <= set("-: "):
            continue
        if name.lower() == "check":
            continue
        rows.append((name, cells[2].lower()))
    return rows


def item_checks(state, text):
    """Item 3: every check the proof file lists passed."""
    if state != proof_file.FOUND:
        return {"item": "checks", "status": SKIPPED, "detail": "there is no proof file to read"}
    rows = proof_rows(text)
    if not rows:
        return {"item": "checks", "status": FAIL, "detail": "the proof file lists no check"}
    failed = [f"{name} ({result})" for name, result in rows if result != "passed"]
    if failed:
        return {"item": "checks", "status": FAIL,
                "detail": "the proof file lists a check that is not passed: " + ", ".join(failed)}
    return {"item": "checks", "status": PASS,
            "detail": f"every one of the {len(rows)} checks the proof file lists passed"}


def item_cost(body, report_exists):
    """Item 4: a cost note, once the MO-1068 cost report exists."""
    if not report_exists:
        return {"item": "cost note", "status": SKIPPED,
                "detail": f"the MO-1068 cost report ({COST_REPORT}) does not exist yet"}
    if COST_NOTE.search(body or ""):
        return {"item": "cost note", "status": PASS, "detail": "the pull request body carries a cost note"}
    return {"item": "cost note", "status": FAIL,
            "detail": "the cost report exists, but the pull request body carries no cost note"}


def checklist(body, pr_body, files, proof_state, proof_text, proof_path, report_exists):
    """The four items, in the order the checklist reads them."""
    return [
        item_scope(body, files),
        item_proof(proof_state, proof_path),
        item_checks(proof_state, proof_text),
        item_cost(pr_body, report_exists),
    ]


def failures(items):
    """The items that fail."""
    return [item for item in items if item["status"] == FAIL]


def report(items, target=""):
    """The checklist as text, one line per item."""
    lines = [f"{item['item']}: {item['status']} - {item['detail']}" for item in items]
    failed = failures(items)
    lines.append(f"RESULT: {'FAIL' if failed else 'PASS'}{(' ' + target) if target else ''}")
    return "\n".join(lines)


def gh_json(args, timeout=GH_TIMEOUT):
    """Run `gh` and read its JSON."""
    try:
        result = subprocess.run(["gh"] + list(args), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"gh {' '.join(args[:2])} timed out after {timeout}s")
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def gh_ok(args, timeout=GH_TIMEOUT):
    """Did `gh` succeed? A reader that fails is not a confirmed absence."""
    try:
        result = subprocess.run(["gh"] + list(args), capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def ticket_key(title):
    """The ticket key from its title, `MO-1077 · name` gives `MO`."""
    match = TICKET_KEY.match(title or "")
    return match.group(1) if match else None


def issue_of(body):
    """The issue number a pull request body refers to."""
    match = ISSUE_REF.search(body or "")
    return int(match.group(1)) if match else None


def run_check(repo, pr, issue=None):
    """Run the checklist on a merged pull request."""
    pull = gh_json(["pr", "view", str(pr), "-R", repo, "--json",
                    "state,headRefOid,body,mergeCommit,files,title"])
    merge = (pull.get("mergeCommit") or {}).get("oid") or pull["headRefOid"]
    files = [entry.get("path") for entry in pull.get("files") or [] if entry.get("path")]
    number = issue if issue is not None else issue_of(pull.get("body"))
    body = ""
    title = pull.get("title") or ""
    if number is not None:
        ticket = gh_json(["issue", "view", str(number), "-R", repo, "--json", "body,title"])
        body = ticket.get("body") or ""
        title = ticket.get("title") or title
    proof_path = proof_file.path_for(ticket_key(title), number)
    state, text = proof_file.fetch(repo, proof_path, merge)
    report_exists = gh_ok(["api", f"repos/{repo}/contents/{COST_REPORT}?ref={merge}"])
    items = checklist(body, pull.get("body") or "", files, state, text, proof_path, report_exists)
    return {"repo": repo, "pr": pr, "issue": number, "merge": merge, "files": files, "items": items}


def main(argv=None):
    parser = argparse.ArgumentParser(description="The close checklist for a merged pull request.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--issue", type=int)
    args = parser.parse_args(argv)
    try:
        result = run_check(args.repo, args.pr, args.issue)
    except RuntimeError as exc:
        print(f"close check: could not read the pull request: {exc}")
        print("RESULT: FAIL")
        return 1
    print(f"close check: {args.repo}#{args.pr} (merge {result['merge'][:12]})")
    for item in result["items"]:
        print(f"{item['item']}: {item['status']} - {item['detail']}")
    target = f" {args.repo}#{result['issue']}" if result["issue"] is not None else ""
    print(f"RESULT: {'FAIL' if failures(result['items']) else 'PASS'}{target}")
    return 1 if failures(result["items"]) else 0


if __name__ == "__main__":
    sys.exit(main())
