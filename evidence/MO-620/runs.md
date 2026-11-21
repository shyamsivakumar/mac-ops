# MO-620 runs

Proof command (adapted): `python3 evidence/MO-620/prove-conditional-reads.py <repo root>`.
The ticket gave an expected shape only. This script drives `coordq.gh_json`, the reader that
`gate_candidates` uses for pulls, comments and statuses, against a stateful fake `gh` that
answers `If-None-Match` with a 304. "Paid" is a 200 answer; a 304 is free. The in-process list
TTL is set to 0 to stand for the 180 s gap between real passes. The board has 3 PRs.

## Before (origin/main 0a84225e)

```
PASS first pass reads everything (7 paid, 0 304)
FAIL second pass over unchanged PRs costs 0 rate-limited calls (7 paid, 0 304)
FAIL a new head and a new comment are re-read (7 paid, 0 304)
FAIL the pass after that is free again (7 paid, 0 304)
PASS corrupt entries are dropped, gatekeep does not crash (7 paid, 0 304)
PASS a full page falls back to the paginated read and returns every row (4 rows, calls: ['200 paginated repos/o/r/pulls?state=open&per_page=2'])
```

## After

```
PASS first pass reads everything (7 paid, 0 304)
PASS second pass over unchanged PRs costs 0 rate-limited calls (0 paid, 7 304)
PASS a new head and a new comment are re-read (3 paid, 4 304)
PASS the pass after that is free again (0 paid, 7 304)
PASS corrupt entries are dropped, gatekeep does not crash (7 paid, 0 304)
PASS a full page falls back to the paginated read and returns every row (4 rows, calls: ['200 repos/o/r/pulls?state=open&per_page=2', '200 paginated repos/o/r/pulls?state=open&per_page=2'])
```

The 3 paid reads in the changed pass are the pull list, the new status list for the moved head,
and the comment list that gained a comment.

## Real GitHub, one read-only list (shyamsivakumar/mac-ops open pulls)

Plain read: `HTTP/2.0 200`, `Etag: W/"f12e9ae8..."`, `X-Ratelimit-Remaining: 4134`.
Same URL with `-H 'If-None-Match: <that etag>'`, twice: both `HTTP/2.0 304 Not Modified`.
`gh api rate_limit` core remaining before the two 304s: 4129; after: 4129. Two 304s cost 0.
The ETag is weak (`W/"..."`); the gateway stores and resends it verbatim.
