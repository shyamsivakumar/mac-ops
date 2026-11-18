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
CACHEABLE_COMMANDS = ("list", "search", "status")
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


def cacheable(argv):
    """True when a repeated read of this command may be served from cache."""
    if not _gh(argv) or not cache_enabled():
        return False
    words = [str(word) for word in argv[1:]]
    if not words:
        return False
    if words[0] in CACHEABLE_COMMANDS:
        return True
    # A paginated read of a list endpoint is a list read. A single pull or
    # issue path is not: it may carry a head SHA into a merge decision.
    return (words[0] == "api" and any("?" in word for word in words)
            and not any("/pulls/" in word or "/issues/" in word for word in words))


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


def _key(argv):
    import hashlib
    return hashlib.sha256("\0".join(str(word) for word in argv).encode()).hexdigest()


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
    if "--paginate" not in argv:
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
    what was spent and not what was wanted."""
    if not _gh(argv) or count <= 0:
        return
    line = json.dumps({"ts": round(time.time(), 3), "caller": caller(),
                       "command": [str(word) for word in argv[1:4]]})
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
