# MO-954 runs

## Ticket proof

```
HOME=$(mktemp -d) python3 -c "import sys;sys.path.insert(0,'coordinator/bin');import close_check as c;t='In:\n- \`src/a.py\`: move it without changing its behavior.\n';i=c.item_scope(t,['src/a.py']);assert i['status']==c.PASS,i['detail'];assert c.item_scope('In: \`src/b.py\`. \`src/a.py\` must not change.\n',['src/a.py'])['status']==c.FAIL"
```

origin/main close_check.py (a6eecb81): exit 1

```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AssertionError: the ticket excludes it: src/a.py
```

Branch code commit f0c65999c049a878daf6f3ef2928bd9f4508467c: exit 0

## Tests

Two new cases fail on origin/main (test_a_without_clause_excludes_from_without_on, test_a_without_clause_excludes_only_what_it_names) and pass on the branch; the other two new cases pass on both, as they pin behavior that must not change. Run with tests/test_close_check.py against main's close_check.py.

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
| strategy-replay-workbench #2475 (ticket #2259) | fail | pass | CHANGED |
|  | main: the ticket excludes it: scripts/srw_exit_drill.cjs | head: every changed file is inside the ticket's stated scope | |
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

changed: 1

The one change is strategy-replay-workbench #2475 (ticket #2259), fail to pass: the #2259 shape this ticket fixes. No other result changed.
