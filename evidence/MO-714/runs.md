# MO-714 run output

Code head these runs used: `302ea05b2e62aae9393243f186869817470bb754`. The check proof in check-proof.md ran on the same head.

## Acceptance 2: the selftest case fails on origin/main and passes on the branch

The new checks sit in the `gate-round-cap` eval (`gatekeep_round_cap` in coordinator/overnight/selftest.py): two open PRs, the first with `Refs #1131` and a missing issue (HTTP 404), the second with no ticket reference. The second must still be a gate candidate, the first must be skipped with its reason, and an `ApiBudgetExhausted` from the comments read must still stop the pass.

```
$ python3 coordinator/overnight/overnight selftest   # coordinator/bin/coordq from origin/main 0abe7c50
FAIL gate-round-cap: GitHub request failed: repos/shyamsivakumar/strategy-replay-workbench/issues/1131/comments?per_page=100

$ python3 coordinator/overnight/overnight selftest   # coordinator/bin/coordq from the branch
PASS gate-round-cap   (and all 24 evals PASS)
```

## Acceptance 3: read-only run against the live repos

`coordq gatekeep --dry-run` is not read-only: it takes the queue and provider-block locks and reads the live queue. The run below calls `gate_candidates` in-process instead, with a scratch queue dir, `gh api` limited to calls with no write flag (an assertion refuses `-X`, `--method`, `-f`, `-F`, `--field`, `--input` and any non-`gh api` command), and `t3mcp` limited to `t3_thread_list` and `t3_thread_read`. The repos are the ones in the gatekeep config, without digitized/Concerning (manual merge repo, not a gatekeep target).

```
22 events, 175 GET reads, 0 writes (all 22 are candidates, none are skips)
```

The live board has no unreadable ticket reference now: the `Refs #1131` line in PR #711 was removed by hand, so no skip shows. The 404 handling against real `gh`:

```
$ gh_json("repos/shyamsivakumar/mac-ops/issues/1131/comments?per_page=100")
GhReadError stderr: 'gh: Not Found (HTTP 404)\n'
reason, body naming MO-1131: issue #1131 does not exist; a ticket key number used as an issue number?
reason, body without a key:  issue #1131 does not exist
```
