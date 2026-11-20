# MO-681: which side served the stale issue list

`ticket open` mints a key from the repo's issue list, read with `fresh=True`
(`coordinator/bin/ticket`, `repo_issues`). On 2026-11-19 six sequential opens,
each finished before the next started under the per-repo open lock, produced
three duplicate keys: #675/#676 both MO-1117, #677/#678 both MO-1118,
#679/#680 both MO-1119. The list read seconds after a create did not include
the issue just made.

Two candidates: GitHub's issue list lags the create, or the gateway's
conditional (ETag) path answered a `fresh` read from its stored page.

## What the code does

`gh_gateway.run(..., fresh=True)` skips only the short-TTL answer:

```python
if not fresh:
    hit = cached(argv)
    if hit is not None:
        ...
if stdin is None and conditional(argv):
    return _conditional_run(argv, timeout, caller_name)
```

So a `fresh` read still goes through `_conditional_run`, which sends
`If-None-Match` and, on a 304, returns the body it stored with that ETag.
That is the only path by which a `fresh` read can return an older body.

## The replay

The real `gh_gateway.run` is driven with `fresh=True` against a fake GitHub
that keeps one ETag per page and answers 304 when the caller's
`If-None-Match` matches. Two worlds are replayed, and in both the create
lands between the first and the second read:

- **lagging**: GitHub's list has not caught up, so the body and the ETag are
  unchanged and the answer is 304.
- **current**: GitHub's list has caught up, so the body and the ETag both
  move and the answer is 200.

```python
import importlib.machinery, importlib.util, json, os, subprocess, tempfile
from pathlib import Path

PATH = "coordinator/bin/gh_gateway.py"

def load():
    loader = importlib.machinery.SourceFileLoader("gw", PATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod

class FakeGitHub:
    """One issues list page, with an ETag that moves only when the body does."""
    def __init__(self, body, etag):
        self.body, self.etag, self.requests = body, etag, []

    def create(self, body, etag):
        self.body, self.etag = body, etag

    def __call__(self, argv, **kwargs):
        words = [str(w) for w in argv]
        sent = None
        for i, w in enumerate(words):
            if w == "-H" and i + 1 < len(words) and words[i + 1].lower().startswith("if-none-match:"):
                sent = words[i + 1].split(":", 1)[1].strip()
        self.requests.append({"if_none_match": sent, "include": "--include" in words})
        if "--include" not in words:
            # A plain read gets the body alone, as `gh api` prints it.
            return subprocess.CompletedProcess(argv, 0, self.body, "")
        if sent and sent == self.etag:
            return subprocess.CompletedProcess(argv, 0, "HTTP/2.0 304 Not Modified\netag: %s\n\n" % self.etag, "")
        return subprocess.CompletedProcess(argv, 0, "HTTP/2.0 200 OK\netag: %s\n\n%s" % (self.etag, self.body), "")

def world(name, lagging, conditional=True):
    gw = load()
    tmp = tempfile.mkdtemp(prefix="mo681-")
    os.environ["COORDINATOR_GH_CACHE"] = "1"
    os.environ["COORDINATOR_GH_CACHE_DIR"] = os.path.join(tmp, "cache")
    os.environ["COORDINATOR_GH_USAGE_LOG"] = os.path.join(tmp, "usage.jsonl")
    gw.CACHE_DIR = Path(os.environ["COORDINATOR_GH_CACHE_DIR"])
    gw.USAGE_LOG = Path(os.environ["COORDINATOR_GH_USAGE_LOG"])
    gw._REMAINING.clear()
    before = json.dumps([{"number": 1, "title": "MO-1 · one"}])
    after = json.dumps([{"number": 2, "title": "MO-2 · two"}, {"number": 1, "title": "MO-1 · one"}])
    github = FakeGitHub(before, '"e1"')
    gw._RUNNER = lambda: github
    if not conditional:
        # The same read with the conditional path turned off.
        gw.conditional = lambda argv: False
    argv = ["gh", "api", "repos/o/r/issues?state=all&per_page=100&page=1"]
    first = gw.run(argv, fresh=True)
    github.create(before if lagging else after, '"e1"' if lagging else '"e2"')
    second = gw.run(argv, fresh=True)
    third = gw.run(argv, fresh=False)
    return {"world": name,
            "first_read": json.loads(first.stdout),
            "fresh_read_after_create": json.loads(second.stdout),
            "plain_read_after_create": json.loads(third.stdout),
            "requests": github.requests,
            "usage": [json.loads(l) for l in open(os.environ["COORDINATOR_GH_USAGE_LOG"])]}

print(json.dumps([world("lagging", True), world("current", False),
                  world("lagging, no conditional path", True, conditional=False)], indent=1))
```

