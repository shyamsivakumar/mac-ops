# MO-1088 · GitHub core API usage

Measured for ticket #548. The GitHub core quota is 5000 calls an hour for
the user, and every caller below shares it. On 2026-11-18 it reached 0 at
12:44 UTC; the lane driver, the overnight shift and gatekeep all stalled
with "API rate limit exceeded" and "board list is stale". After the reset
it fell from 3811 to 2542 remaining in 15 minutes, so the same hour would
run out again.

## What the logs already show

`~/Code/coordinator/queue/dispatch.log` and
`~/Library/Logs/coordinator/lanes.log` hold the refusals that reached a
caller. They are the visible end of the exhaustion, not the count:

| log | `API rate limit exceeded` lines |
| --- | --- |
| `queue/dispatch.log` | 14 |
| `Library/Logs/coordinator/lanes.log` | 35 |

The refusals cluster in the hours the shift and the board poller both ran
(`2026-11-13 17:xx`, `2026-11-14 21:xx`, `2026-11-15 06:xx–08:xx`), which
is what a shared 5000 call pool looks like when every caller counts only
its own work.

## The share by caller

Herdr reported its own share for this ticket. The coordinator's share is
read from the call sites and the launchd intervals (`coordinator/launchd/`),
because one pass of each caller is what repeats:

| caller | interval | reads per pass | calls per hour |
| --- | --- | --- | --- |
| Herdr worktree scan | 4 scans/h | one `gh api repos/*/commits/<sha>` per worktree head (212) | ~850 |
| Herdr board ticket list | 60 s | 12 repos, 9 of them empty, TTL 60 s | up to 720 |
| gatekeep | 60 s | login 1 + pull list per repo 4 + comments and statuses per PR (~12) | ~1000 |
| lane driver | 180 s | board snapshot 3 calls every 5 passes + one view per item | ~200 |
| overnight board | 300 s | board list + per-repo bodies and checks | ~150 |
| tick | 1800 s | board JSON + gate backstop | ~30 |
| coordq refill | 30 s | one owner search + one issue list per repo | ~100 |

Herdr is cutting its own share to about 200/h on `herdr/gh-trim`; this
ticket does not touch Herdr's code. Its two suggestions for the ticket
tool are taken: the board cache now outlives the one-minute poller, and a
single-page REST read is made conditional, so a 304 costs no core call.

## What changed

One helper, `coordinator/bin/gh_gateway.py`, is the only GitHub call path
for the lane driver, coordq, the overnight shift and the ticket tool.

1. **Cache.** A repeated list read is served from
   `~/.cache/coordinator/gh` for 120 s. The verb is read from the command,
   so `gh pr list` and `gh issue list` are cached like `gh label list`; a
   `view` is not. An `gh api` read is cached only when it is a verified
   GET of a list endpoint: a write that carries a query string, such as a
   repository dispatch, is never answered from the cache. `ticket`'s own board cache keeps
   its list for 240 s instead of 60 s, so a poller that reads the board
   every minute is served by the cache for three of its four reads
   (`TICKET_CACHE_TTL`, and `--fresh` still bypasses it).
2. **Conditional reads.** A single-page `gh api` GET carries
   `If-None-Match` from the last ETag. The HTTP status line is parsed, so
   only a status 304 answers from the stored body and costs no core call;
   a 200 whose body happens to hold the number 304 is a fresh answer. A
   paginated read is not conditional: its header blocks and bodies
   interleave, so the cache is the only saving there.
3. **Floor.** The shared reserve is 1500 remaining calls
   (`COORDINATOR_GH_FLOOR`, default 1500; the lane driver's old 500 is
   raised to it). Below the floor the gatekeep run and the overnight board
   read wait for the quota instead of spending the last calls. An optional
   read that is below the floor is skipped; a read that matters still runs
   and fails on its own if GitHub refuses it.
4. **Measurement.** Every GitHub request is one line in
   `~/Library/Logs/coordinator/gh-usage.jsonl`, with the caller, the
   verb and the quota it spends (`core`, `search` or `graphql`). No
   argument is written: a `-H` header can carry a token.
   The quota is read from the endpoint or the command, not from the first
   word: `gh api search/issues` is the search bucket, `gh run list` is a
   core call on the Actions REST API, and `gh pr list` is GraphQL. A
   command named in neither list is `other` and is never counted as core. A paginated read logs one line per page it fetched. A
   conditional 200 logs its line, and a 304 logs none.
   `python3 scripts/gh-usage-report.py --hours 1` prints the count per
   caller per quota per hour and the core total.

A cached answer and a 304 are not calls that cost core quota, so they are
not in the log. That makes the log the count of what was spent, not of what
was wanted.

## Stale decisions

The cache never serves a read that decides a merge or a gate on a head:
`gh pr view`, `gh pr merge` and a single `repos/.../pulls/<n>` path are
not cacheable commands in the helper, and the lane driver's merge decision
reads the head and merges with `--match-head-commit` on that same read.
The TTL is 120 s, so a new pull request or a moved label shows within two
minutes.

## Expected effect

From the table above the coordinator's own share is about 1500/h and
Herdr's is about 1570/h, so the pool is spent before the hour ends. With
the cache (gatekeep's unchanged list and status reads answered locally),
the 240 s ticket list and Herdr's own trim:

| caller | before | after |
| --- | --- | --- |
| Herdr (its own trim) | ~1570 | ~200 |
| gatekeep | ~1000 | ~350 |
| lane driver | ~200 | ~120 |
| overnight + tick + refill | ~280 | ~180 |
| **total** | **~3050** | **~850** |

That leaves the 5000 call pool well above 2500 remaining at the end of a
normal hour.

## Reproduce the one-hour sample

After install, on an hour of normal running:

```
python3 scripts/gh-usage-report.py --hours 1
gh api rate_limit --jq '.resources.core'
```

Run the `rate_limit` sample at the start and at the end of the hour and
paste both. The core `remaining` must stay above 2500.

## Proof of the helper

`python3 evidence/MO-1088/prove-gh-gateway.py` runs against a fake `gh` on
PATH and asserts: a repeated list read runs once; a slurped and an
un-slurped paginated read each log one row per page; a conditional 200 is
counted and returns the new body; a 200 whose body holds the number `304`
returns the new body and not the stored one; a real 304 serves the stored
body and logs no row; a head read always calls, is counted and is never
conditional; the usage log names the caller; and a read below the floor is
refused.

Last run: every line PASS.
