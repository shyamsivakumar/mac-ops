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
import json
import os
import re
import subprocess
import sys
import time
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
               "ruleset", "gist", "codespace", "repo", "attestation",
               "ssh-key", "gpg-key", "auth")
GRAPHQL_GROUPS = ("pr", "issue", "project", "label", "org")
# The `gh api` flags that take a value, so the endpoint can be found and the
# method can be read without mistaking a value for the endpoint.
VALUE_FLAGS = ("-X", "--method", "-H", "--header", "-f", "-F", "--field",
               "--raw-field", "--input", "-q", "--jq", "-t", "--template",
               "--cache")
BODY_FLAGS = ("-f", "-F", "--field", "--raw-field", "--input")


def has_body(argv):
    """True when the command carries a request body, so it is a write.

    `gh` accepts the value attached (`--raw-field=name=value`, `-fname=value`)
    or as the next word; both are the same POST, and neither may be cached."""
    for word in [str(token) for token in argv[1:]]:
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
USAGE_LOG_MAX = 4 * 1024 * 1024
_CALLER = None
# A caller whose tests replace its own `subprocess` name hands the helper a
# getter for the launcher, so every gh call still goes through the one it
# can see. Resolved at call time, never captured at import time.
_RUNNER = None
_REMAINING = {"at": 0.0, "value": None}
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


def _launch():
    return _RUNNER() if _RUNNER else subprocess.run


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


def method(argv):
    """Return the HTTP method `gh api` will use, as GitHub counts it.

    `gh api` reads unless a method is named or a field is given; a field
    without a method is a POST, and `-X GET` overrides a field."""
    words = [str(word) for word in argv[1:]]
    for index, word in enumerate(words):
        # `--method=POST` and `-XPOST` are the same method as `-X POST`.
        if word.startswith("--method="):
            return word.split("=", 1)[1].strip().upper()
        if word.startswith("-X") and len(word) > 2:
            return word[2:].lstrip("=").strip().upper()
        if word in ("-X", "--method"):
            return words[index + 1].strip().upper() if index + 1 < len(words) else ""
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
        if path.startswith("search/") or "/search/" in path:
            return SEARCH
        if path == "graphql" or "graphql" in words:
            return GRAPHQL
        return CORE
    if words[0] in REST_GROUPS:
        return CORE
    if words[0] in GRAPHQL_GROUPS:
        return GRAPHQL
    return "other"


def cacheable(argv):
    """True when a repeated read of this command may be served from cache."""
    if not _gh(argv) or not cache_enabled():
        return False
    words = [str(word) for word in argv[1:]]
    if not words:
        return False
    if any(word in CREDENTIAL_FLAGS for word in argv[1:]):
        # `gh auth status --show-token` prints a token: never written down.
        return False
    if has_body(argv):
        # A body means a write, and a write is never served from a cache.
        return False
    host, account, checkout, repo_override, token_id = context()
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
    path = endpoint(argv)
    if method(argv) != "GET" or "?" not in path:
        return False
    # A single pull or issue path may carry a head SHA into a merge
    # decision, so it is never cached or answered from an ETag.
    return re.match(r"^repos/[^/]+/[^/]+/(?:pulls|issues)/\d+", path.lstrip("/")) is None


def conditional(argv):
    """True when a read can be made conditional, so a 304 costs no core call.

    Only a single-page `gh api` GET qualifies: a paginated read answers with
    one header block per page, and a write is never conditional."""
    if not cacheable(argv):
        return False
    words = [str(word) for word in argv[1:]]
    if not words or words[0] != "api":
        return False
    return not any(word in ("--paginate", "--slurp", "-X", "--method") for word in words)


def _etag_path(argv):
    return CACHE_DIR / "etag" / _key(argv)


def _read_etag(argv):
    try:
        state = json.loads(_etag_path(argv).read_text())
        return state if isinstance(state, dict) and state.get("etag") else None
    except (OSError, ValueError):
        return None


def _write_etag(argv, etag, stdout):
    try:
        path = _etag_path(argv)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"etag": etag, "stdout": stdout}))
        os.replace(tmp, path)
    except OSError:
        return


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


def _conditional_run(argv, timeout):
    """Run one api GET with If-None-Match; only a 304 answers from the file."""
    state = _read_etag(argv)
    extra = ["--include"]
    if state:
        extra += ["-H", f"If-None-Match: {state['etag']}"]
    result = _launch()(argv + extra, capture_output=True, text=True, timeout=timeout)
    headers, body = _split_headers(result.stdout or "")
    status = _status(headers)
    if status == 304 and state:
        return subprocess.CompletedProcess(argv, 0, state["stdout"], "")
    record(argv, 1)
    if status is not None and 200 <= status < 300:
        header = re.search(r"(?im)^etag:\s*(\S+)\s*$", headers)
        if header:
            _write_etag(argv, header.group(1), body)
    return subprocess.CompletedProcess(argv, result.returncode, body, result.stderr)


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
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            current = line.split(":", 1)[0].strip()
        elif current == host:
            key, _, value = line.strip().partition(":")
            if key.strip() == "user" and value.strip():
                return value.strip()
    return ""


