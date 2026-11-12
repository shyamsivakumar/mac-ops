# Decisions ledger — MO-178

Decisions this ticket did not cover, in the dzhng audit-decisions format: every
entry carries when it landed, the decision in plain words, the gap it closes,
its reach, a verdict and a confidence. Groups run needs-user, unsound, sound;
within a group, least confident first. `evidence/MO-178/decisions.md`.

The ticket's stop condition is live: an existing check hard-codes the old
900-second builder budget, so the branch is held for Shyam's direction and the
PR stays blocked until he rules. The first entry says what that block is and
what it waits on.

## Needs-user

### The turn-budget check keeps its hard-coded 900s until Shyam approves the edit

**When:** MO-178 build, 2026-11-11 PT.

*`verification/check_hub_turn_budget.py` asserts the routing file's builder
budgets by value: line 209 pins the whole `turnLimits` dict to 900, line 210
expects `turn_seconds_for(routing, "standard") == 900`, line 321 expects a
default thread's budget to be 900 and line 325 expects the failure text
`turn budget exceeded: 15 min`. This ticket moves the routing values to 600,
so those assertions no longer hold, and `python3 verification/check_hub_turn_budget.py`
ends in `FAILED (failures=2)` — the run stops at line 209 and line 321, so
lines 210 and 325 are the ones waiting behind them. The ticket says to report
that conflict rather than edit the test, and the repo's rule forbids editing a
base-branch check without Shyam's quoted approval of the exact edit, so the
check stays red in this branch and the ticket's stop condition is live: the
branch carries the 600-second values, and the PR must not merge until Shyam
says which way it goes — he approves moving the four expectations to 600 and
`10 min`, the same edit MO-174 made when it moved the budget to 900, or he
says the 600-second budget ships with the check left red. The unbuilt
alternative — editing the check here to make the branch green — is exactly
what the ticket forbids without that approval.*

**Gap:** the ticket says report rather than edit, but it does not say whether
Shyam wants the edit in this PR or in a follow-up ticket, and it quotes no
approval for those four lines.

**Reach:** the branch is held for Shyam's direction and the PR stays blocked
until he rules. `verification/check_hub_turn_budget.py` stays red meanwhile;
the four other hub checks and the CI fast-check are green either way.

**Verdict:** needs-user — only Shyam can approve the exact edit, and the repo
rule requires that approval before the check changes.

**Confidence:** high — the failure is deterministic and those four lines are
the file's only builder-value assertions.

**Owner:** `verification/check_hub_turn_budget.py:209`

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
existing turn-budget check owns the assertion once its four lines move.

**Verdict:** sound — the ticket asked for the existing tests unchanged, and the
repo rule reads the absence of a request for new checks as a prohibition.

**Confidence:** medium — a new green assertion would have given the branch a
passing builder check, and Shyam may want one when he approves the edit to the
existing check.

**Owner:** `empryo/config/EMPRYO.md:12`