## What the replay found

| world | first read | fresh read after the create | requests | usage rows (cost, cache) |
| --- | --- | --- | --- | --- |
| lagging | `MO-1 · one` | `MO-1 · one` | no `If-None-Match`, then `If-None-Match: "e1"` | paid, then `0 / 304`, then `0 / hit` |
| current | `MO-1 · one` | `MO-2 · two`, `MO-1 · one` | no `If-None-Match`, then `If-None-Match: "e1"` | paid, then paid, then `0 / hit` |
| lagging, no conditional path | `MO-1 · one` | `MO-1 · one` | no `If-None-Match` on either read | paid, then paid, then `0 / hit` |

What the replay settles, and what it does not:

- It settles that `fresh=True` skips the short-TTL cache: in the current world
  the second read is a paid call, not a `hit`.
- It settles that the conditional path is not what makes a `fresh` read stale.
  With the conditional path turned off, a lagging list still answers with the
  old body, and the read is a paid call with no `If-None-Match` at all. The
  conditional path only saves the core call when GitHub says the page is
  unchanged, and it then returns the body it stored with that ETag, which is
  exactly what GitHub said was current.
- It does **not** settle which response GitHub sent during the six opens on
  2026-11-19. The fake chooses whether the body and the ETag advance, so the
  lagging world is a model of GitHub's eventual consistency, not a recording
  of it. The usage log for that day predates the `cost` field, so it cannot
  tell a 304 from a paid call either.

So upstream lag is consistent with the evidence and with the gateway's code,
and the gateway is not shown to be at fault; the incident's exact cause stays
unconfirmed. Either way the client cannot make GitHub's list catch up, so the
fix is to stop trusting the list alone.

## The fix, and the replay that proves it

`coordinator/bin/ticket` keeps `last-key-<repo>-<prefix>.json` in `CACHE_DIR`,
written under the open lock, holding:

- `number`: the highest key number this repo has given out under that prefix.
- `unconfirmed`: the numbers given out that the issue list has not shown yet.
- `pending`: the number of a create whose answer has not come back.

The mint goes one past `max(listed keys, number)`. An explicit key is refused
when the list or `unconfirmed` already holds it. The record is written before
the create and cleared after it, so a create that lands and then loses its
answer leaves the key pending and the next open refuses until a human checks
the repo. Only a failure that establishes rejection (`auth`, `budget`,
`rate_limit`) puts the record back and frees the key; a generic `error` does
not, because `gh` can fail locally after GitHub has already made the issue.
The prefix is part of the file name, so a new prefix starts at one and
switching back finds the old sequence.

The new `key-mint` case in `coordinator/overnight/selftest.py` replays the
worst lag: the fake GitHub's list never catches up, so every read is the same
page. Three back-to-back opens still give three distinct keys:

```
PASS key-mint
```

and with the record ignored (`read_last_key` forced to zero) the same three
opens give one key three times, so the case fails on the old mint:

```
old mint caught: expected ['MO-2', 'MO-3', 'MO-4'], got ['MO-2', 'MO-2', 'MO-2']
```

The case also covers the other ways to reuse a key: an explicit key an earlier
open gave out, a listed key past the record, a create GitHub refused, a prefix
change, a pending create, and a record that cannot be read.