def _token_id(token):
    """Return a short fingerprint of a token, never the token itself."""
    if not token:
        return ""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def context():
    """Return (host, identity, checkout, repo_override, token_id) for this call.

    `gh pr list` resolves its repository from the working directory and its
    account from `GH_TOKEN` or gh's hosts file, so two identical commands
    under different overrides are different reads. The token is kept as a
    fingerprint, never as the value."""
    host = os.environ.get("GH_HOST") or "github.com"
    account = os.environ.get("COORDINATOR_GH_ACCOUNT") or _hosts_account(host)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GH_ENTERPRISE_TOKEN") or ""
    repo_override = os.environ.get("GH_REPO") or ""
    return host, account, os.getcwd(), repo_override, _token_id(token)


def _key(argv):
    import hashlib
    host, account, checkout, repo_override, token_id = context()
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
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / _key(argv)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"expiry": time.time() + LIST_TTL, "stdout": stdout}))
        os.replace(tmp, path)
    except OSError:
        return


def requests(argv, stdout):
    """Return the number of GitHub requests one command made.

    A paginated read makes one request per page. With `--slurp` the pages
    are the elements of one JSON array; without it they are the JSON values
    written one after another. A read that is not paginated is one request.
    """
    if not _gh(argv):
        return 0
    if "--paginate" not in argv or resource(argv) != "core":
        return 1
    if "--slurp" in argv:
        # gh writes the pages as one JSON array here, so the pages are its
        # elements and not one value.
        try:
            pages = json.loads((stdout or "").strip() or "[]")
        except ValueError:
            return 1
        return max(1, len(pages)) if isinstance(pages, list) else 1
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
    return max(1, count)


def record(argv, count=1):
    """Write one usage-log line per GitHub core request the command made.

    A 304 is not a core call and is never passed here, so the log holds
    what was spent and not what was wanted. The quota the request spends is
    on the row, so the report never counts a search or a GraphQL read as a
    core call."""
    if not _gh(argv) or count <= 0:
        return
    # No argument is written: `gh api -H "Authorization: ..."` carries a
    # credential in one. The caller, the quota and the verb are enough for
    # the report and safe to keep.
    line = json.dumps({"ts": round(time.time(), 3), "caller": caller(),
                       "resource": resource(argv), "verb": verb(argv)})
    try:
        if USAGE_LOG.exists() and USAGE_LOG.stat().st_size > USAGE_LOG_MAX:
            os.replace(USAGE_LOG, USAGE_LOG.with_suffix(".jsonl.1"))
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(USAGE_LOG, "a") as handle:
            for _ in range(count):
                handle.write(line + "\n")
    except OSError:
        return


def api_remaining(timeout=60):
    """Return the remaining core and graphql calls, or raise."""
    now = time.time()
    if _REMAINING["value"] is not None and now - _REMAINING["at"] < _REMAINING_TTL:
        return dict(_REMAINING["value"])
    try:
        result = _launch()(["gh", "api", "rate_limit"], capture_output=True,
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
    _REMAINING.update(at=now, value=value)
    return dict(value)


def remaining_or_none():
    """Return the quota, or None when it cannot be read.

    A caller that only skips optional reads uses this: a quota it cannot
    read is not a reason to stop the work, and a read that matters still
    fails on its own when GitHub refuses it."""
    try:
        return api_remaining()
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


def guard_floor(limit=None):
    """Raise only when the quota is known to be below the floor.

    A quota that cannot be read does not stop a read: the read fails on its
    own if GitHub refuses it, and a failed rate-limit read is not evidence
    that the quota is gone."""
    remaining = remaining_or_none()
    limit = floor() if limit is None else limit
    if remaining and min(remaining.values()) < limit:
        raise ApiBudgetExhausted(
            f"optional reads stopped: remaining={remaining}, floor={limit}")
    return remaining


def below_floor(limit=None):
    """True when the quota is known and under the floor."""
    remaining = remaining_or_none()
    return bool(remaining) and min(remaining.values()) < (floor() if limit is None else limit)


def run(argv, timeout=60, stdin=None, limit=None):
    """Run one GitHub command, from the cache when it is a repeated read.

    The result is a `CompletedProcess`, so a caller keeps its own error
    handling: this function does not decide whether a failed read is a
    refusal or a skip."""
    if limit is not None:
        guard_floor(limit)
    hit = cached(argv)
    if hit is not None:
        return subprocess.CompletedProcess(argv, 0, hit, "")
    if stdin is None and conditional(argv):
        return _conditional_run(argv, timeout)
    result = _launch()(argv, input=stdin, capture_output=True, text=True,
                       timeout=timeout)
    record(argv, requests(argv, result.stdout))
    if result.returncode == 0:
        store(argv, result.stdout)
    return result
