"""The close checklist: what the coordinator reads before it closes a ticket.

Four items, each answered from the merged pull request and its ticket:

1. scope: every changed file is inside the ticket's stated scope.
2. proof file: the pull request carries its repo's own check evidence. In
   mac-ops that is a proof file (MO-1065), in strategy-replay-workbench a
   `success` `srw/agent-check` status on the head, elsewhere a
   `Builder check: PASS <head sha>` line in the pull request body.
3. checks: every check the mac-ops proof file lists is `passed`.
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
MAC_OPS_REPO = "shyamsivakumar/mac-ops"
SRW_REPO = "shyamsivakumar/strategy-replay-workbench"
SRW_CHECK_CONTEXT = "srw/agent-check"
COST_REPORT = "evidence/MO-1068/cost-report.md"
# A cost note carries a value: "Cost:" on its own is a label without a
# note, so it waives nothing.
COST_NOTE = re.compile(r"(?im)^[ \t>*-]*(cost|cost note|kosten)[ \t]*[:\-][ \t]*\S")
TICKET_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9]*)-(\d+)\b")
ISSUE_REF = re.compile(r"(?:refs|fixes|closes|resolves)[ \t]+#(\d+)", re.IGNORECASE)
# A token is a whole path, never the tail of a longer one: the part of
# `~/Code/inbox/note.md` after the `~` or the `/` is not a path in this
# repository, so the character before a token may not continue a path.
_NOT_IN_PATH = r"(?<![A-Za-z0-9_.*~/\\-])"
# A path token keeps the slash a directory declaration ends with, so
# "In: src/" stays "src/" and bounds every path under it.
PATH_TOKEN = re.compile(_NOT_IN_PATH +
                        r"(?=[A-Za-z0-9_.*-]*/)[A-Za-z0-9_.*-]+(?:/[A-Za-z0-9_.*-]+)*/?")
# A bare file name is a token only when its extension is one this list
# knows: the list is what keeps prose such as "3.9" or "e.g." out of the
# tokens. It carries the document and source extensions a ticket can
# declare by name, so a new language is one entry here and one test.
FILE_TOKEN = re.compile(_NOT_IN_PATH + r"[A-Za-z0-9_.*-]+\.(?:py|js|mjs|cjs|json|md|sh|ts|tsx|jsx|yml|yaml|cfg|toml|txt|html|css|swift)\b")
DOCKERFILE_TOKEN = re.compile(_NOT_IN_PATH + r"Dockerfile(?:\.[A-Za-z0-9_-]+)?\b")

PASS = "pass"
FAIL = "fail"
SKIPPED = "skipped"

# The ticket template says whether its own tests may change. The clause is
# the ticket's statement, so it is the ticket that allows the change. The
# clause keeps its restriction: it lets a test change when the test pins
# what the change pins, never when the test is about something else.
# A ticket says whether its existing tests may change. Its clause keeps its
# restriction: a test may change as far as this needs, that is when the
# ticket names that test or when the test is the test of a file the change
# touches. No string ties a test to a change: a pull request can write the
# same string into an unrelated test and into a file it changed, and that
# proves nothing.


# A ticket states its scope in prose, and it can exclude as well as permit.
# "In: x. Out: y" says that y is not in scope, so the words after an "out"
# marker, and the words of a sentence that forbids a change, name what the
# ticket excludes. Those names are never permission.
SEGMENT = re.compile(r"(?i)\b(in|inside|out|out of scope|not in scope|excludes|except)\b\s*:")
OUT_MARKERS = ("out", "out of scope", "not in scope", "excludes", "except")
# A prohibition names a change it forbids: "must not change x", "do not
# touch x". A phrase that merely forbids something else, "never file
# follow-up issues", forbids no file and excludes nothing.
PROHIBITION = re.compile(r"(?i)\b(?:must not|do not|never)\s+"
                          r"(?:change|changes|changing|touch|touches|touching|edit|edits|editing|include|includes)\b")
WITHOUT_CLAUSE = re.compile(r"(?i)\bwithout\s+"
                            r"(?:change|changes|changing|touch|touches|touching|edit|edits|editing|include|includes)\b")
SENTENCE = re.compile(r";|\.\s")
# A Markdown heading opens a section, and a section states its own intent.
HEADING = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]*(.*)$")
# A heading that declares the scope of the change: the section under it is
# the ticket's declaration of what it changes.
SCOPE_HEADING = re.compile(r"(?i)^[*_ ]*scope\b")
# A heading that names only exclusions excludes what its section names.
EXCLUSION_HEADING = re.compile(
    r"(?i)^[*_ ]*(out|out of scope|not in scope|excludes?|non-goals?|except(?: for)?)[*_ :]*$")


def scope_texts(body):
    """The ticket's permission text and the ticket's exclusion text.

    An "out" segment, a sentence that forbids a change, and the words
    after them are exclusions, and an exclusion holds to the end of its
    section: a Markdown list under an `Out of scope:` heading stays
    excluded, because the list continues the exclusion the heading began.
    A Markdown heading states its section's intent again, and an "in"
    marker states it inside a line, so the words after it are the
    declaration. When the ticket declares its scope, that declaration is
    the permission and the rest of the ticket is background.
    """
    declared = []
    plain = []
    exclusion = []
    kind = "plain"

    def record(text, kind):
        """File one piece of text, and answer the kind it leaves behind."""
        if not text.strip():
            return kind
        if PROHIBITION.search(text):
            exclusion.append(text)
            return kind
        clause = None if kind == "exclusion" else WITHOUT_CLAUSE.search(text)
        if clause:
            record(text[:clause.start()], kind)
            exclusion.append(text[clause.start():])
            return kind
        if kind == "exclusion":
            exclusion.append(text)
        elif kind == "declared":
            declared.append(text)
        else:
            plain.append(text)
        return kind

    # The sections that are open, each with the intent it carries. A
    # heading ends the sections at its level and deeper and opens one of
    # its own, and it keeps the intent of the section it sits in: a file
    # under "### Protected files" is still excluded by the
    # "## Out of scope" section around it, and a sibling heading restores
    # that section's intent rather than dropping it.
    sections = []
    for line in (body or "").splitlines():
        heading = HEADING.match(line)
        if heading:
            named = (heading.group(2) or "").strip()
            depth = len(heading.group(1))
            while sections and sections[-1][0] >= depth:
                sections.pop()
            enclosing = sections[-1][1] if sections else "plain"
            if EXCLUSION_HEADING.match(named):
                kind = "exclusion"
            elif SCOPE_HEADING.match(named):
                # A heading that declares the scope cannot lift the
                # exclusion of the section it sits in: the exclusion holds
                # until a sibling or a higher heading ends it.
                kind = "exclusion" if enclosing == "exclusion" else "declared"
            else:
                kind = enclosing
            sections.append((depth, kind))
        for sentence in SENTENCE.split(line):
            position = 0
            for match in SEGMENT.finditer(sentence):
                kind = record(sentence[position:match.start()], kind)
                marker = match.group(1).lower()
                if marker in OUT_MARKERS:
                    kind = "exclusion"
                elif kind != "exclusion":
                    kind = "declared"
                # An inline marker cannot lift the exclusion of the
                # section it sits in: the exclusion holds until a sibling
                # or a higher heading ends it. The marker becomes the
                # intent of the section it is in, so a heading under that
                # section keeps it too.
                if sections:
                    sections[-1] = (sections[-1][0], kind)
                position = match.end()
            kind = record(sentence[position:], kind)
    # A ticket is judged by its declaration: the words after an "in"
    # marker, and the section under a heading that declares the scope.
    # The rest of the ticket is background, and a name in the background
    # does not widen the scope of the change the ticket asked for. A
    # ticket that declares no scope declares none that can be judged, so
    # the scope fails closed rather than fall back to the whole ticket.
    return "\n".join(declared), "\n".join(exclusion)


def scope_tokens(body):
    """The files and paths the ticket permits.

    A ticket names its area in prose, so the tokens are the path-like
    words in the body: a path with a slash, or a file name with an
    extension. A name the ticket excludes is not a permission, so it is
    not a token.
    """
    permission, exclusion = scope_texts(body)
    excluded = exclusion_tokens(exclusion)
    tokens = set()
    for text in (permission,):
        for match in PATH_TOKEN.finditer(text or ""):
            token = match.group(0).strip(".,;:()[]")
            if token and "://" not in token:
                tokens.add(token)
        for match in FILE_TOKEN.finditer(text or ""):
            tokens.add(match.group(0).strip(".,;:()[]"))
        for match in DOCKERFILE_TOKEN.finditer(text or ""):
            tokens.add(match.group(0).strip(".,;:()[]"))
    return {token for token in tokens if not token_matches_any(token, excluded)}


def exclusion_tokens(text):
    """The files and paths the ticket excludes."""
    tokens = set()
    for match in PATH_TOKEN.finditer(text or ""):
        token = match.group(0).strip(".,;:()[]")
        if token and "://" not in token:
            tokens.add(token)
    for match in FILE_TOKEN.finditer(text or ""):
        tokens.add(match.group(0).strip(".,;:()[]"))
    for match in DOCKERFILE_TOKEN.finditer(text or ""):
        tokens.add(match.group(0).strip(".,;:()[]"))
    return tokens


def token_matches_any(token, tokens):
    """Does a token name another token?

    Two qualified paths are compared in full, because a path that carries
    its directory names one file: the exclusion `legacy/config.py` does
    not reach `src/config.py`. A bare name carries no directory, so it
    names any token that ends with it.
    """
    for other in tokens:
        if token == other:
            return True
        if "/" in token and "/" in other:
            continue
        if token.rsplit("/", 1)[-1] == other.rsplit("/", 1)[-1]:
            return True
    return False


def evidence_dir(proof_path):
    """The ticket's own evidence directory, read from its proof file path.

    The proof file of a ticket sits in `evidence/<KEY>-<issue>/`, so that
    directory holds the evidence of this ticket and nothing else. A pull
    request with no ticket has no such directory: its proof file sits at
    the default path, so that one file is all the evidence it can add.
    """
    if not proof_path or proof_path == proof_file.DEFAULT_PROOF:
        return ""
    return os.path.dirname(proof_path.rstrip("/"))


def in_evidence(path, evidence=""):
    """Is this file evidence of this ticket?

    Evidence travels with the change, but only the ticket's own evidence
    directory travels. A pull request scoped to one file can neither add
    nor overwrite another ticket's evidence and still pass the scope
    item.
    """
    directory = (evidence or "").rstrip("/")
    if not directory.startswith("evidence/"):
        return False
    return path.startswith(directory + "/")


def in_scope(path, tokens, changed=(), evidence=""):
    """Is one changed file inside the ticket's stated scope?

    A file is in scope when the ticket names it, names a directory that
    holds it, or names a glob that matches it. Evidence travels with the
    change, so a file under the ticket's own evidence directory is in
    scope. A test is in scope only when it tests a file the change
    touches: a test of something else is not part of this change, not
    even when the ticket says its existing tests may change.
    """
    base = os.path.basename(path)
    if in_evidence(path, evidence):
        return True, f"{path} is the ticket's evidence and travels with the change"
    for token in tokens:
        if token_matches(path, token):
            return True, f"{path} is named by {token}"
    if path.startswith("tests/"):
        # The inferred allowance reaches the test of a changed file, and
        # only a test file: a fixture or a helper that happens to carry
        # the name of the source is not part of the change.
        if not is_test_file(base):
            return False, ""
        stem = os.path.splitext(base)[0].removeprefix("test_")
        for other in named_sources(changed, tokens):
            other_stem = os.path.splitext(os.path.basename(other))[0]
            if stem == other_stem:
                return True, f"{path} tests {other}"
    return False, ""


def is_test_file(name):
    """Is this file a test of a module?

    A test file carries the test prefix and the test extension. A fixture
    or a helper that shares the name of a source file is not a test of
    it, so the inferred allowance does not reach it.
    """
    return name.startswith("test_") and name.endswith(".py")


def named_sources(changed, tokens=None):
    """The changed source files a test can tie to.

    A test ties to a source file, never to evidence and never to another
    test: a pull request can add an evidence file that carries the name
    of its own test, and that must not authorize the test change. A
    source file the ticket never names fails the scope item on its own,
    so tying to it grants nothing.
    """
    return [path for path in changed
            if not path.startswith("evidence/") and not path.startswith("tests/")]


def token_matches(path, token):
    """Does a token name this file?

    A token names a file when it is the file, a directory that holds it,
    a glob that matches it, or the file's own name.
    """
    base = os.path.basename(path)
    if any(char in token for char in "*?["):
        return fnmatch.fnmatch(path, token) or fnmatch.fnmatch(base, token)
    if "/" in token:
        return path == token or path.startswith(token.rstrip("/") + "/")
    return base == token


def names_a_scope(tokens):
    """Does the ticket name something that bounds the scope?

    A file name, a path, or a glob. A path is a directory of the
    repository, and it bounds every changed file under it, so a ticket
    that declares a directory says where its change is and each changed
    path is checked against that boundary.
    """
    for token in tokens:
        if any(char in token for char in "*?["):
            return True
        if "/" in token:
            return True
        if FILE_TOKEN.fullmatch(token.rsplit("/", 1)[-1]):
            return True
        if DOCKERFILE_TOKEN.fullmatch(token.rsplit("/", 1)[-1]):
            return True
    return False


def item_scope(body, files, evidence="", error=""):
    """Item 1: the diff stays inside the ticket's stated scope.

    The ticket is the only authority for the scope. A pull request cannot
    widen the scope of the ticket that asked for the change, so nothing in
    the pull request body is read here. When the ticket names no file in
    this repository the scope cannot be judged, and an unjudged scope
    authorizes no close: the item fails. The evidence that travels is the
    evidence of this ticket, never another ticket's.
    """
    if error:
        return {"item": "scope", "status": FAIL, "required": True, "unknown": True,
                "detail": ("the files of the pull request were not read to the end, so the scope "
                           f"cannot be judged: {error}")}
    permission, exclusion = scope_texts(body)
    excluded = exclusion_tokens(exclusion)
    blocked = [path for path in files if any(token_matches(path, token) for token in excluded)]
    if blocked:
        return {"item": "scope", "status": FAIL, "required": True,
                "detail": "the ticket excludes it: " + ", ".join(sorted(blocked))}
    tokens = scope_tokens(body)
    if not tokens or not names_a_scope(tokens):
        return {"item": "scope", "status": FAIL, "required": True,
                "detail": ("the ticket names no file in this repository, so the scope cannot be "
                           "judged: the ticket has to name the files it changes")}
    outside = []
    for path in files:
        ok, _ = in_scope(path, tokens, files, evidence)
        if not ok:
            outside.append(path)
    if outside:
        return {"item": "scope", "status": FAIL, "required": True,
                "detail": "outside the ticket's stated scope: " + ", ".join(sorted(outside))}
    return {"item": "scope", "status": PASS, "required": True,
            "detail": "every changed file is inside the ticket's stated scope"}


def changed_proof(files, proof_path):
    """Is the proof file part of this change?

    A proof file that is already on the base branch is an earlier run's
    proof. The checklist reads the proof of the change in front of it, so
    the path has to be among the files the pull request changes.
    """
    return proof_path in files


def item_proof(state, path, detail=""):
    """Item 2: the pull request carries a proof file."""
    if state == proof_file.FOUND:
        return {"item": "proof file", "status": PASS, "required": True, "detail": f"{path} is present"}
    if state == proof_file.MISSING:
        return {"item": "proof file", "status": FAIL, "required": True,
                "detail": detail or f"the pull request carries no proof file at {path}"}
    return {"item": "proof file", "status": FAIL, "required": True, "unknown": True,
            "detail": f"the proof file at {path} could not be read, so the checks are unproven"}


def latest_status(statuses, context):
    """The newest status of one context: GitHub lists the newest first."""
    for status in statuses:
        if status.get("context") == context:
            return status
    return None


def item_agent_check(repo, head, pr_body, statuses):
    if repo == SRW_REPO:
        status = latest_status(statuses, SRW_CHECK_CONTEXT)
        state = status.get("state") if status else "missing"
        return {"item": "proof file", "status": PASS if state == "success" else FAIL, "required": True,
                "detail": f"{SRW_CHECK_CONTEXT} is {state} on {head}"}
    line = f"Builder check: PASS {head}"
    found = any(row.strip() == line for row in (pr_body or "").splitlines())
    return {"item": "proof file", "status": PASS if found else FAIL, "required": True,
            "detail": (f"the pull request body has the line `{line}`" if found else
                       f"the pull request body has no line `{line}`")}


def item_checks_skipped(repo):
    return {"item": "checks", "status": SKIPPED, "required": False,
            "detail": f"the proof table is read for {MAC_OPS_REPO} only; {repo} has no proof table"}


# A Markdown cell holds a pipe that is written as \|, so a row is split on
# the pipes that are not escaped, and the escape is read back as a pipe.
PIPE_SPLIT = re.compile(r"(?<!\\)\|")
# The header of the proof table, cell for cell. A row that only starts
# like the header is a check, so the row that carries a failure can never
# be dropped as a header. The short header is the one an older proof file
# writes; the full header adds the detail the canonical template has.
PROOF_HEADERS = (("check", "command", "result"),
                 ("check", "command", "result", "detail"))
# A check recorded outside the table: a name, a colon, and a result.
RESULT_LINE = re.compile(r"(?i)^(?:[-*+]\s+)?(?P<name>[^:]+?)\s*:\s*(?P<result>passed|failed|not run)\s*$")


def split_cells(line):
    r"""The cells of one table row.

    A command can hold a pipe, and a Markdown table writes that pipe as
    \|, so a row is split on the pipes that are not escaped and the
    escape is read back as the pipe it stands for.
    """
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [cell.strip().replace("\\|", "|") for cell in PIPE_SPLIT.split(inner)]


def proof_rows(text):
    """Every check the proof file lists, with the result it recorded.

    A row that stops short of its result cell is still a check the file
    lists, and it carries no result: the empty result is what makes it
    fail the item, so the row is never dropped. Only the table's own
    separator and header are not checks, and the header is recognized
    once as the whole header row: every cell of it, including the result
    and detail cells, has to read as the header. A row that only starts
    like the header is a check like any other, so a recorded failure
    cannot hide behind a name that reads like the header. The separator is recognized
    as the whole row too: a row that only its first cell marks as a
    separator is a check with a malformed name, and a malformed row is a
    row that blocks the close.
    """
    rows = []
    header_seen = False
    in_table = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            in_table = False
            continue
        if "|" not in line:
            if in_table:
                # A line inside the table that is not a row is a malformed
                # row: dropping it would hide whatever it recorded.
                rows.append((line, ""))
                continue
            # A result written outside the table is a check too: "lane
            # selection: failed" records a failure, and dropping it would
            # report that every check passed.
            plain = RESULT_LINE.match(line)
            if plain:
                rows.append((plain.group("name").strip(), plain.group("result").lower()))
            continue
        cells = split_cells(line)
        if cells and all(cell and set(cell) <= set("-: ") for cell in cells):
            continue
        name = cells[0] if cells else ""
        if not header_seen and tuple(cell.lower() for cell in cells) in PROOF_HEADERS:
            header_seen = True
            in_table = True
            continue
        in_table = True
        result = cells[2].lower() if len(cells) > 2 else ""
        rows.append((name or "(unnamed row)", result))
    return rows


def item_checks(state, text):
    """Item 3: every check the proof file lists passed."""
    if state != proof_file.FOUND:
        return {"item": "checks", "status": SKIPPED, "required": True,
                "detail": "there is no proof file to read"}
    rows = proof_rows(text)
    if not rows:
        return {"item": "checks", "status": FAIL, "required": True,
                "detail": "the proof file lists no check"}
    failed = [f"{name} ({result or 'no result recorded'})"
              for name, result in rows if result != "passed"]
    if failed:
        return {"item": "checks", "status": FAIL, "required": True,
                "detail": "the proof file lists a check that is not passed: " + ", ".join(failed)}
    return {"item": "checks", "status": PASS, "required": True,
            "detail": f"every one of the {len(rows)} checks the proof file lists passed"}


def item_cost(body, report_state, detail=""):
    """Item 4: a cost note, once the MO-1068 cost report exists.

    The lookup of the report has three answers, not two: the report
    exists, the report does not exist, or the lookup did not answer. A
    lookup that did not answer is not a confirmed absence, so the cost
    note cannot be waived and the item fails.
    """
    if report_state == "absent":
        return {"item": "cost note", "status": SKIPPED, "required": False,
                "detail": f"the MO-1068 cost report ({COST_REPORT}) does not exist yet"}
    if report_state == "unknown":
        return {"item": "cost note", "status": FAIL, "required": True,
                "detail": (f"the lookup of the cost report did not answer, so the cost note "
                           f"cannot be confirmed: {detail}")}
    if COST_NOTE.search(body or ""):
        return {"item": "cost note", "status": PASS, "required": True,
                "detail": "the pull request body carries a cost note"}
    return {"item": "cost note", "status": FAIL, "required": True,
            "detail": "the cost report exists, but the pull request body carries no cost note"}


def checklist(body, pr_body, files, proof_state, proof_text, proof_path, report_state, report_detail="", proof_detail="", scope_files=None, scope_error="", repo_items=None):
    """The four items, in the order the checklist reads them.

    Outside mac-ops, repo_items is the (proof, checks) pair that replaces
    the two items read from the proof file.
    """
    proof_item, checks_item = repo_items or (item_proof(proof_state, proof_path, proof_detail),
                                             item_checks(proof_state, proof_text))
    return [
        item_scope(body, files if scope_files is None else scope_files,
                   evidence_dir(proof_path), scope_error),
        proof_item,
        checks_item,
        item_cost(pr_body, report_state, report_detail),
    ]


def failures(items):
    """The items that fail."""
    return [item for item in items if item["status"] == FAIL]


def blocking(items):
    """The items that stop the close.

    A failure stops the close, and so does a check that could not be
    judged: an unknown scope or an unanswered lookup authorizes nothing.
    Only a requirement that does not exist yet, the cost note before the
    MO-1068 report lands, is skipped without blocking.
    """
    return [item for item in items
            if item["status"] == FAIL or (item["status"] == SKIPPED and item.get("required", True))]


def report(items, target=""):
    """The checklist as text, one line per item."""
    lines = [f"{item['item']}: {item['status']} - {item['detail']}" for item in items]
    stopped = blocking(items)
    lines.append(f"RESULT: {'FAIL' if stopped else 'PASS'}{(' ' + target) if target else ''}")
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


def report_state(repo, ref):
    """Does the cost report exist, and did the lookup answer?

    Three answers: the report exists, the report does not exist, or the
    lookup did not answer. A timeout, a permission error and a GitHub
    service error are all the third one, and the third one is never a
    confirmed absence.
    """
    args = ["api", f"repos/{repo}/contents/{COST_REPORT}?ref={ref}"]
    try:
        result = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=GH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "unknown", f"the read timed out after {GH_TIMEOUT}s"
    except OSError as exc:
        return "unknown", str(exc)
    if result.returncode == 0:
        return "exists", ""
    error = result.stderr.strip()
    if "404" in error or "Not Found" in error:
        return "absent", error
    first = error.splitlines()[0] if error else f"gh exited {result.returncode}"
    return "unknown", first


# The pages of a pull request's files the checklist reads. A pull request
# with more files than a page holds would hide its last files from the
# scope, so the pages are read to the end.
FILE_PAGES = 30


def fetch_files(repo, pr, expected=None):
    """The files a pull request changes, and the path a rename came from.

    A rename has two paths: the file it came from and the file it is now.
    The scope is judged against both, so a rename cannot carry an
    out-of-scope file into an in-scope name.
    """
    changed = []
    scope = []
    error = ""
    for page in range(1, FILE_PAGES + 1):
        try:
            entries = gh_json(["api", f"repos/{repo}/pulls/{pr}/files?per_page=100&page={page}"])
        except RuntimeError as exc:
            # The pages were not read to the end, so the diff is not known:
            # the scope cannot be judged and the close is refused.
            error = str(exc)
            break
        if not isinstance(entries, list) or not entries:
            break
        for entry in entries:
            path = entry.get("filename")
            if path:
                changed.append(path)
                scope.append(path)
            previous = entry.get("previous_filename")
            if previous:
                scope.append(previous)
        if len(entries) < 100:
            break
    if not error and expected is not None and len(changed) != expected:
        # The pages ended before the diff did, so the diff is not known:
        # the scope cannot be judged and the close is refused.
        error = (f"the pull request changes {expected} files and {len(changed)} were read")
    return changed, scope, error


def ticket_key(title):
    """The ticket key from its title, `MO-1077 · name` gives `MO`."""
    match = TICKET_KEY.match(title or "")
    return match.group(1) if match else None


def issue_of(body):
    """The issue number a pull request body refers to."""
    match = ISSUE_REF.search(body or "")
    return int(match.group(1)) if match else None


def fetch_statuses(repo, head):
    return gh_json(["api", f"repos/{repo}/commits/{head}/statuses?per_page=100"])


def run_check(repo, pr, issue=None, reader=None, status_reader=None):
    """Run the checklist on a merged pull request.

    A reader reads one file at a ref and returns the state and the text
    of it, the way `proof_file.fetch` does. The close step reads through
    GitHub; the replay reads through the local checkout, so it runs
    without the API. A status_reader does the same for the commit
    statuses of a head, and defaults to the API.
    """
    """Run the checklist on a merged pull request."""
    pull = gh_json(["pr", "view", str(pr), "-R", repo, "--json",
                    "state,headRefOid,body,mergeCommit,title,changedFiles"])
    merge = (pull.get("mergeCommit") or {}).get("oid") or pull["headRefOid"]
    files, scope_files, files_error = fetch_files(repo, pr, pull.get("changedFiles"))
    number = issue if issue is not None else issue_of(pull.get("body"))
    body = ""
    title = pull.get("title") or ""
    if number is not None:
        ticket = gh_json(["issue", "view", str(number), "-R", repo, "--json", "body,title"])
        body = ticket.get("body") or ""
        title = ticket.get("title") or title
    proof_path = proof_file.path_for(ticket_key(title), number)
    repo_items = None
    state, text, proof_detail = proof_file.MISSING, None, ""
    if repo == MAC_OPS_REPO:
        if reader is None:
            state, text = proof_file.fetch(repo, proof_path, merge)
        else:
            state, text = reader(proof_path, merge)
    else:
        head = pull["headRefOid"]
        statuses = (status_reader or fetch_statuses)(repo, head) if repo == SRW_REPO else []
        repo_items = (item_agent_check(repo, head, pull.get("body"), statuses),
                      item_checks_skipped(repo))
    proof_unknown = False
    if state == proof_file.FOUND and not changed_proof(files, proof_path):
        # The file is on the base branch: it is an earlier run's proof.
        state, text = proof_file.MISSING, None
        proof_detail = (f"the proof file at {proof_path} is not part of this change: the pull "
                        "request does not change it, so it is an earlier run's proof")
        proof_unknown = bool(files_error)
    if reader is None:
        report, report_detail = report_state(repo, merge)
    else:
        found, _ = reader(COST_REPORT, merge)
        report = {"found": "exists", "missing": "absent"}.get(found, "unknown")
        report_detail = ""
    items = checklist(body, pull.get("body") or "", files, state, text, proof_path, report,
                      report_detail, proof_detail, scope_files, files_error, repo_items)
    if proof_unknown:
        for item in items:
            if item["item"] == "proof file":
                item["unknown"] = True
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
    print(f"RESULT: {'FAIL' if blocking(result['items']) else 'PASS'}{target}")
    return 1 if blocking(result["items"]) else 0


if __name__ == "__main__":
    sys.exit(main())
