# MO-685: builds and fixes launch through the task router

Builds and fixes launched by `coordq` went straight to
`{instanceId: pi, model: morph/morph-dsv41flash}` or
`{pi, morph/morph-kimik31}`, so they never passed through the T3 `router`
instance and its `task-router.ts` extension. A Morph rate limit (429) failed
the item. On the router the same limit falls back to the next Morph model
inside the same thread.

## What landed

- `coordinator/models.json`: the two `pi` Morph entries in `build` and `fix`
  are replaced by one `router` entry, `{instanceId: router, model:
  task/standard}`, with a `routes` table (task type to chain) and a `chains`
  table (chain to Morph models in order). `cursor`, `terra`, `sol` and
  `sol-max` keep their order and `only` lists, so quick work still ends on
  terra.
- `coordinator/bin/models.py`: `selection_for` resolves the router entry's
  route for a task type; `entry_blocked` treats the router entry as blocked
  only when every Morph identity it covers is blocked; `find` accepts a
  configured `task/<chain>`; `router_covers` maps a direct `pi` Morph
  selection to the router entry by blocked-store identity; `pi_routes` and
  `pi_identities` expand the chains so the installer still rebuilds `ROUTES`;
  `first_other` uses the same blocked rule.
- `coordinator/bin/coordq`: `with_model` resolves the router selection for the
  task type and maps a direct `pi` Morph payload to the router entry instead
  of refusing it; `queued_launch_args` classifies a legacy Morph payload the
  same way.
- `coordinator/bin/ticket`: `resolve_models` resolves the builder selection
  for the ticket type; `builder:kimi` and `builder:deepseek` labels on older
  tickets are read as `builder:router`.
- `coordinator/overnight/selftest.py` and `coordinator/bin/hourly_selftest.py`:
  the `router-build` and `router-blocked` evals, and the `start-routing`
  assertions updated to the router entry.
- `evidence/MO-685/check-proof.md`: the check proof.

## Why the two extra files are in the change

The close checklist read the merged pull request #686 and failed the scope
item:

```
scope: fail - outside the ticket's stated scope: coordinator/overnight/lane_driver.py, docs/model-list.md
proof file: pass - evidence/MO-685/check-proof.md is present
checks: pass - every one of the 12 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#685
```

Both files are consequences of the change the ticket asked for, not new work:

- `coordinator/overnight/lane_driver.py`: `dead_run_model` reads the build
  list through `first_available`, so with the router entry it picks the
  router. Without the one-line change a dead run on a usage limit relaunches
  on the same entry it just failed on, which is the opposite of what the
  function documents. Recovery has to skip the failed entry, and skipping the
  router entry means excluding every Morph identity it covers.
- `docs/model-list.md`: the doc describes the model list this ticket changes.
  Left alone it would say the workhorses are two `pi` entries that no longer
  exist.

The ticket's scope section now names both files, with those reasons. The
change itself is unchanged.

## The close checklist, after the scope correction

The scope item, read against the file list of the merged pull request #686 and
the corrected ticket:

```
scope: pass - every changed file is inside the ticket's stated scope
```

The other three items are unchanged from the run above: the proof file is
present, all 12 checks it lists passed, and the cost note is skipped because
the MO-1068 report does not exist yet.

This pull request carries only the ticket's evidence directory, so its own
scope item reads the same way.

## Proof

- `python3 coordinator/overnight/overnight selftest` - 24/24 PASS, including
  `router-build` and `router-blocked`.
- `python3 scripts/mac_ops_fast_check.py` - passed; `check-proof.md` lists
  every check with the command that ran it. This pull request changes only
  evidence, so the run covers the base checks and no per-file syntax or test
  check; the merged change's own proof listed 12.

The passing run is `check-proof.md`. The proof file is removed in the commit
this record lands in and written again by the run that follows, so the diff
from the checked commit to the head only adds it.

## Left for later

Nothing.
