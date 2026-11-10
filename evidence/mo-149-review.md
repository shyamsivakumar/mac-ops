# MO-149 in-session code review (one round)

Reviewer: `code-reviewer`, `subscriptions/claude-opus-5-5`.
Base: `origin/main`, frozen initial SHA `debbe637b07cbae40daadf244089ef539ccc7094`.
Read-only review of production diff, new checks and builder proof output; **not independently rerun**. No production bugs found. Separate deployment gate and coordinator approval are still required.

## Findings

- **major / acceptance** — `verification/check_hub_turn_budget.py:25,103`: existing proof fails 6/6 at its old unconditional-`main()` AST assumption, then would require removed provider-slot APIs and queue behavior. Leave unchanged pending Shyam's exact-edit approval. Do not restore production shims.
- **major / pending evidence** — the 601-second real wall-clock proof had not finished at review time. **Resolved after review:** exit 0, 10m 1s; full output in `evidence/mo-149-wall-clock.log`. The reviewer verdict below remains unchanged; no second round was requested.
- **minor** — the standard `__main__` guard additionally invalidates the old proof loader. Kept intentionally: safe ordinary imports are the natural supported loader for new checks, rather than deleting startup AST nodes. Existing provider-slot fixture already cannot satisfy the requested uncapped design.
- **minor** — docs still described provider-slot clocks and release. Corrected after review to describe prompt-time clocks, engine release, startup locking and new proof commands.

## Reviewer checks

Startup ownership precedes store reads/socket mutation. Arguments exit zero before hub-directory creation. Losing starters make no byte/mtime/inode changes. Lock descriptor remains process-lifetime, close-on-exec; no lock-file unlink. Provider gate/config/status references removed while `turnLimits`, breaker settlement and engine cleanup remain. Original proof untouched; five original test methods reused unchanged with new fixture. Bytecode-cache fixture isolation does not weaken assertions.

Builder output examined: startup 5 OK, uncapped budget/provenance 7 OK, repository tests 51 OK, diff check clean.

Original final reviewer line (not upgraded by the builder):

VERDICT: FAIL
