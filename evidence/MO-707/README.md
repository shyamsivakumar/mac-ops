# MO-707: a stale `stage:started` label no longer makes a repo busy

Ticket: shyamsivakumar/mac-ops#707 (key MO-1132). The check proof is
`check-proof.md` in this directory.

This directory is the ticket's own evidence directory, the one the close
checklist reads: `proof_file.path_for` builds `evidence/<key>-<issue>/` from
the ticket title and number, so the proof of #707 sits at
`evidence/MO-707/check-proof.md`. The earlier run wrote it to
`evidence/MO-1132/`, which the checklist does not read, so the close failed on
the proof file and on the two extra files there being outside the ticket's
scope. The code is unchanged from #712; this pull request carries the evidence
at the path the checklist reads.

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
`~/Library/Logs/coordinator/gh-usage.jsonl` under this script's own caller
name (`evidence/MO-707/count-pass.py`):

```
new usage rows 24
by route Counter({'repos/*/*/issues': 12, 'repos/*/*/pulls': 12})
paid 24 free 0
distinct calls 24
```

The pull read is one page (`per_page=100`, no `--paginate`) and it is fresh, so
a pull request opened a moment ago is never hidden by the gateway's 120s list
cache. A repo with a full page of open pull requests cannot be read within the
one-read allowance, so the pass stops and logs
`refill stopped: open pull request list is longer than one page for <repo>`
rather than spending a second call.

## The log line

`refill: #<n> is stage:started with no live thread or open PR`, one line per
ticket per pass, from `board_candidates`. `check_lane_selection` asserts the
exact line for a stale ticket, asserts no line when an open pull request refs
the ticket, asserts no line for a draft pull request, and asserts no line when
a live thread works the repo.

## A waiting builder still holds its repo

`coordq`'s cap list does not count a thread that waits for an answer, but the
ticket CLI does (`coordinator/bin/ticket` `LIVE_STATUSES` includes `waiting`).
The `stage:started` label used to cover that gap. `live_lane_repositories` now
asks for `LANE_STATUSES` (`LIVE_STATUSES` plus `waiting`), so a waiting builder
still makes its repo busy and the cap is unchanged.

The live board had no open `stage:started` ticket when this ran
(`gh search issues --owner shyamsivakumar --state open --label stage:started`
returned `[]`), so the line is proven by the check rather than by a live pass.

## Stop condition

A pull request list that cannot be read raises `RuntimeError` from
`open_pr_refs`: a failed read, a body that is not a list, a page that is not a
list of pull requests, or a list longer than the one page the pass may read.
`refill` already catches that and logs
`refill stopped: open pull request snapshot failed for <repo>`, so the pass
stops with no partial busy set. `gh_gateway.run(..., limit=FLOOR)` raises
`ApiBudgetExhausted` (a `RuntimeError`) below the existing budget floor, so the
same path covers the floor.
