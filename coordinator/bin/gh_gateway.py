"""One GitHub call path for every coordinator caller.

The GitHub core quota is 5000 calls an hour for the user, and every caller
in the coordinator shares it. On 2026-11-18 it reached 0 at 12:44 UTC and
the lane driver, the overnight shift and gatekeep all stalled. This module
is the one place a caller's GitHub reads go through, so the count is known
and the repeated reads are served from a cache.

Three things live here.

`api_remaining()` reads the quota. The `rate_limit` endpoint does not count
against the core limit, so the read is cheap; it is still shared per
process, because several callers ask for it in one pass.

`run()` is a `subprocess.run` for a GitHub command. It records the call for
the usage report, and it serves a repeated list read from a short-lived
file cache when the caller's environment turns the cache on.

`cached()`, `store()` and `record()` are the same three steps for the
callers that already own their subprocess call, such as the overnight
shift, which starts the command in its own process group.

The cache is never used for a read that decides a merge or a gate on a
head. A head SHA read (`gh pr view`, `gh api .../pulls/<n>`) is not a
cacheable command here, so a short TTL on a list can never carry a stale
head into a merge decision. The floor is checked by the caller, because a
caller that may skip a read is the one that knows the read is optional.
"""
import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

# The core calls the callers should leave in reserve. Below this floor an
# optional read is skipped: the board keeps moving on what it already read
# instead of spending the last calls and stalling every caller at once.
DEFAULT_FLOOR = 1500
# A repeated list read is served from the cache for this long. It is short
# on purpose: a new pull request or a moved label shows within two minutes,
# and no read that decides a merge is cached at all.
LIST_TTL = 120
# A read that names its command may come from the cache, a read that names
# one object may not. `view` and a `repos/.../pulls/<n>` path are the head
# reads a merge decision uses.
# The reads the cache may serve, named one by one. A verb alone is not
# enough: `gh auth status --show-token` is a `status` read that prints a
# token, so it must never reach the disk cache. A command that is not in
# this set is not cached, whatever its verb.
# The complete collection routes the cache may serve. A route is matched in
# full, so a single object is never cached whatever its last segment is:
# `repos/o/r/pulls/7` is a pull and `repos/o/r/git/ref/heads/releases` is a
# ref to a branch named releases, and neither is a list.
COLLECTION_ROUTES = (
    r"repos/[^/]+/[^/]+/(?:issues|pulls|commits|branches|tags|releases|labels"
    r"|milestones|events|contributors|collaborators|forks|stargazers"
    r"|subscribers|topics|environments|deployments|comments|statuses"
    r"|check-runs|actions/runs|actions/workflows)",
    r"repos/[^/]+/[^/]+/(?:issues|pulls)/\d+/(?:comments|events|labels|timeline"
    r"|files|reviews|commits|statuses|check-runs|requested_reviewers)",
    r"repos/[^/]+/[^/]+/commits/[^/]+/(?:statuses|check-runs|comments)",
    r"search/(?:issues|repositories|users|commits|code|topics)",
    r"(?:orgs|users)/[^/]+/(?:repos|members|teams|events|followers)",
)
# A read that names only full commit SHAs returns the same bytes forever, so
# it is kept for IMMUTABLE_TTL instead of LIST_TTL. A route that names a
# branch or a tag is never here: `compare/main...<sha>` moves with `main`.
IMMUTABLE_TTL = 30 * 24 * 3600
SHA = r"[0-9a-f]{40}"
IMMUTABLE_ROUTES = (
    (rf"repos/[^/]+/[^/]+/git/trees/{SHA}", ("", "recursive=1")),
    (rf"repos/[^/]+/[^/]+/compare/{SHA}\.\.\.{SHA}", ("",)),
    (r"repos/[^/]+/[^/]+/contents/[^?]+", (f"ref={SHA}",)),
)
READ_COMMANDS = (
    ("pr", "list"),
    ("issue", "list"),
    ("label", "list"),
    ("repo", "list"),
    ("release", "list"),
    ("run", "list"),
    ("workflow", "list"),
    ("cache", "list"),
    ("gist", "list"),
    ("project", "list"),
    ("org", "list"),
    ("search", "search"),
)
# A command that prints a credential is never cached, whatever its verb.
CREDENTIAL_FLAGS = ("--show-token",)
CACHEABLE_COMMANDS = tuple(verb for _group, verb in READ_COMMANDS)
# The commands that take a subcommand, such as `gh pr list`. The verb is the
# word after the group, not the first word, so `gh pr list` and `gh issue
# list` are list reads and are cacheable like `gh label list`.
GROUPS = ("pr", "issue", "repo", "label", "release", "run", "workflow", "gist",
          "cache", "auth", "secret", "variable", "ruleset", "project", "org",
          "codespace", "extension", "api", "search")
# GitHub counts a search against its own bucket (30 requests a minute), not
# against the 5000 core calls an hour. A report that calls it a core call
# overstates the core usage.
SEARCH = "search"
CORE = "core"
GRAPHQL = "graphql"
# A command that is not one of these is `other`: it is named as such and is
# never counted as a core call.
REST_GROUPS = ("run", "workflow", "cache", "release", "secret", "variable",
               "ruleset", "gist", "codespace", "attestation",
               "ssh-key", "gpg-key", "auth")
# `gh repo` is a mixed command: its list and view are answered over GraphQL,
# its write commands over REST. A command this code does not know is `other`,
# never a guessed core call.
REPO_GRAPHQL_VERBS = ("list", "view")
REPO_REST_VERBS = ("clone", "create", "fork", "delete", "edit", "archive",
                   "rename", "sync", "set-default")
