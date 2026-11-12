# Decisions ledger — MO-181

Run: `ticket:shyamsivakumar/mac-ops#119:a1`

Ticket: https://github.com/shyamsivakumar/mac-ops/issues/119

Base: `origin/main` at `b33dbf28bb08575a212a8c64db12bc8622152711`.
MO-179 merged as PR #118 and is an ancestor of this base.

Audit-decisions format: when, decision, gap, reach, verdict, confidence, owner.
This supersedes the earlier scope-stop record: the coordinator explicitly
resumed implementation and authorized admission and timing-test changes.

## Sound

### All admission gates use the original 30-minute wait, with no new state

**When:** MO-181 resumed implementation, 2026-11-11 PT.

*Keep the existing marker, worker, state names and coalescing path. Only age-gate
pending/waiting-idle admission in empq and the hub; installing/restarting always
block. The worker returns without side effects during the first 30 minutes.
The existing mark function already preserves the original since and updates the
pending SHA, including unrelated subsequent fast-forwards, so it is unchanged.*

**Gap:** the original scope omitted the hub's independent admission gate.
The coordinator now explicitly says "hub admission changes ... are authorized".
The matching small change to `emp-hub.install_pending` is necessary: otherwise
empq only moves work into a held hub queue and subsequent merges still refuse.
No scheduling, routing, turn-limit, daemon or state-file change was introduced.

**Reach:** thread starts, scheduler resumption and merges share the hub gate;
empq admission agrees at the exact 1800-second boundary. Invalid/missing/future
or nonfinite wait timestamps fail closed; interrupted side effects still refuse
before considering the wait. Persisted state updates, locks, exact HEAD and
origin/main verification, clean-main checks, routing checks, identity validation,
post-install idle checks and once-only restart logic are retained.

**Verdict:** sound — one age predicate at each existing admission boundary;
no workaround states, special launch paths or new machinery.

**Confidence:** high — temporary-home proof exercises empq drain through an
extracted hub start_turn with a fake engine/thread, merge admission, both gates,
coalescing, delayed once-only install/restart and baseline safety refusals.
No real hub process was run or contacted, and the real install marker was never
written. Only fake hub sockets in temporary homes were used.

**Owner:** `empryo/bin/empq:86`; `empryo/bin/emp-hub:806`;
`empryo/bin/emp_hub_install.py:123`.

### Preserve the bounded refusal after the batching window

**When:** MO-181 resumed implementation, 2026-11-11 PT.

*Keep CAP_SECONDS at 1800. The first 1800 seconds batch; the following 1800
seconds permit draining and installation. Refuse at since + 3600, without any
install or restart if still waiting. Later merges do not extend either window.*

**Gap:** the old total 30-minute deadline would refuse precisely when admission
now stops. Moving the existing 30-minute idle-wait budget after batching retains
the refusal rather than removing it. Coordinator authorization: "Existing timeout
tests that encode the old 'pause immediately' behavior may change only as far as
that stated change needs ... list every changed test line in the PR."

**Reach:** seven existing test lines change only fake times. No assertion,
refusal, fixture structure or proof step is removed. Changed lines in
`tests/test_hub_install.py` (old → new):

- 122: `def tick(self, now=101, **kwargs):` → `def tick(self, now=1900, **kwargs):`
- 195: direct timeout tick `now=101` → `now=1900`.
- 201: waiting assertion tick `now=1899` → `now=3699`.
- 202: refusal assertion tick `now=1900` → `now=3700`.
- 203: repeat terminal tick `now=1901` → `now=3701`.
- 227: post-install running-turn check tick `now=101` → `now=1900`.
- 286: final-idle-check merge exclusion tick `now=101` → `now=1900`.

**Verdict:** sound — all old safety checks run after the batch window instead
of before it. The cap still notifies once and never retries terminal side effects.

**Confidence:** high — the cap boundary and every existing refusal test pass.

**Owner:** `empryo/bin/emp_hub_install.py:145`; `tests/test_hub_install.py`.

## Targeted proof

Before production changes, the new seven-test acceptance suite failed four
cases: immediate admission block, immediate early install, and refusal at 31
minutes. Baseline owning suite before changes: 26 tests passed unchanged.

After implementation:

```text
python3 -m unittest discover -s tests -p 'test_hub_install*.py' -v
Ran 33 tests in 8.158s

OK
```

The 26 existing tests retain every assertion (only the seven authorized clock
lines above changed); seven new tests live in `tests/test_hub_install_batch.py`.
No full repo check, heavy command, live install/restart/drain/kickstart or real
hub command ran. `git diff --check` passed.

## In-session review

A fresh read-only Claude Opus 5.5 review of the implementation is required;
the earlier documentation-only PASS is not the implementation gate verdict.
