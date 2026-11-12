# Decisions ledger — MO-179

Decisions this ticket did not cover, in the dzhng audit-decisions format:
every entry carries when it landed, the decision in plain words, the gap it
closes, its reach, a verdict and a confidence. Groups run needs-user, unsound,
sound; within a group, least confident first. `evidence/MO-179/decisions.md`.

## Needs-user

### The ticket's test-edit authorization did not cover the fixture's two roles

**When:** MO-179 closeout, 2026-11-11 PT.

*The ticket authorized one thing in the existing tests: "if an existing test
encodes the old path, change only that line and list it in the PR". The hub
install fixture built one checkout at `home/Code/mac-ops` and used it for two
roles — the live main checkout the post-merge fast-forward targets, and the
checkout the worker installs from. After the worker moved to the persistent
checkout, the two roles are two directories, so the fixture had to gain the
persistent one: three added lines in `setUp` and one changed line in the
dirty-checkout test, which now dirties the checkout the worker inspects. The
alternative — changing only the fixture's path line — leaves the post-merge
proof without a live checkout under `home/Code` and the suite fails. The
ticket's other instruction, to run the existing tests unchanged, cannot hold
either: against the new worker code the upstream test file fails 9 of its 26
hub install tests with `refused` != `done`, because the fixture checkout is
the development checkout the worker no longer reads. The in-session reviewer
read the added lines as beyond the ticket's authorization, so this stays open
for Shyam: the diff needs his approval for those four test lines, or the suite
needs a different fixture split.*

**Gap:** the ticket said the fixture encoded the old path in one line and left
it there; the line carried two roles, so no single-line edit keeps the suite
green.

**Reach:** every deferred-install proof for this worker depends on a fixture
that has both a live checkout under `home/Code` and a persistent checkout under
`home/.local/share`, and the upstream test file cannot stand in for that
fixture.

**Verdict:** needs-user — the test edits are forced by the code change, but
the ticket's authorization named one line, and only Shyam can approve the
rest.

**Confidence:** medium — the reading of the ticket's authorization is a
judgement call; the suite's dependency on the fixture is not.

**Owner:** `tests/test_hub_install.py:65`

### The persistent checkout still has to reach the pending SHA before a deferred install can run

**When:** MO-179 closeout, 2026-11-11 PT.

*The worker now installs from `~/.local/share/mac-ops-install`. On this machine
that path is a linked worktree of `~/Code/mac-ops` whose HEAD is detached at
842a196 while `origin/main` is 15a2104. The worker's existing guards refuse a
checkout that is not on `main` and a checkout whose HEAD is not the pending
SHA, so every deferred install refuses with "Deployment safety check failed"
until the persistent checkout sits on `main` at the pending SHA. This change
left the guards alone: the ticket allows one path constant, the ticket's scope
is repo files only, and the guards fail closed, so no install or restart runs
from the wrong source. The alternative — relaxing the guards to accept a
detached HEAD at the pending SHA, or letting the worker fast-forward the
persistent checkout itself — changes what the worker installs and when, which
is a different ticket.*

**Gap:** the ticket named the persistent checkout but never said who advances it
to the pending SHA, and the worker cannot do it from inside its current
contract.

**Reach:** every deferred Empryo install on this machine stays refused until the
persistent checkout is on `main` at the pending SHA; once an install does run,
the receipt names the persistent source again.

**Verdict:** needs-user — Shyam has to say how the persistent checkout is kept
current (a dedicated clone on `main`, a linked worktree pinned by hand, or a
worker-side fast-forward), because the ticket does not cover it and the
machine's checkout state does not do it today.

**Confidence:** high — the guards and the machine's checkout state were both
read directly.

**Owner:** `empryo/bin/emp_hub_install.py:16`

## Sound

### The worker keeps one constant for the install checkout and both call sites read it

**When:** MO-179 closeout, 2026-11-11 PT.

*`tick()` and `save()` each built the install path. The change replaced both
with `home / INSTALL_CHECKOUT`, a module constant holding
`.local/share/mac-ops-install`. The alternative — a literal at each site —
repeats the path and lets the two drift apart again, which is how the original
bug survived; a helper function `install_checkout(home)` was also possible,
but the file already keeps its shared values as module constants (`ACTIVE`,
`CAP_SECONDS`).*

**Gap:** the ticket said "one path constant" without saying constant or
helper, and without saying where it lives.

**Reach:** any later change to the install source touches one line in the
worker, and the two call sites cannot disagree about it.

**Verdict:** sound — the file's own convention is module constants, and both
call sites now agree by construction.

**Confidence:** high — the constant and both uses are the whole diff in the
worker.

**Owner:** `empryo/bin/emp_hub_install.py:16`

### The test fixture keeps the live checkout and adds a separate persistent checkout

**When:** MO-179 closeout, 2026-11-11 PT.

*`tests/test_hub_install.py` built one fixture checkout at `home/Code/mac-ops`
and used it for two roles: the live main checkout the post-merge fast-forward
targets, and the checkout the worker installs from. The two are now different
paths, so the fixture was split — `self.checkout` stays the live checkout and
a new `self.install` clone at `home/.local/share/mac-ops-install` is what the
worker reads. The dirty-checkout test now dirties the install checkout, which
is the checkout the worker inspects. The alternative — pointing the whole
fixture at the persistent path — breaks the post-merge proof, which needs a
live checkout under `home/Code`; leaving the fixture alone would have let the
worker keep installing from the development checkout.*

**Gap:** the ticket said "if an existing test encodes the old path, change
only that line", but that one line carried two roles, so the fixture needed a
second directory.

**Reach:** the hub install proof now fails if the worker installs from the
development checkout again — reverting the worker line to
`home / "Code/mac-ops"` failed on the dirty-checkout test, which is the
assertion that pins the path.

**Verdict:** sound — the split keeps every existing assertion and the dirty
test pins the stated behavior change.

**Confidence:** high — the suite passes with the change and fails without it.

**Owner:** `tests/test_hub_install.py:65`
