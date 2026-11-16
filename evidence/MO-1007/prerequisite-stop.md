# MO-1007 prerequisite stop

Run: ticket:shyamsivakumar/mac-ops#346:a1

Verified 2026-11-16. HEAD and fetched origin/main both equal
6befb689c1fa64053085e97331b2612e4502cbc3.
The watcher implementation merge 661e2c8 is an ancestor of origin/main.
Issue #345 is closed. However, the native blocked-by list for #346 contains
only #366, #374 and #388 (all closed), and omits required #345.

Reproduce with:

```sh
git fetch origin
git rev-parse HEAD origin/main
git merge-base --is-ancestor 661e2c8 origin/main
gh issue view 345 --json state,title,closedAt
gh api repos/shyamsivakumar/mac-ops/issues/346/dependencies/blocked_by --jq '.[] | {number,state}'
```

Stopped under the brief's missing-prerequisite condition. No implementation,
live activation, package execution, tests, commit, push or PR. No claim of
wake-backlog delivery. Coordinator should restore the required native #345
relationship or explicitly waive it, then reissue the same bounded slice.

Superseded: coordinator continuation explicitly overrides this stop; implementation proceeds.
