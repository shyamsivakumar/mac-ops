# MO-990 runs

Issue #990, PR #983, branch `t3/close-scope-swift-files`.
Code head checked: `2ddae417f4f36c2e8cc349bc87a94a75d0e9e7b0`.

## The issue's proof

```text
HOME=/nonexistent python3 -c "import sys;sys.path.insert(0,'coordinator/bin');import close_check as c;t=c.scope_tokens('In: the sheet: Foo.swift.');print('tokens',t);sys.exit(t!={'Foo.swift'} or c.scope_tokens('In: Foo.swift.template.')!=set())"
```

| Tree | Output | Exit |
| --- | --- | --- |
| `origin/main` (`1ec19918`; `close_check.py` equals the `5574760f` the PR branched from) | `tokens set()` | 1 (red) |
| head `83405858` (before this fix) | `tokens {'Foo.swift'}` | 0 |
| code head `2ddae417` | `tokens {'Foo.swift'}` | 0 (green) |

## The scope item on the last 40 merged PRs

Read only. For each merged PR of `mac-ops`, `strategy-replay-workbench` and
`tunerise`: the ticket named by `Refs/Fixes/Closes #n` in the PR body, and the
files of the PR (with rename sources). Both versions of `close_check.py`
(`origin/main` and `2ddae417`) were loaded side by side and compared on
`item_scope`, `scope_tokens` and `exclusion_tokens`.

| Repo | PRs | With a ticket | Status or detail changed | Tokens changed |
| --- | --- | --- | --- | --- |
| mac-ops | 40 | 37 | 0 | 0 |
| strategy-replay-workbench | 40 | 39 | 0 | 0 |
| tunerise | 40 | 39 | 0 | 3 (added Swift tokens only) |

Changed answers, all in tunerise, none changes pass or fail:

- tunerise#120 (ticket #116): adds token `TRSourceImportSheet.swift`.
- tunerise#121 and #122 (ticket #117): add `HomeView.swift` and
  `MainFlowAcceptanceUITests.swift`.

tunerise#120 passes under the old code too when run today. Ticket #116 has been
edited since the close check failed it: its scope line now carries the full
path of the Swift file, so the old reading finds it as a path. The failure is
not reproducible on the live ticket; the issue's proof above covers the bare
name.

## Names in odd places

A first fix of this PR (`83405858`) dropped some names that the old code kept.
The probes found it: `In: **Foo.swift** and docs/x.md` with `App/Foo.swift` and
`docs/x.md` changed went from pass to fail, and so did `In: Foo.swift-only`.
No ticket in the 120 PRs has a bold or italic bare name in its scope text, so no
real answer moved. The fix removes `*` and `-` from the second lookahead of
`_FILE_END`; the two cases are tests.

Probes of `scope_tokens("In: <text>")`, `origin/main` against `2ddae417`:

| Text | Result |
| --- | --- |
| `foo.py:12`, `foo.py's`, `` `foo.py`, ``, `foo.py.`, `foo.py...`, `(foo.py)`, `foo.py;`, `foo.py?`, `foo.py!`, `foo.py"`, `foo.py>`, `foo.py)`, `foo.py:`, `foo.py=1`, `foo.py#L12`, `foo.py@v1`, `foo.py\|bar`, `foo.py&bar.md`, `foo.py+bar.py`, `foo.py%`, `a-foo.py` | same |
| `foo.py-only`, `foo.py-`, `foo.py--bar`, `foo.py*`, `**foo.py**` | same (`foo.py`, or `**foo.py` for the bold name) |
| `[foo.py](https://x.org/a/b.py)` | same (`foo.py`) |
| `see https://github.com/o/r/blob/main/src/foo.py`, `https://x.org/foo.py and bar.py` | same (URL read out; `bar.py` stays) |
| `foo.py.bak`, `foo.py.Then`, `foo.py\` | changed: no token (the front of a longer name, as intended) |
| `foo.py/` | changed: `foo.py/` only (a directory, as intended) |

`python3 -m unittest tests.test_close_check` passes with the two new cases.