GRAPHQL_GROUPS = ("pr", "issue", "project", "label", "org")
# The `gh api` flags that take a value, so the endpoint can be found and the
# method can be read without mistaking a value for the endpoint.
VALUE_FLAGS = ("-X", "--method", "-H", "--header", "-f", "-F", "--field",
               "--raw-field", "--input", "-q", "--jq", "-t", "--template",
               "--cache", "--hostname")
BODY_FLAGS = ("-f", "-F", "--field", "--raw-field", "--input")
# The flags this code understands. A cluster it does not know, such as
# `-iXPOST`, may hide a method or a body, so such a command is never cached.
KNOWN_FLAGS = ("-X", "--method", "-H", "--header", "-f", "-F", "--field",
               "--raw-field", "--input", "-q", "--jq", "-t", "--template",
               "--cache", "--hostname", "--paginate", "--slurp", "--include",
               "-i", "--silent", "--verbose", "-v", "--raw", "--graphql",
               "-p", "--preview")
# The flags that format the output. With one of these, a page is not a JSON
# value any more, so the page count has to come from the response headers.
# `--silent` prints no body at all, so a paginated read with it cannot be
# counted from its output either.
OUTPUT_FILTER_FLAGS = ("-q", "--jq", "-t", "--template", "--silent", "--verbose")


def tokens(argv):
    """Return (flag, value) for the command's own words.

    A value can look exactly like a flag: `--template '-XGET'` carries the
    text `-XGET`, which is not a method. Pairing each value flag with its
    value is what tells a flag from its value."""
    words = [str(word) for word in (argv or [])[1:]]
    paired, index = [], 0
    while index < len(words):
        word = words[index]
        if word in VALUE_FLAGS and index + 1 < len(words):
            paired.append((word, words[index + 1]))
            index += 2
            continue
        paired.append((word, None))
        index += 1
    return paired


def significant(argv):
    """Return the command's own words, without the values of value flags."""
    return [word for word, _value in tokens(argv)]


def has_body(argv):
    """True when the command carries a request body, so it is a write.

    `gh` accepts the value attached (`--raw-field=name=value`, `-fname=value`)
    or as the next word; both are the same POST, and neither may be cached."""
    for word in significant(argv):
        if word in BODY_FLAGS:
            return True
        if word.startswith("--field=") or word.startswith("--raw-field=") or word.startswith("--input="):
            return True
        if len(word) > 2 and word.startswith(("-f", "-F")):
            return True
    return False
CACHE_ON = "COORDINATOR_GH_CACHE"
CACHE_DIR = Path(os.environ.get("COORDINATOR_GH_CACHE_DIR",
                                os.path.expanduser("~/.cache/coordinator/gh")))
# The usage report reads this file. One line per call that reached GitHub.
USAGE_LOG = Path(os.environ.get("COORDINATOR_GH_USAGE_LOG",
                                os.path.expanduser("~/Library/Logs/coordinator/gh-usage.jsonl")))
USAGE_LOG_MAX = int(os.environ.get("COORDINATOR_GH_USAGE_MAX", 4 * 1024 * 1024))
_CALLER = None
GATEWAY_MARK = "COORDINATOR_GH_VIA"
# A caller whose tests replace its own `subprocess` name hands the helper a
# getter for the launcher, so every gh call still goes through the one it
# can see. Resolved at call time, never captured at import time.
_RUNNER = None
_ETAG_DIR = None
_REMAINING = {}
_REMAINING_TTL = 30.0


class ApiBudgetExhausted(RuntimeError):
    pass


def floor():
    """Return the reserve this caller keeps, from the shared default."""
    try:
        return int(os.environ.get("COORDINATOR_GH_FLOOR", DEFAULT_FLOOR))
    except ValueError:
        return DEFAULT_FLOOR


def caller():
    """Return the name the usage report files this caller's calls under."""
    named = _CALLER or os.environ.get("COORDINATOR_CALLER")
    if named:
        return named
    return os.path.basename(sys.argv[0] or "python")


def set_runner(getter):
    """Use the caller's own subprocess launcher, looked up on every call."""
    global _RUNNER
    _RUNNER = getter


def set_etag_dir(getter):
    """Keep the etag entries in the caller's own directory, looked up on every call."""
    global _ETAG_DIR
    _ETAG_DIR = getter


def gateway_env():
    """The environment for a gh child the gateway starts, so the observation
    shim on PATH leaves the call to the gateway's own log line."""
    return {**os.environ, GATEWAY_MARK: "gateway"}


def _launch():
    runner = _RUNNER() if _RUNNER else subprocess.run

    def launch(*args, **kwargs):
        kwargs["env"] = {**(kwargs.get("env") or os.environ), GATEWAY_MARK: "gateway"}
        return runner(*args, **kwargs)
    return launch


def set_caller(name):
    """Name this caller in the usage log. A module a caller imports is not
    its own process, so it names itself rather than the command line."""
    global _CALLER
    _CALLER = name


def cache_enabled():
    return os.environ.get(CACHE_ON, "") in ("1", "on", "true", "yes")


def _gh(argv):
    return bool(argv) and os.path.basename(str(argv[0])) == "gh"


def verb(argv):
    """Return the command's verb, such as `list` in `gh issue list`."""
    words = [str(word) for word in argv[1:]]
    if not words:
        return ""
    if words[0] in (SEARCH, "api"):
        return words[0]
    if words[0] in GROUPS and len(words) > 1:
        return words[1]
    return words[0]


def endpoint(argv):
    """Return the `gh api` endpoint, or "" when the command names none."""
    words = [str(word) for word in argv[1:]]
    if not words or words[0] != "api":
        return ""
    skip = False
    for word in words[1:]:
        if skip:
            skip = False
            continue
        if word in VALUE_FLAGS:
            skip = True
            continue
        if word.startswith("-"):
            continue
        return word
    return ""


