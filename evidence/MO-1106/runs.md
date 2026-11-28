# MO-1106 proof runs

## Ticket proof command on origin/main (red)
```
unrecognized arguments: --pr
```
## Same command on the branch (green)
```
usage: coordq gatekeep [-h] [--dry-run] [--pr PR] [--config CONFIG]
  --pr PR          gate this pull request only, as owner/repo#number
```
## Selftest cases on the branch, temp COORDQ_DIR, fake gh (no heavy)
```
gatekeep_single_pr ok: --pr reads only pulls/21, queues only its gate; dry --pr queues nothing; full pass queues both
existing gatekeep cases ok
```
## origin/main against the new case
```
coordq: error: unrecognized arguments: --pr a/b#1
```

## Unreadable ticket title skips one PR (added after the lead's note)
`gatekeep_single_pr` now has a PR whose `issues/11` read fails inside `builder_thread_for_issue`.
Old coordq (commit b64d2135 plus the config change): the case exits 1 (gatekeep died, `gatekeep stopped: GitHub request failed`).
New coordq: the PR is skipped with one stderr line and the other PR is still queued; the case passes.
