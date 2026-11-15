# MO-1006 delivery

Refs #345. Run ticket:shyamsivakumar/mac-ops#345:a1.

Fresh base: 8d6c70d4146cf857a59d0081159e784773837635. Fetched and rebased
on origin/main. Native blocked-by relationship to closed #344 was verified in
the initial turn; watch-lanes is present at the base.

The continuation supersedes scope-stop.md. Read the external lane.md and
notes.md from /Users/shyamsivakumar/Code/coordinator without modifying them.

Decisions: foreground continuous mode is default, with --once retained for
existing callers. Run identity comes from activeRunId and the matching latest
recentRuns entry, never thread creation time. Running threads without a known
start time stay unknown. Rate-limit and traceback events are read from explicit
logs or the queue dispatch.log default. Only the state file is written at runtime;
its parent must exist. The lifetime lock prevents a second watcher sharing state.
No dispatch, mutation, labels, PR actions or lane scheduler are in the watcher.

Installer source contract already maps coordinator/bin/coord-watch to
~/.local/bin/coord-watch at mode 0755 via BIN_FILES and plan(). No redundant
mapping edit was made. No installation or package execution was performed.

Verification command (required agent check):

    timeout 300 python3 scripts/mac_ops_fast_check.py

Device, live-service and owner testing are waived by the continuation. No new
unit tests were created. Fake-clock runtime replay and temporary-HOME actual
installation were not executed; source inspection is not their equivalent.
The fast check covers changed Python syntax and existing selected checks,
including the HeavyQueue model, not end-to-end runtime acceptance.

Deslop review used standard-library facilities and existing installer mapping;
no dependencies or cleanup installs. no-comments diff review: only the CLI
module docstring changed; it describes the command contract. No added code
comments or suppressions. Documentation is updated in docs/coord-watch.md,
already linked from README.md. No writes outside this repository.

Limitations: persistence precedes printing, so a crash in that window can lose
an event; state loss can repeat events. Unread tails of rotated-away files are
not recovered. Identical truncate/regrow boundaries cannot be detected. State
history exceeding 8 MiB fails visibly and requires operator intervention.
Signal shutdown during collection can take up to the 120-second shared deadline.
No live activation, merge or next-ticket start. Provides watch-complete remains
subject to coordinator review and verification on merge.