def graphql_operation(argv):
    """Return the operation name in a `gh api graphql` query, or ""."""
    words = [str(word) for word in argv[1:]]
    for index, word in enumerate(words[:-1]):
        if word in BODY_FLAGS and words[index + 1].startswith("query="):
            match = re.search(r"\b(?:query|mutation)\s+(\w+)", words[index + 1])
            return match.group(1) if match else ""
    return ""


def route(argv):
    """Return the command's endpoint with owner, repo, numbers and SHAs as `*`."""
    words = [str(word) for word in argv[1:]]
    if not words:
        return ""
    if words[0] != "api":
        return " ".join(words[:2]) if words[0] in GROUPS and len(words) > 1 else words[0]
    path = endpoint(argv).lstrip("/").split("?", 1)[0]
    segments = path.split("/")
    for index in range(len(segments)):
        redact = (segments[index].isdigit()
                  or re.fullmatch(r"[0-9a-f]{7,40}", segments[index]) is not None
                  or (index in (1, 2) and segments[0] == "repos")
                  or (index == 1 and segments[0] in ("orgs", "users")))
        if redact:
            segments[index] = "*"
    template = "/".join(segments)
    operation = graphql_operation(argv) if template == GRAPHQL else ""
    return f"{template} {operation}" if operation else template


def unknown_short_flag(argv):
    """True when a short flag cluster may hide a method or a body.

    `-iXPOST` carries a method inside the cluster. A cluster this code does
    not understand, and that holds an `X`, `f` or `F`, could be a write, so
    it is never cached."""
    for word in [str(token) for token in (argv or [])[1:]]:
        if not word.startswith("-") or word.startswith("--"):
            continue
        if word in KNOWN_FLAGS:
            continue
        if any(letter in word[1:] for letter in ("X", "f", "F")):
            return True
    return False


def method(argv):
    """Return the HTTP method `gh api` will use, as GitHub counts it.

    `gh api` reads unless a method is named or a field is given; a field
    without a method is a POST, and `-X GET` overrides a field. The method
    may be attached to another short flag, as in `-iXPOST`."""
    # `gh` uses the last method flag, so a repeated flag is read the same
    # way here. Reading only the first would call `-X GET -X POST` a read.
    named = None
    for word, value in tokens(argv):
        if word.startswith("--method="):
            named = word.split("=", 1)[1]
        elif word in ("-X", "--method"):
            named = value if value is not None else ""
        elif word.startswith("-") and not word.startswith("--") and "X" in word[1:]:
            # A combined short cluster such as `-iXPOST`: the method is the
            # text after X.
            named = word.split("X", 1)[1] or ""
        elif word.startswith("-X") and len(word) > 2:
            named = word[2:].lstrip("=")
    if named is not None:
        return named.strip().upper()
    if has_body(argv):
        return "POST"
    return "GET"


def resource(argv):
    """Return the GitHub quota a command spends.

    The quota is read from the endpoint or the command, not from the first
    word: `gh api search/issues` spends the search bucket, `gh run list`
    spends core calls on the Actions REST API, and `gh pr list` spends the
    GraphQL bucket. A command that is named in neither list is `other`."""
    words = [str(word) for word in argv[1:]]
    if not words:
        return CORE
    if words[0] == SEARCH:
        return SEARCH
    if words[0] == "api":
        path = endpoint(argv).lstrip("/")
        # Only the leading endpoint decides: `repos/acme/search/issues` is a
        # core read of a repository named search.
        if path.split("/", 1)[0] == SEARCH:
            return SEARCH
        # Only the parsed endpoint decides. `--jq graphql` is a filter
        # value on a REST read, not a GraphQL request.
        if path == GRAPHQL:
            return GRAPHQL
        return CORE
    if words[0] == "repo":
        subcommand = verb(argv)
        if subcommand in REPO_GRAPHQL_VERBS:
            return GRAPHQL
        return CORE if subcommand in REPO_REST_VERBS else "other"
    if words[0] in REST_GROUPS:
        return CORE
    if words[0] in ("issue", "pr"):
        # A mixed group: list and view are GraphQL, but a write such as
        # `gh issue comment` can post through REST. Its quota is not known
        # here, so it is reported as `other` rather than counted as a
        # GraphQL call it may not have made.
        return GRAPHQL if verb(argv) in ("list", "view", "status") else "other"
    if words[0] in GRAPHQL_GROUPS:
        return GRAPHQL
    return "other"


def has_flag(argv, name, short=None):
    """True when a boolean flag is set, whatever spelling `gh` accepted.

    `--paginate` and `--paginate=true` are the same flag, and a caller may
    use either; `=false` is not set."""
    def enabled(value):
        return value.strip().lower() in ("1", "true", "yes", "on")

    for word in [str(token) for token in (argv or [])[1:]]:
        if word == name:
            return True
        if word.startswith(name + "=") and enabled(word.split("=", 1)[1]):
            return True
        if short:
            if word == short:
                return True
            # A short alias takes an explicit value too: `-i=true`, `-w=true`.
            if word.startswith(short + "=") and enabled(word.split("=", 1)[1]):
                return True
    return False


def paginated(argv):
    return has_flag(argv, "--paginate")


def include_requested(argv):
    return has_flag(argv, "--include", "-i")


