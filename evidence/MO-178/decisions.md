# Decisions ledger — MO-178

Decisions this ticket did not cover, in the dzhng audit-decisions format: every
entry carries when it landed, the decision in plain words, the gap it closes,
its reach, a verdict and a confidence. Groups run needs-user, unsound, sound;
within a group, least confident first. `evidence/MO-178/decisions.md`.

The ticket's stop condition was live and is now resolved: an existing check
hard-coded the old 900-second builder budget, the first build reported that
without touching the check, and Shyam's gate review then approved a four-line
edit to that check. The branch is green with every hub check passing. The last
entry records that approval and the four changed lines.

## Sound

### The hub's own 900-second fallback stays where the config no longer agrees with it

**When:** MO-178 build, 2026-11-11 PT.

*`empryo/bin/emp-hub:125` and `empryo/bin/emp-hub:1595` fall back to 900
seconds when the routing file carries no `turnSeconds`, and the routing file
now says 600. The ticket says no code changes, so both fallbacks stay at 900.
The work today reads the configured value on every launched thread and only
reaches the fallback if `routing.json` loses its `turnSeconds` key. The
unbuilt alternative — moving the two fallbacks to 600 — would make the code
default track the config, but it edits the hub binary for a fallback that the
shipped configuration never reaches.*

**Gap:** the ticket scoped itself to routing.json values and did not say
whether the code's hard-coded default has to follow the configured one.

**Reach:** a routing file that loses `turnSeconds` hands builders 15 minutes
again, and the code default no longer matches the configured budget; the next
change to the builder budget has to touch routing.json only, as it does today.
The gate review called this minor and out of scope for this ticket, so both
fallbacks stay at 900.

**Verdict:** sound — routing.json owns the budget and always carries the key,
so the fallback is unreachable in the shipped config.

**Confidence:** medium — Shyam may want the fallback aligned in a follow-up
rather than left as a second, older number in the binary.

**Owner:** `empryo/bin/emp-hub:125`

### `docs/empryo-hub.md` names the budget, so its numbers move with the config

**When:** MO-178 build, 2026-11-11 PT.

*The turn-budget section of `docs/empryo-hub.md` states the numbers in prose:
"the default (900)", "900 for the builder types, 1200 for `review`", "the
routing default (900 if absent)" and "With the 900-second budget the
no-progress (1200) and tool (10800) limits sit above it". After this ticket
those three 900s are false. The work today states 600 for the default and for
the builder types, keeps 1200 for `review`, keeps the no-progress and tool
limits where they are, and keeps the code fallback visible as the 900 it still
is. The unbuilt alternative — leaving the prose alone — would leave the hub
documentation describing a budget the hub no longer enforces.*

**Gap:** the ticket said "no code changes" and "values only" and did not say
whether the prose that quotes those values is in scope.

**Reach:** the hub docs describe the same budget the config enforces, and the
per-type table a reader finds there stays true for the next change too.

**Verdict:** sound — the alternative leaves a factual error in the repository's
own documentation, and this is the section MO-174 updated in the same way
when the budget moved to 900.

**Confidence:** medium — the ticket's "values only" wording could be read as
excluding the prose, and Shyam may prefer the doc edit in its own commit.

**Owner:** `docs/empryo-hub.md:212`

### No new check file for the 600-second values

**When:** MO-178 build, 2026-11-11 PT.

*The change ships with no new assertion file. The ticket asks for the repo's
existing hub tests to run unchanged, and the repo's rule puts new checks in new
files only when the task asks for them, so nothing new was written. The
acceptance proof is the ticket's own command, `python3 -c "import json;d=json.load(open('empryo/hub/routing.json'))['turnLimits'];print(d)"`,
which prints 600 for every builder type and 1200 for `review`. The unbuilt
alternative — a new proof file asserting the new values — would add a second
place to update at the next budget change, next to the check that already
covers these values.*

**Gap:** the ticket does not say whether the moved budget needs an assertion
of its own once the existing check is approved for the edit.

**Reach:** the builder budget is pinned in one place, `routing.json`, and the
existing turn-budget check owns the assertion; its four lines moved to 600 on
Shyam's approval, so the check is green without a second file.

**Verdict:** sound — the ticket asked for the existing tests unchanged, and the
repo rule reads the absence of a request for new checks as a prohibition.

**Confidence:** medium — a new assertion in a second file would have given the
budget a second place to update at the next change, next to the check that
already covers these values.

**Owner:** `empryo/config/EMPRYO.md:12`

### The turn-budget check moves with the budget, on Shyam's approval

**When:** MO-178 fix, 2026-11-11 PT.

*`verification/check_hub_turn_budget.py` asserts the routing file's builder
budgets by value, so moving `routing.json` to 600 broke four expectations:
line 209 pinned the whole `turnLimits` dict to 900, line 210 expected
`turn_seconds_for(routing, "standard") == 900`, line 321 expected a default
thread's budget to be 900, and line 325 expected the failure text
`turn budget exceeded: 15 min`. The first build reported that conflict without
touching the check, as the ticket asked. The gate review then ruled FAIL on that
one point and prescribed the smallest fix: this ticket states a behavior change,
so under Shyam's 2026-11-10 test-edit rule exactly those four expectations may
move. They did, to 600 and to `10 min`; nothing else in the file changed, and
the legacy path that drops `turnSeconds` from the routing file keeps its 900 and
its `15 min` at lines 331 and 334 because that path exercises the hub's code
fallback, not the configured budget. The unbuilt alternative — leaving the check
red, or moving its other 900s as well — would either fail the gate again or
change an assertion about a different code path.*

**Gap:** the ticket said report rather than edit and quoted no approval, so the
build stopped with the check red; the gate review supplied the approval and the
exact scope of the edit.

**Reach:** `python3 verification/check_hub_turn_budget.py` is green again on
the 600-second budget, and the check still asserts the configured values, so
the next budget change fails here first.

**Verdict:** sound — the gate named the four lines and the values, and the edit
stays inside them.

**Confidence:** high — the edit is the prescribed one and the check passes.

**Owner:** `verification/check_hub_turn_budget.py:209`
