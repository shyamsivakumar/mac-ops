# Decisions ledger — MO-181

Run: `ticket:shyamsivakumar/mac-ops#119:a1`  
Ticket: https://github.com/shyamsivakumar/mac-ops/issues/119  
Base: `origin/main` at `b33dbf28bb08575a212a8c64db12bc8622152711`.
MO-179 merged as PR #118 (`10027e3f2579955ebac0cb46424fac1d66d47b38`),
an ancestor of this base.

Audit-decisions format: when, plain-language decision, gap, reach, verdict,
confidence and owner. Needs-user entries precede sound entries.

## Needs-user

### The two-function scope cannot keep turns and subsequent merges moving

**When:** MO-181 investigation, 2026-11-11 PT.

*Stop before production coding, as the ticket requires when the change needs
another layer. Changing only `empq.install_pending` and the install worker's
`tick` cannot achieve the stated goal. The hub independently treats `pending`
and `waiting idle` as immediate admission barriers. `start_turn` saves starts
as pending instead of running an engine, the scheduler does not resume them,
and `merge_guard` refuses subsequent merges. Letting empq dispatch during the
first 30 minutes would therefore only move work into the hub's blocked queue;
it would not let that work run or allow the second merge to reach the existing
SHA-coalescing path.*

**Gap:** the ticket prohibits hub changes and places the rule in two functions,
but `empryo/bin/emp-hub:806`, `:840`, `:1571` and `:2259` also own admission.
A temporary-home AST extraction of the unchanged hub's `install_pending` and
`merge_guard` demonstrated:

```text
Hub blocks turns for any pending age: True
RuntimeError: Empryo install pending; retry merge after deployment completes
Exit code: 1
```

The probe loaded only these function definitions, supplied a fake lock and
thread, and wrote a temporary `install.json`. No hub process or socket was used.
A separate temporary-home extraction of empq's gate with a five-minute-old
pending marker reproduced the reported immediate queue pause:

```text
5-minute pending blocks new work: True
AssertionError: pending state blocks immediately instead of after 30 minutes
Exit code: 1
```

**Reach:** acceptance (1) must mean a real turn starts, not merely a successful
queue dispatch; (3) needs the hub to admit a second merge during batching.
Both fail under the existing hub admission contract, regardless of empq's age
check. No production or existing test files were changed.

**Verdict:** needs-user — authorize an admission-contract refactor before
implementation. Recommended design: distinguish batching from draining in the
existing install state, have mark/coalescing preserve the original batch start,
and make the hub and empq gate only draining/installing/restarting states.
The worker must persist the draining barrier before checking idle and retain
all exact-SHA, checkout, identity, interrupted-install and routing refusals.
This stays within the existing state file and worker, but necessarily widens
the named-function scope and the hub contract; it is not implemented here.

**Confidence:** high — both independent barriers were reproduced directly.

**Owner:** `empryo/bin/emp-hub:806`; `empryo/bin/emp_hub_install.py:69`.

### The existing 30-minute refusal conflicts with starting the drain at 30 minutes

**When:** MO-181 investigation, 2026-11-11 PT.

*Do not silently remove the worker's bounded-wait refusal or change the test
that pins it. `tick` refuses at `now - since >= CAP_SECONDS` (1800 seconds),
so a 31-minute-old pending marker cannot install even if empq now drains.
The unchanged `test_thirty_minute_cap_notifies_once_and_never_restarts` explicitly
requires refusal at this boundary. A new batching window needs a separately
specified bounded draining window and approval to update that old expectation.*

**Gap:** the ticket requires installation after a 30-minute batching wait,
unchanged existing tests, and preservation of safety refusals, without defining
a replacement deadline. Those requirements cannot all hold for the existing
30-minute-cap assertion.

**Reach:** acceptance (2) and (4), timeout behavior, and the existing installer
suite. Recommend keeping a bounded 30-minute drain budget after the batch
window, anchored independently of later merges; approval is needed, not assumed.

**Verdict:** needs-user — authorize the deadline semantics and the exact obsolete
test expectation before implementing. No existing test was edited or weakened.

**Confidence:** high — the boundary and assertion are explicit.

**Owner:** `empryo/bin/emp_hub_install.py:145`; `tests/test_hub_install.py:199`.

## Sound

### Baseline safety proof uses only a temporary home and fake hub

**When:** MO-181 investigation, 2026-11-11 PT.

*Run the owning existing installer suite unchanged, rather than the full repo
check or any live install command.*

**Gap:** the automatic test runner reported no detected command, so the targeted
unittest command was used directly:

```text
python3 -m unittest discover -s tests -p test_hub_install.py -v
...
Ran 26 tests in 24.094s

OK
```

**Reach:** the unchanged suite proves the baseline's once-only install/restart,
running-turn exclusion, dirty/wrong checkout refusal, routing protection,
interrupted-side-effect refusal, queue locking, SHA coalescing, admission barrier
and existing timeout. It does not prove the requested new batching behavior.
No real hub was run, restarted, drained or kickstarted, and the real install
marker was never written. All execution side effects used the suite's fakes.

**Verdict:** sound — baseline safety remains intact; implementation is blocked
on the two scope decisions above.

**Confidence:** high — all 26 targeted tests passed unchanged.

**Owner:** `tests/test_hub_install.py`.