def cacheable(argv):
    """True when a repeated read of this command may be served from cache."""
    if not _gh(argv) or not cache_enabled():
        return False
    words = [str(word) for word in argv[1:]]
    if not words:
        return False
    if has_flag(argv, "--web", "-w"):
        # `--web` opens a browser; a cached answer would silently skip it.
        # `--web=true` is the same flag.
        return False
    if unknown_short_flag(argv):
        # A flag cluster may hide a method or a body: never cache it.
        return False
    if any(word in CREDENTIAL_FLAGS for word in argv[1:]):
        # `gh auth status --show-token` prints a token: never written down.
        return False
    if has_body(argv):
        # A body means a write, and a write is never served from a cache.
        return False
    host, account, checkout, repo_override, token_id = context(argv)
    if not account:
        # The account is unknown, so one entry could answer another
        # account's read. Skip the cache rather than guess.
        return False
    if (words[0], verb(argv)) in READ_COMMANDS:
        return True
    if words[0] != "api":
        return False
    # An api read is cached only when it is a verified GET of a list
    # endpoint. A write that carries a query string, such as
    # `gh api -X POST repos/o/r/dispatches?ref=main`, must never be served
    # from the cache: the cached success would answer a request that was
    # never sent.
    if immutable(argv):
        return True
    path = endpoint(argv)
    if method(argv) != "GET" or "?" not in path:
        return False
    clean = path.split("?", 1)[0].rstrip("/").lstrip("/")
    # The whole route has to be a collection. A query string alone does not
    # make a read a list, so a single pull or a ref such as
    # `repos/o/r/git/ref/heads/main?per_page=1` is never answered from the
    # cache after the branch or the pull moves.
    return any(re.fullmatch(route, clean) for route in COLLECTION_ROUTES)


def immutable(argv):
    """True when this api GET names only full commit SHAs, so it never changes."""
    path = endpoint(argv)
    if not path or method(argv) != "GET":
        return False
    route, _, query = path.lstrip("/").partition("?")
    return any(re.fullmatch(pattern, route.rstrip("/")) and any(re.fullmatch(q, query) for q in queries)
               for pattern, queries in IMMUTABLE_ROUTES)


SINGLE_OBJECT_ROUTES = (
    r"repos/[^/]+/[^/]+/(?:issues|pulls)/\d+",
    r"repos/[^/]+/[^/]+/git/ref/.+",
)


def single_object(argv):
    """True for a plain GET of one issue, pull or ref.

    These are never kept for a TTL, because the object moves. They can still
    be revalidated: a 304 is the live object, so it is always fresh."""
    if not _gh(argv) or not cache_enabled() or has_body(argv) or unknown_short_flag(argv):
        return False
    if not context(argv)[1]:
        return False
    path = endpoint(argv)
    if not path or "?" in path or method(argv) != "GET":
        return False
    return any(re.fullmatch(route, path.lstrip("/")) for route in SINGLE_OBJECT_ROUTES)


def conditional(argv):
    """True when a read can be made conditional, so a 304 costs no core call.

    A `gh api` GET of a list or of one object qualifies, and so does a
    paginated slurp read: it is probed one page at a time, and a page that
    fills up falls back to the caller's full read. A write is never
    conditional."""
    if not (cacheable(argv) or single_object(argv)):
        return False
    words = [str(word) for word in argv[1:]]
    if not words or words[0] != "api":
        return False
    # A caller that asked for the headers gets them: the conditional path
    # splits the response and would hand back only the body. `-i` is the
    # short form of `--include`.
    if include_requested(argv):
        return False
    # Only the slurp form is probed: one page is then one JSON array, and a
    # short array is the whole list.
    if paginated(argv) != has_flag(argv, "--slurp"):
        return False
    return not any(word in ("-X", "--method") for word in words)


def _etag_path(argv):
    base = Path(_ETAG_DIR()) / "gh-etag" if _ETAG_DIR else CACHE_DIR / "etag"
    return base / _key(argv)


def _read_etag(argv):
    path = _etag_path(argv)
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if (isinstance(state, dict) and isinstance(state.get("etag"), str)
            and isinstance(state.get("stdout"), str)):
        return state
    try:
        path.unlink()
    except OSError:
        pass
    return None


def _atomic_write(path, text):
    """Write one file with a temporary name of this writer's own.

    Two callers may refresh the same key at once. A shared `.tmp` path lets
    one rename the file while the other is still writing it, so the entry
    can hold a partial write. Every writer takes its own temporary file and
    the rename stays atomic."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile("w", dir=str(path.parent),
                                             prefix=path.name + ".", suffix=".tmp",
                                             delete=False)
        try:
            with handle:
                handle.write(text)
            os.replace(handle.name, path)
            return True
        except OSError:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            return False
    except OSError:
        return False


def _write_etag(argv, etag, stdout):
    _atomic_write(_etag_path(argv),
                  json.dumps({"etag": etag, "stdout": stdout}))


def _split_headers(text):
    """Return (headers, body) for the output of `gh api --include`."""
    match = re.search(r"\r?\n\r?\n", text)
    if not match:
        return "", text
    return text[:match.start()], text[match.end():]


def _status(headers):
    """Return the status code of the last response in an `--include` output.

    Only the status line counts. The body of a 200 can hold the number 304,
    and an error message can too, so a search for "304" anywhere in the
    output would answer an old body to a fresh read."""
    codes = re.findall(r"(?m)^HTTP/[\d.]+\s+(\d{3})", headers or "")
    return int(codes[-1]) if codes else None


def _per_page(argv):
    """Return the page size the endpoint asks for, or GitHub's default."""
    match = re.search(r"[?&]per_page=(\d+)", endpoint(argv))
    return int(match.group(1)) if match else 30


def _one_page(argv, body, etag):
    """Return the slurp-shaped body of a one-page read, or None for a full page.

    A page holding as many rows as it asked for may have a next page, so
    only the caller's full read can answer it."""
    try:
        rows = json.loads(body)
    except ValueError:
        rows = None
    if not isinstance(rows, list) or len(rows) >= _per_page(argv):
        _etag_path(argv).unlink(missing_ok=True)
        return None
    stdout = "[" + body.strip() + "]"
    if etag:
        _write_etag(argv, etag, stdout)
    store(argv, stdout)
    return subprocess.CompletedProcess(argv, 0, stdout, "")


