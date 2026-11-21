# MO-756 runs

## Proof command, origin/main (red)
```
KeyError: 'escaped_merges'
```

## Proof command, branch (green)
```
{'r/x#1': 'fix'}
```

## Real 7-day count, mac-ops, merges 2026-11-13 to 2026-11-20 (read-only gh, adapted from the proof command)

Rule: a fix PR that names the merged PR number (`Fixes #<pr>`, `Follow-up to #<pr>`) counts. A fix PR that names only the ticket counts only if that ticket was closed before the fix PR was created (closed tickets come from one extra issue search over the window plus 7 days). Reverts: none. Reopen events: one in the repo (#378, 2026-11-16), matched no merge.

Result: 7 escaped of 255 merges. Each of the 7 was checked by hand against the fix PR body.

| Merge | Fix PR | Verdict | Reason |
| --- | --- | --- | --- |
| #203 intake records | #205 | counted | body says "Follow-up to #203"; merged 2026-11-13 16:55, fix merged 17:04 |
| #245 T3c ordering | #288 | counted | body says "Follow-up to #245"; fixes blockers found in the review round |
| #256 coordq fix findings | #259 | counted | body says "Follow-up to #256"; merged 4 minutes later with review fixes |
| #262 T6 evidence rule | #263 | counted | body says "Follow-up to #262"; carries the T6 review fixes |
| #308 dispatch reservation | #313 | counted | body says "Follow-up to #308"; reclaim rule corrected |
| #310 gatekeep re-gate cap | #312 | counted | body says "Follow-up to #310"; one explicit gate per given-up head |
| #408 lane passes | #409 | counted | body says "Follow-up to #408"; restores the item failure raise |

Dropped by the new rule: none. All 7 name the PR number, so the ticket-only rule changed nothing today. Ticket-only matches that the old code counted were zero.

## Bounded events fetch (gate finding, scorecard reopened)

Approach: page `repos/<repo>/issues/events?per_page=100&page=N` by hand, newest first. Each page charges one call against the 60 call limit. Paging stops at the first page whose oldest event is older than the window start, or at a short page.

Stub proof, `gh` stubbed to return 5 pages where page 2 already predates the window:
```
pages fetched [1, 2] calls charged 2 reopens kept [{'number': 1, 'at': '1970-01-18T08:40:00+00:00'}]
```

Real mac-ops count after the change (merges 2026-11-13 to 2026-11-20, read-only gh):
```
escaped 7 of 255 calls 53
```
The 53 calls are 5 searches plus 48 event pages: this repo logs about 4800 events in the week, so a weekly window pages deep. A one day window pages about 14 times.
