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

import subprocess

# File names, compared without case. The coordinator's agent rules, the bar,
# the brief and the answer format the gate reads, the playbook, the reviewer
# prompt and every skill file.
PROMPT_FILE_NAMES = (
    "agent-rules.md",
    "answer_format.py",
    "gate_bar.py",
    "gate_findings.py",
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

# The branch a merge lands on when nothing retargets the pull request. A
# retarget moves a pull request onto another base without moving its head, and
# no head-only merge can refuse that, so the classification covers this branch
# as well as the pull request's own base.
DEFAULT_BASE = "main"


def scan_diff(fetch, repo, base, head, attempts=2):
    """HOLD, CLEAR or UNKNOWN for one head against its own base.

    The reviewed base is the only base this pull request is classified
    against. Scanning another base as well would hold ordinary code work: a
    feature branch can carry a prompt edit the default branch does not have,
    and a child pull request that changes only code would then read as a
    prompt change it never made.
    """
    for _ in range(max(1, attempts)):
        try:
            paths = tree_diff(fetch, repo, base, head)
        except (RuntimeError, ValueError, subprocess.SubprocessError):
            continue
        if paths is not None:
            return prompt_scan(paths)
    return UNKNOWN


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


def page_entries(pages):
    """The file entries of a slurped page list, or None when it is not one.

    `gh api --paginate --slurp` wraps every page in a single array, so one
    page arrives as `[[entry, ...]]` and several as `[[...], [...]]`. Reading
    the raw paginated output instead concatenates the pages, which is not JSON
    at all: a 101-file pull request then read as unknown on every run.
    """
    if not isinstance(pages, list) or not all(isinstance(page, list) for page in pages):
        return None
    return [entry for page in pages for entry in page if isinstance(entry, dict)]


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
    dropped the one prompt file. A count that is not known is not a complete
    list either: without it the caller cannot tell, and the safe answer for a
    list that authorizes a merge is defer. An entry GitHub gave no name for
    makes the list unusable too: the missing name could be the prompt file.
    """
    if not isinstance(changed_files, int):
        return False
    entries = list(entries or ())
    if len(entries) < changed_files:
        return False
    return all(isinstance(entry, dict) and isinstance(entry.get("filename"), str)
               and bool(entry["filename"]) for entry in entries)


def prompt_scan(paths):
    """HOLD, CLEAR or UNKNOWN for one changed-path list.

    An unreadable list (None) is UNKNOWN, never CLEAR: its caller retries or
    defers the gate, because CLEAR lets the pull request merge.
    """
    if paths is None:
        return UNKNOWN
    return HOLD if prompt_change(paths) else CLEAR


def one_object(value):
    """The single object a reader's JSON helper returned, or None.

    A reader may hand back the object itself or the one-row slurped list of
    it, so both shapes read the same here.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for row in value:
            if isinstance(row, dict):
                return row
    return None


def tree_entries(tree, prefix=""):
    """Every non-directory path of one tree response mapped to its entry, or None.

    A blob is a file and a `commit` entry is a submodule: both can carry
    prompt text, so both are kept. Only the directory entries are dropped,
    because a directory is not a changed path of its own. The whole entry is
    kept (type, mode and sha) and not just the sha: a mode-only change keeps
    the blob sha while changing what git records, and a submodule has no blob
    sha at all. A tree GitHub truncated, or an entry without a usable path,
    is not a complete picture of the paths, so it is None.
    """
    tree = one_object(tree)
    if not isinstance(tree, dict) or tree.get("truncated"):
        return None
    entries = tree.get("tree")
    if not isinstance(entries, list):
        return None
    paths = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") == "tree":
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            # An entry GitHub gave no path for is a tree that cannot be read
            # completely, so it decides nothing.
            return None
        paths[prefix + path] = (entry.get("type"), entry.get("mode"), entry.get("sha"))
    return paths


# A recursive tree listing stops at 100,000 entries or 7 MB, so a big
# repository arrives truncated. Its directories are then read in step, and
# a directory whose subtree sha is the same on both sides is skipped without
# a request, so a code-only change spends the budget on the directories it
# touched rather than on every directory of the repository. The bound is
# still finite: a walk that cannot finish is unknown, never clear.
TREE_REQUESTS = 5000


def tree_paths(fetch, repo, ref, requests=None):
    """Every non-directory path of one commit's tree, or None.

    `fetch(endpoint)` is a reader's own `gh api` read. The recursive listing
    is the cheap read. A truncated one is no list of paths at all: the walk
    starts again from a fresh, non-recursive root listing, so the files at
    the root count as well, and reads each directory in turn. That is how a
    repository too big for one listing still yields every path instead of
    blocking the pull request for ever.
    """
    budget = [TREE_REQUESTS] if requests is None else requests
    budget[0] -= 1
    if budget[0] < 0:
        return None
    root = fetch(f"repos/{repo}/git/trees/{ref}?recursive=1")
    complete = tree_entries(root)
    if complete is not None:
        return complete
    tree = one_object(root)
    if not isinstance(tree, dict) or not tree.get("truncated"):
        return None
    paths = {}
    stack = [(ref, "")]
    while stack:
        sha, prefix = stack.pop()
        if not isinstance(sha, str) or not sha:
            return None
        budget[0] -= 1
        if budget[0] < 0:
            return None
        directory = one_object(fetch(f"repos/{repo}/git/trees/{sha}"))
        if not isinstance(directory, dict) or directory.get("truncated"):
            return None
        entries = directory.get("tree")
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if not isinstance(entry, dict):
                return None
            path = entry.get("path")
            if not isinstance(path, str) or not path:
                return None
            if entry.get("type") == "tree":
                if not isinstance(entry.get("sha"), str) or not entry["sha"]:
                    return None
                stack.append((entry["sha"], f"{prefix}{path}/"))
                continue
            paths[prefix + path] = (entry.get("type"), entry.get("mode"), entry.get("sha"))
    return paths


def parse_listing(listing):
    """One tree listing as `(files, directories)`, or None when it is not whole.

    A blob is a file and a `commit` entry is a submodule: both can carry
    prompt text, so both are kept. A directory is not a changed path of its
    own, so it is kept apart with its subtree sha: two sides of a walk that
    hold the same sha hold the same paths, and neither needs reading.
    """
    listing = one_object(listing)
    if not isinstance(listing, dict) or listing.get("truncated"):
        return None
    entries = listing.get("tree")
    if not isinstance(entries, list):
        return None
    files, directories = {}, {}
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            return None
        if entry.get("type") == "tree":
            sha = entry.get("sha")
            if not isinstance(sha, str) or not sha:
                return None
            directories[path] = sha
            continue
        files[path] = (entry.get("type"), entry.get("mode"), entry.get("sha"))
    return files, directories


def read_listing(fetch, repo, ref, budget, recursive=False):
    """One tree listing read as `(files, directories)`, or None.

    None means the budget is spent or the read is not a whole listing, so a
    caller never reads it as an empty tree.
    """
    budget[0] -= 1
    if budget[0] < 0:
        return None
    query = "?recursive=1" if recursive else ""
    return parse_listing(fetch(f"repos/{repo}/git/trees/{ref}{query}"))


def walked_changes(fetch, repo, before, base, after, head, budget):
    """The changed paths of two trees, reading only the directories that differ.

    A repository too big for one recursive listing is read directory by
    directory, both sides in step. A directory whose subtree sha is the same
    on both sides holds the same paths, so it is skipped without spending a
    request: a code-only change pays for the directories it touched, not for
    every directory of the repository. A side that already has a whole
    listing contributes its root entries, so its root is not read again.
    """
    def root(side, ref):
        if side is None:
            return read_listing(fetch, repo, ref, budget)
        files, directories = side
        return ({path: entry for path, entry in files.items() if "/" not in path},
                {path: sha for path, sha in directories.items() if "/" not in path})

    before_root, after_root = root(before, base), root(after, head)
    if before_root is None or after_root is None:
        return None
    changed = set()
    stack = [(before_root, after_root, "")]
    while stack:
        (before_files, before_dirs), (after_files, after_dirs), prefix = stack.pop()
        for name, entry in after_files.items():
            if before_files.get(name) != entry:
                changed.add(prefix + name)
        for name in before_files:
            if name not in after_files:
                changed.add(prefix + name)
        for name in set(before_dirs) | set(after_dirs):
            before_sha, after_sha = before_dirs.get(name), after_dirs.get(name)
            if before_sha is not None and before_sha == after_sha:
                continue
            sides = []
            for sha in (before_sha, after_sha):
                side = ({}, {}) if sha is None else read_listing(fetch, repo, sha, budget)
                if side is None:
                    return None
                sides.append(side)
            stack.append((sides[0], sides[1], f"{prefix}{name}/"))
    return sorted(changed)


def changed_paths(before, after):
    """The paths whose entry differs between two commit trees.

    An entry is its type, mode and sha, so a renamed, retyped, re-moded or
    rewritten path is changed. A path only on one side is changed too.
    """
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    changed = {path for path, sha in after.items() if before.get(path) != sha}
    changed.update(path for path in before if path not in after)
    return sorted(changed)


def tree_diff(fetch, repo, base, head, requests=None):
    """The complete changed paths of a pull request, or None.

    `fetch(endpoint)` is a reader's own `gh api` read. The files endpoint
    stops at 3,000 entries, so a bigger pull request's list is incomplete by
    construction and can never be cleared; comparing the merge base's tree
    with the head's tree gives every changed path instead, which is what the
    hold decides on. Both refs are the ones the caller pinned, so a head that
    moves during the gate cannot change the answer. A repository too big for
    one recursive listing is walked with its unchanged directories skipped,
    so the walk budgets for the changed paths and not for the whole tree.
    None means the diff could not be read completely.
    """
    budget = [TREE_REQUESTS] if requests is None else requests
    compare = one_object(fetch(f"repos/{repo}/compare/{base}...{head}"))
    merge_base = ((compare or {}).get("merge_base_commit") or {}).get("sha")
    if not isinstance(merge_base, str) or not merge_base:
        return None
    before = read_listing(fetch, repo, merge_base, budget, recursive=True)
    after = read_listing(fetch, repo, head, budget, recursive=True)
    if before is not None and after is not None:
        return changed_paths(before[0], after[0])
    return walked_changes(fetch, repo, before, merge_base, after, head, budget)