def _conditional_run(argv, timeout, caller_name=None):
    """Run one api GET with If-None-Match; only a 304 answers from the file."""
    state = _read_etag(argv)
    extra = ["--include"]
    if state:
        extra += ["-H", f"If-None-Match: {state['etag']}"]
    command = argv
    if paginated(argv):
        command = [word for word in argv
                   if word.split("=", 1)[0] not in ("--paginate", "--slurp")]
    result = _launch()(command + extra, capture_output=True, text=True, timeout=timeout)
    headers, body = _split_headers(result.stdout or "")
    status = _status(headers)
    if status == 304 and state:
        # The ETag says the body is still good, so the TTL cache is renewed
        # too; without this every identical read of an unchanged list pays a
        # core call once the entry expires.
        store(argv, state["stdout"])
        record(argv, 1, caller_name, free="304")
        return subprocess.CompletedProcess(argv, 0, state["stdout"], "")
    record(argv, 1, caller_name)
    # A 2xx is not a success by itself: `gh` can fail locally after a good
    # response, as a `--jq` evaluation error does. Only a command that
    # exited zero may write either cache, or the next identical read would
    # be answered with a cached error and exit zero.
    if result.returncode == 0 and status is not None and 200 <= status < 300:
        header = re.search(r"(?im)^etag:\s*(\S+)\s*$", headers)
        if paginated(argv):
            return _one_page(argv, body, header.group(1) if header else "")
        if header:
            _write_etag(argv, header.group(1), body)
        # Keep the body for the short TTL as well. A response with no ETag
        # would otherwise make the next identical read a fresh core call.
        store(argv, body)
    return subprocess.CompletedProcess(argv, result.returncode, body, result.stderr)


def cached_login(directory, read):
    """The authenticated login, read once and kept in `directory`.

    `read` is the caller's own lookup and runs only when no login is on disk."""
    login_file = Path(directory) / "gh-login"
    try:
        login = login_file.read_text().strip()
    except OSError:
        login = ""
    if not login:
        login = read()
        _atomic_write(login_file, login)
    return login


def _hosts_account(host):
    """Return the account `gh` is signed in as for one host, or "".

    The answer is read from gh's own hosts file, so no GitHub call is made.
    A name that cannot be read is an unknown context, and an unknown
    context is never cached: two accounts must not share an entry."""
    config = os.environ.get("GH_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".config", "gh")
    try:
        lines = open(os.path.join(config, "hosts.yml")).read().splitlines()
    except OSError:
        return ""
    current = ""
    # Only the host-level field counts: `hosts.yml` keeps a `users:` map
    # beneath the host, and its entries are indented deeper. Reading the
    # first `user:` anywhere would answer with an inactive account.
    candidates = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            current = line.split(":", 1)[0].strip()
            continue
        if current != host:
            continue
        indent = len(line) - len(line.lstrip())
        key, _, value = line.strip().partition(":")
        if key.strip() == "user" and value.strip():
            candidates.append((indent, value.strip()))
    if not candidates:
        return ""
    shallowest = min(indent for indent, _value in candidates)
    names = {value for indent, value in candidates if indent == shallowest}
    # More than one host-level name is ambiguous, so no account is claimed.
    return names.pop() if len(names) == 1 else ""


# Every variable `gh` accepts a credential from. A fingerprint covers all
# of them, so switching a fallback token changes the cache key too.
TOKEN_VARS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN",
              "GITHUB_ENTERPRISE_TOKEN")


def _token_id():
    """Return a short fingerprint of the credentials in the environment.

    The value is never kept, only a hash of every credential variable that
    is set, so any change of identity changes the key."""
    import hashlib
    tokens = [os.environ.get(name) or "" for name in TOKEN_VARS]
    if not any(tokens):
        return ""
    return hashlib.sha256("\0".join(tokens).encode()).hexdigest()[:16]


def argv_host(argv):
    """Return the host a command targets, or "" when it names none.

    Two forms name a host: `--hostname HOST`, and a repository selector with
    a host in it, `-R HOST/OWNER/REPO` (or `GH_REPO`). Both decide which
    host's quota and account apply."""
    words = [str(word) for word in (argv or [])[1:]]
    for index, word in enumerate(words):
        if word == "--hostname" and index + 1 < len(words):
            return words[index + 1]
        if word.startswith("--hostname="):
            return word.split("=", 1)[1]
    selector = os.environ.get("GH_REPO") or ""
    for index, word in enumerate(words):
        if word in ("-R", "--repo") and index + 1 < len(words):
            selector = words[index + 1]
        elif word.startswith("--repo="):
            selector = word.split("=", 1)[1]
    parts = selector.split("/")
    if len(parts) == 3 and parts[0]:
        return parts[0]
    return ""


def context(argv=None):
    """Return (host, identity, checkout, repo_override, token_id) for a call.

    `gh pr list` resolves its repository from the working directory and its
    account from a credential variable or gh's hosts file, so two identical
    commands under different overrides are different reads. A command that
    names a host with `--hostname` is answered by that host's account, not
    the default one. A credential is kept as a fingerprint of every
    variable that is set, never as a value."""
    host = argv_host(argv) or os.environ.get("GH_HOST") or "github.com"
    account = os.environ.get("COORDINATOR_GH_ACCOUNT") or _hosts_account(host)
    repo_override = os.environ.get("GH_REPO") or ""
    return host, account, os.getcwd(), repo_override, _token_id()


def _key(argv):
    import hashlib
    # The key follows the command's own host, so a `--hostname` read is
    # keyed by that host's account and cannot answer another account's read.
    host, account, checkout, repo_override, token_id = context(argv)
    parts = [host, account, checkout, repo_override, token_id] + [str(word) for word in argv]
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()


