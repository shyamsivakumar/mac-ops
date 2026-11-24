# MO-955 runs

## Ticket proof

```
HOME=$(mktemp -d) python3 -c "import sys;sys.path.insert(0,'coordinator/bin');import close_check as c;b='In: Files: Dockerfile.dashboard';assert c.item_scope(b,['Dockerfile.dashboard'])['status']==c.PASS;assert c.item_scope('In: Dockerfile',['Dockerfile.dashboard'])['status']==c.FAIL"
```

origin/main close_check.py (a6eecb81): exit 1

```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AssertionError
```

Branch code commit 7f28e9cefd91ad1243f99e92c572530cf133c6ff: exit 0

## Tests

test_a_dockerfile_variant_is_a_file_token fails on origin/main and passes on the branch; the other four new cases pass on both, as they pin behavior that must not change.

## Replay

item_scope over the ticket (issue named by Refs/Fixes in the PR body) and changed files of the 15 most recent merged PRs of mac-ops and strategy-replay-workbench (30 total), origin/main code against this branch. Status columns are main then head.

| PR | main | head | result |
| --- | --- | --- | --- |
| mac-ops #949 (ticket #945) | fail | fail | same |
| mac-ops #948 (ticket #944) | fail | fail | same |
| mac-ops #947 (ticket #943) | fail | fail | same |
| mac-ops #941 (ticket #939) | fail | fail | same |
| mac-ops #940 (ticket #938) | fail | fail | same |
| mac-ops #937 (ticket #936) | fail | fail | same |
| mac-ops #935 (ticket #932) | fail | fail | same |
| mac-ops #934 (ticket #933) | fail | fail | same |
| mac-ops #931 (ticket #927) | fail | fail | same |
| mac-ops #930 (ticket #928) | fail | fail | same |
| mac-ops #929 (ticket #926) | fail | fail | same |
| mac-ops #925 (ticket #923) | fail | fail | same |
| mac-ops #924 (ticket #922) | fail | fail | same |
| mac-ops #921 (ticket #917) | fail | fail | same |
| mac-ops #920 (ticket #918) | fail | fail | same |
| strategy-replay-workbench #2477 (ticket #2181) | fail | fail | same |
| strategy-replay-workbench #2476 (ticket #1969) | pass | pass | same |
| strategy-replay-workbench #2475 (ticket #2259) | fail | fail | same |
| strategy-replay-workbench #2474 (ticket #2015) | fail | fail | same |
| strategy-replay-workbench #2473 (ticket #2013) | fail | fail | same |
| strategy-replay-workbench #2472 (ticket #1969) | pass | pass | same |
| strategy-replay-workbench #2471 (ticket #1965) | pass | pass | same |
| strategy-replay-workbench #2469 (ticket #1918) | fail | fail | same |
| strategy-replay-workbench #2467 (ticket #2333) | pass | pass | same |
| strategy-replay-workbench #2466 (ticket #2333) | pass | pass | same |
| strategy-replay-workbench #2463 (ticket #2460) | fail | fail | same |
| strategy-replay-workbench #2459 (ticket #2406) | fail | fail | same |
| strategy-replay-workbench #2458 (ticket #2443) | pass | pass | same |
| strategy-replay-workbench #2457 (ticket #2406) | fail | fail | same |
| strategy-replay-workbench #2456 (ticket #1964) | pass | pass | same |

changed: 0

No result changed. SRW #1427 (the Dockerfile.dashboard case) is not among the 15 most recent merged SRW PRs, so no replayed ticket names a Dockerfile.
