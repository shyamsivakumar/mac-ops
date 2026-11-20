# MO-1132: a stale `stage:started` label no longer makes a repo busy

Ticket: shyamsivakumar/mac-ops#707. The check proof is `check-proof.md` in this
directory.

## What changed

- `coordinator/bin/coordq`: `lane_candidates` no longer adds a repo to `busy`
  for a `stage:started` label. A repo is busy when a live lane thread works it
  (`live_lane_repositories`, unchanged) or when an open, non-draft pull request
  refs one of its open tickets (`Refs #n`, `Closes #n`, `Fixes #n`).
- `coordinator/bin/coordq`: `open_pr_refs` reads the open pull requests of one
  repo through `gh_gateway`, one read per repo per pass, and `stale_started`
  names the `stage:started` tickets with no live thread and no open pull
  request that refs them. `board_candidates` logs one line per such ticket per
  pass and changes nothing else.
- `scripts/mac_ops_fast_check.py`: `check_lane_selection` replaces the old
  assertion that a `stage:started` row makes its repo busy with the three new
  cases, and covers the log line, the draft/other-number cases and a failed
  pull request read.

## GitHub calls per refill pass

12 repos are configured in `~/.coordinator/tickets.json`. Before the change a
pass read the open issues of each repo: 12 calls. After the change a pass reads
the open issues and the open pull requests of each repo: 24 calls, one extra
read per configured repo.

Measured on this head with `live_lane_repositories` stubbed to an empty set, so
only the board reads ran, counting the rows the pass appended to
`~/Library/Logs/coordinator/gh-usage.jsonl`:

```
new usage rows 24
by route Counter({'repos/*/*/issues': 12, 'repos/*/*/pulls': 12})
paid 24 free 0
distinct calls 24
```

The pull read is a cacheable list route (`repos/o/r/pulls?state=open`), so a
repeated pass inside the 120s list TTL is served from the gateway cache and
costs nothing.

## The log line

`refill: #<n> is stage:started with no live thread or open PR`, one line per
ticket per pass, from `board_candidates`. `check_lane_selection` asserts the
exact line for a stale ticket, asserts no line when an open pull request refs
the ticket, and asserts no line when a live thread works the repo.

The live board had no open `stage:started` ticket when this ran
(`gh search issues --owner shyamsivakumar --state open --label stage:started`
returned `[]`), so the line is proven by the check rather than by a live pass.

## Stop condition

A pull request list that cannot be read raises `RuntimeError` from
`open_pr_refs`, which `refill` already catches and logs as
`refill stopped: open pull request snapshot failed for <repo>`. The pass stops
with no partial busy set, and `gh_gateway.run(..., limit=FLOOR)` raises
`ApiBudgetExhausted` (a `RuntimeError`) below the existing budget floor, so the
same path covers the floor.