def cached(argv):
    """Return a fresh cached stdout for this read, or None when it must run."""
    if not cacheable(argv):
        return None
    path = CACHE_DIR / _key(argv)
    try:
        entry = json.loads(path.read_text())
        if float(entry["expiry"]) < time.time():
            return None
        return entry["stdout"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def store(argv, stdout):
    """Keep one read's output for the rest of its TTL."""
    if not cacheable(argv) or not isinstance(stdout, str):
        return
    _atomic_write(CACHE_DIR / _key(argv),
                  json.dumps({"expiry": time.time() + (IMMUTABLE_TTL if immutable(argv) else LIST_TTL),
                            "stdout": stdout}))


def filtered(argv):
    """True when the command formats its output, so pages are not JSON."""
    if has_flag(argv, "--silent") or has_flag(argv, "--verbose"):
        return True
    for word in significant(argv):
        if word in OUTPUT_FILTER_FLAGS:
            return True
        if word.startswith(("--jq=", "--template=", "-q=")):
            return True
        # The short flags also take their value attached, as `-q.[].name`
        # and `-t{{.name}}`.
        if len(word) > 2 and word.startswith(("-q", "-t")):
            return True
    return False


# A real response block is a status line followed by at least one header
# line and a blank line. The header line is what tells a block apart from a
# body that happens to start with text such as `HTTP/1.1 200 OK`, which is
# user data and must be neither counted nor removed.
_HEADER_CANDIDATE = re.compile(
    r"(?m)^HTTP/[\d.]+\s+\d{3}[^\n]*\n(?:[^:\n]+:[^\n]*\n)*\n")
# A real gh response block carries a GitHub or rate-limit header. That is
# what tells it apart from a body that prints a header-shaped block itself,
# which is user data and must be neither counted nor removed.
_GITHUB_HEADER = re.compile(r"(?im)^(?:x-github-|x-ratelimit-)")


def _header_blocks(text):
    return [match for match in _HEADER_CANDIDATE.finditer(text or "")
            if _GITHUB_HEADER.search(match.group(0))]


def status_lines(text):
    """Return how many response blocks an `--include` output holds.

    One block is one request, whatever the output formatting did to the
    body, so this is the page count before formatting. A header block only
    counts when it carries a header line, so body text is not a page."""
    return len(_header_blocks(text))


def strip_headers(text):
    """Remove every real `--include` header block, keeping the bodies.

    Only a block with a header line is removed, so a body that begins with
    `HTTP/1.1 200 OK` and a blank line survives in the caller's output."""
    text = text or ""
    kept, position = [], 0
    for block in _header_blocks(text):
        kept.append(text[position:block.start()])
        position = block.end()
    kept.append(text[position:])
    return "".join(kept)


def requests(argv, stdout, floor=True):
    """Return the number of GitHub requests one command made.

    A paginated read makes one request per page. With `--slurp` the pages
    are the elements of one JSON array; without it they are the JSON values
    written one after another. A read that is not paginated is one request.
    """
    if not _gh(argv):
        return 0
    words = significant(argv)
    if not paginated(argv) or not words or words[0] != "api":
        # Only an api read prints pages we can count. A search read counts
        # its pages the same way, whatever quota it spends.
        return 1 if floor else 0
    if has_flag(argv, "--slurp"):
        # gh writes the pages as one JSON array here, so the pages are its
        # elements and not one value.
        try:
            pages = json.loads((stdout or "").strip() or "[]")
        except ValueError:
            pages = None
        if isinstance(pages, list):
            return max(1, len(pages)) if floor else len(pages)
        # A short read can print fewer pages than `--slurp` expects, so the
        # text is counted page by page below.
    decoder = json.JSONDecoder()
    text = (stdout or "").strip()
    count, index = 0, 0
    while index < len(text):
        try:
            _, end = decoder.raw_decode(text, index)
        except ValueError:
            break
        count += 1
        index = end
        while index < len(text) and text[index].isspace():
            index += 1
    return max(1, count) if floor else count


def prepare(argv):
    """Return (command to run, headers_counted) for one read.

    The gateway never adds `--include` itself. A formatted paginated read
    prints text the caller controls, and no amount of header-shaped text in
    it can be told apart from a real response header, so counting from that
    output would either miscount or delete the caller's own words. Such a
    read is counted as the one request it starts with; the caller's output
    is returned exactly as gh wrote it. A caller that asks for `--include`
    itself still gets its headers counted, because then the output is what
    it asked for."""
    return list(argv), False


def settle(argv, stdout, headers_counted, failed=False):
    """Return (body, count) for one read that has already run.

    A paginated read that failed part way still made the request that
    failed, so that request is counted too: the pages it printed are the
    ones that succeeded."""
    stdout = stdout or ""
    if headers_counted:
        pages = status_lines(stdout)
        return (strip_headers(stdout),
                max(1, pages + _failed_request(argv, failed, pages, True, stdout)))
    # Unreachable today: the gateway never adds the header flag. Kept so a
    # caller that adds it itself is handled by the branch below.
    if paginated(argv):
        # The rule follows the output shape, not the quota bucket: a filtered
        # search read prints the caller's text just as a core read does.
        has_include = include_requested(argv)
        if filtered(argv):
            # A filtered body is the caller's text. It cannot be counted by
            # parsing (the text may print anything) and it is not counted by
            # a replay (that spends quota, can double-charge, and would send
            # a write twice if the method were ever misread). So the read is
            # one invocation with an unknown page count, and the report
            # labels the totals it feeds as lower bounds.
            return stdout, 1
        if has_include:
            # Unfiltered pages are JSON, so a header block is a real one.
            pages = status_lines(stdout)
            return stdout, max(1, pages + _failed_request(argv, failed, pages, True, stdout))

    # Nothing here ever re-runs the command. A replay could send a write
    # twice, and a second pagination would spend quota to learn a count.
    # A formatted read is measured as the one invocation it is, and the row
    # says its page count is unknown rather than guessing.
    pages = requests(argv, stdout, floor=False)
    if filtered(argv) and paginated(argv):
        # The formatted output is not a page list: one page of ten issues
        # with `--jq '.[].number'` prints ten numbers, and the JSON reader
        # would call those ten pages. One invocation, one row.
        return stdout, 1 + _failed_request(argv, failed, pages)
    return stdout, max(1, pages + _failed_request(argv, failed, pages))


def _last_status(text):
    """Return the last HTTP status in a header-carrying output, or None."""
    codes = re.findall(r"(?m)^HTTP/[\d.]+\s+(\d{3})", text or "")
    return int(codes[-1]) if codes else None


def _failed_request(argv, failed, pages, header_blocks=False, stdout=""):
    """One extra request when a paginated core read stopped on an error.

    `pages` is the number of pages already counted from the output. Only
    when a page got through: a read whose first request failed made exactly
    one attempt, and counting the failure as well would log two."""
    if not (failed and paginated(argv) and resource(argv) == CORE):
        return 0
    if header_blocks:
        # A failed response that printed its own header block is already in
        # the block count. When no error block was printed, the attempt is
        # still missing, so it is added here.
        status = _last_status(stdout)
        return 0 if status is not None and status >= 400 else 1
    return 1 if pages else 0


def pages_unknown(argv):
    """True when a read's page count cannot be known.

    A CLI command such as `gh run list --limit 200` fetches as many pages as
    it needs without `--paginate`, so one invocation is not one request.
    Only `gh api` is counted exactly from its own output.

    A formatted paginated read prints the caller's text, so neither the
    body nor a replay can tell how many pages it took. The row says so
    instead of pretending to a number."""
    if not _gh(argv):
        return False
    words = significant(argv)
    if words and words[0] != "api":
        return True
    if paginated(argv) and filtered(argv):
        return True
    if (paginated(argv) and not has_flag(argv, "--slurp")
            and not include_requested(argv)):
        # Without slurp the pages arrive as several JSON values, but gh may
        # also hand back one array for several pages. The boundaries are not
        # visible, so the count is a lower bound.
        return True
    return False


def record(argv, count=1, caller_name=None, via=None, free=None):
    """Write one usage-log line per GitHub core request the command made.

    A 304 or a cache hit is passed with `free` and is logged as one row of
    `cost` 0, so the report can tell paid calls from free ones. The quota
    the request spends is on the row, so the report never counts a search
    or a GraphQL read as a core call."""
    if not _gh(argv) or count <= 0:
        return
    # No argument is written: `gh api -H "Authorization: ..."` carries a
    # credential in one. The caller, the quota and the verb are enough for
    # the report and safe to keep.
    row = {"ts": round(time.time(), 3), "caller": caller_name or caller(),
           "resource": resource(argv), "verb": verb(argv),
           "route": route(argv), "call": uuid.uuid4().hex[:12]}
    if free:
        row["cost"] = 0
        row["cache"] = free
    if via:
        row["via"] = via
    if pages_unknown(argv):
        row["pages"] = "unknown"
    line = json.dumps(row)
    lines = (line + "\n") * count
    # The size check, the rotation and the append are one critical section
    # under a lock. Without it two callers can both see a full log: the
    # first rotates it, and the second replaces `.1` with the new, nearly
    # empty log, destroying the retained history the report reads.
    lock_path = USAGE_LOG.with_suffix(USAGE_LOG.suffix + ".lock")
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                if USAGE_LOG.exists() and USAGE_LOG.stat().st_size > USAGE_LOG_MAX:
                    os.replace(USAGE_LOG, USAGE_LOG.with_suffix(USAGE_LOG.suffix + ".1"))
                with open(USAGE_LOG, "a") as handle:
                    handle.write(lines)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    except OSError:
        return


def quota_key(host=None):
    """Return the identity a quota sample belongs to, or "" if unknown.

    The token, the host, the gh configuration directory and the account the
    configuration selects can all change inside a long-lived process. A
    balance read for one identity must not set the floor for another, and an
    identity that cannot be established is never reused."""
    host = host or os.environ.get("GH_HOST") or "github.com"
    account = os.environ.get("COORDINATOR_GH_ACCOUNT") or _hosts_account(host)
    if not account:
        return ""
    config = os.environ.get("GH_CONFIG_DIR") or ""
    return "|".join([host, account, config, _token_id()])


def api_remaining(timeout=60, host=None):
    """Return the remaining core and graphql calls for one host, or raise."""
    now = time.time()
    key = quota_key(host)
    entry = _REMAINING.get(key) if key else None
    if entry and entry["at"] and now - entry["at"] < _REMAINING_TTL:
        return dict(entry["value"])
    try:
        probe = ["gh", "api", "rate_limit"]
        if host:
            # The reserve belongs to the host the request targets.
            probe += ["--hostname", host]
        result = _launch()(probe, capture_output=True,
                           text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ApiBudgetExhausted("quota could not be read") from exc
    if result.returncode:
        raise ApiBudgetExhausted("quota could not be read")
    try:
        resources = json.loads(result.stdout)["resources"]
        value = {name: int(resources[name]["remaining"]) for name in ("core", "graphql")}
    except (ValueError, KeyError, TypeError) as exc:
        raise ApiBudgetExhausted("quota response is invalid") from exc
    if key:
        _REMAINING[key] = {"at": now, "value": value}
    return dict(value)


def remaining_or_none(timeout=60, host=None):
    """Return the quota, or None when it cannot be read.

    A caller that only skips optional reads uses this: a quota it cannot
    read is not a reason to stop the work, and a read that matters still
    fails on its own when GitHub refuses it. The timeout is the caller's,
    so a probe inside a deadline cannot outlast it."""
    try:
        return api_remaining(timeout=timeout, host=host)
    except ApiBudgetExhausted:
        return None


def require_budget(limit=None):
    """Raise when the quota is below the caller's floor."""
    limit = floor() if limit is None else limit
    remaining = api_remaining()
    if min(remaining.values()) < limit:
        raise ApiBudgetExhausted(
            f"optional reads stopped: remaining={remaining}, floor={limit}")
    return remaining


def guard_floor(limit=None, timeout=60, host=None):
    """Raise only when the quota is known to be below the floor.

    A quota that cannot be read does not stop a read: the read fails on its
    own if GitHub refuses it, and a failed rate-limit read is not evidence
    that the quota is gone."""
    remaining = remaining_or_none(timeout=timeout, host=host)
    limit = floor() if limit is None else limit
    if remaining and min(remaining.values()) < limit:
        raise ApiBudgetExhausted(
            f"optional reads stopped: remaining={remaining}, floor={limit}")
    return remaining


def below_floor(limit=None):
    """True when the quota is known and under the floor."""
    remaining = remaining_or_none()
    return bool(remaining) and min(remaining.values()) < (floor() if limit is None else limit)


def run(argv, timeout=60, stdin=None, limit=None, fresh=False, caller_name=None):
    """Run one GitHub command, from the cache when it is a repeated read.

    The result is a `CompletedProcess`, so a caller keeps its own error
    handling: this function does not decide whether a failed read is a
    refusal or a skip. A `fresh` read is never answered from the short-TTL
    cache, so a caller that must see what GitHub has now is never given an
    old list; its own answer refreshes the entry for everyone else."""
    # A cache hit answers without reading the quota, so a stalled quota
    # probe cannot delay a read that is already paid for.
    if not fresh:
        hit = cached(argv)
        if hit is not None:
            record(argv, 1, caller_name, free="hit")
            return subprocess.CompletedProcess(argv, 0, hit, "")
    started = time.monotonic()
    if limit is not None:
        # The probe and the read share one deadline: the probe gets half of
        # it, and the read gets whatever is left.
        guard_floor(limit, timeout=max(1, int(timeout) // 2),
                    host=argv_host(argv) or None)
        timeout = max(1, int(timeout - (time.monotonic() - started)))
    if stdin is None and conditional(argv):
        answered = _conditional_run(argv, timeout, caller_name)
        if answered is not None:
            return answered
    command, headers_counted = prepare(argv) if stdin is None else (list(argv), False)
    result = _launch()(command, input=stdin, capture_output=True, text=True,
                       timeout=timeout)
    # A caller's launcher need not be a real CompletedProcess, so every part
    # is read with a default.
    stdout = getattr(result, "stdout", "") or ""
    body, count = settle(argv, stdout, headers_counted,
                         failed=getattr(result, "returncode", 0) != 0)
    record(argv, count, caller_name)
    if result.returncode == 0:
        store(argv, body)
    return subprocess.CompletedProcess(argv, result.returncode, body,
                                       getattr(result, "stderr", "") or "")


def usage_rows(hours, now=None, by="caller"):
    """Count paid calls per hour and caller (or per route) over the last `hours` hours.

    A call is one invocation: `record` writes one row per page, so rows
    sharing a `call` id are one call. A row from before the id existed is
    its own call. A row of cost 0 is a 304 or a cache hit: it is counted
    apart as free and never as a call."""
    since = (now or time.time()) - hours * 3600
    table = {}
    for number, path in enumerate((USAGE_LOG.with_suffix(USAGE_LOG.suffix + ".1"), USAGE_LOG)):
        if not path.exists():
            continue
        for index, line in enumerate(path.read_text().splitlines()):
            row = json.loads(line)
            if row["ts"] < since:
                continue
            hour = time.strftime("%Y-%m-%d %H:00", time.localtime(row["ts"]))
            key = (hour, row["caller"]) if by == "caller" else (row.get("route") or "unknown",)
            cell = table.setdefault(key, {"calls": {}, "pages": 0, "free": 0})
            if row.get("cost") == 0:
                cell["free"] += 1
                continue
            call = row.get("call") or f"{number}:{index}"
            cell["calls"][call] = (row["resource"] if row["resource"] in ("core", "graphql") else "other", row.get("via") == "shim")
            cell["pages"] += 1
    if by == "route":
        return sorted(table.items(), key=lambda item: -len(item[1]["calls"]))
    return sorted(table.items())


def usage_report(hours, by="caller"):
    if by == "route":
        lines = [f"{'route':<56} {'paid':>6} {'free':>6}"]
        for (name,), cell in usage_rows(hours, by=by):
            lines.append(f"{name:<56} {len(cell['calls']):>6} {cell['free']:>6}")
        return "\n".join(lines)
    header = f"{'hour':<17} {'caller':<24} {'core':>6} {'graphql':>8} {'other':>6} {'pages':>6} {'free':>6} {'via shim (bypassed the gateway)':>32}"
    lines = [header]
    for (hour, name), cell in usage_rows(hours):
        kinds = [kind for kind, _shim in cell["calls"].values()]
        shim = sum(shim for _kind, shim in cell["calls"].values())
        lines.append(f"{hour:<17} {name:<24} {kinds.count('core'):>6} {kinds.count('graphql'):>8} {kinds.count('other'):>6} {cell['pages']:>6} {cell['free']:>6} {shim:>32}")
    return "\n".join(lines)


if __name__ == "__main__":
    if sys.argv[1:2] == ["log-shim"]:
        record(["gh", *sys.argv[3:]], caller_name=sys.argv[2] or "unknown", via="shim")
        sys.exit(0)
    parser = argparse.ArgumentParser(description="GitHub call usage")
    parser.add_argument("command", choices=["usage"])
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--by", choices=["caller", "route"], default="caller")
    args = parser.parse_args()
    print(usage_report(args.hours, args.by))
