"""The merge bar both gate brief builders read, so the text lives only once."""

SEVERITY_BAR = """Severity bar (Shyam, 2026-11-19). This applies to every gate:
- A finding is critical or major only when it is likely to happen in this fleet's real use, or would cause harm that is hard to undo: data loss, a merge or push that should not happen, a lane or queue that stays stuck, a secret leak, a wrong trade or exit. State in one sentence how it happens in practice: who or what triggers it, and how often.
- A case that needs an unlikely sequence of events, an attacker inside our own agents, or input our own tools never produce is minor. Minors never fail a PR. List them under 'Left for later'; the Coordinator turns them into a follow-up issue.
- A proof or check that fails the same way on origin/main is pre-existing: note it as minor, not the PR's finding. One that fails only on this PR's head, or fails differently, is the PR's finding. Compare against origin/main before calling a proof failure major.
- If every remaining finding is minor, the verdict is PASS."""

GATE_BAR = (
    """Merge bar (Shyam, 2026-11-16). This overrides any stricter proof wording in the ticket.

PASS when all of these hold:
- The diff is correct: no bug you can point to at file:line.
- The diff is scoped to the ticket: no runtime change outside it, no weakened unrelated test, no workflow file, no secret.
- The repo check passed on this exact head (the status or the `Builder check: PASS <head>` line).

Missing proof does not block. If the ticket asks for evidence the builder could not produce (a complete suite run, live or device receipts, acceptance artifacts), list each missing item as a minor finding headed "Left for later" and post that list as a PR comment before merging. Do not FAIL for missing proof alone.

Exception, full proof bar kept: if the diff changes stop logic, exit logic, or trade execution (order placement, fills, sizing, booking of executed trades), every proof the ticket asks for is required, and missing proof is a major finding.

Say in one line which bar you applied and why.

"""
    + SEVERITY_BAR
    + """

Convergence rule (Shyam, 2026-11-18 09:55 PT, from Fable's review). This applies to every gate:
- Round 1 must list every critical and major found, not just the first.
- Round 2 and later: raise only findings in lines changed since the previous reviewed head, plus any earlier critical or major still open. Anything else you notice is a minor under 'Left for later'.
- Earlier findings: confirm each is fixed; an unfixed earlier major still blocks.
- After 3 review rounds without PASS, the PR is re-cut into smaller PRs or brought to Shyam; no 4th review as is.

Failure blast radius (Shyam, 2026-11-18, after a sell-recovery check blocked every Bot 1 exit for 1.5 days):
- For any change that can stop, skip or delay an order or an exit, state what happens to EVERY open trade when the new check fails or throws, and to trades unrelated to the bad input. A check that fails closed for all trades because of one record is a major finding, even if the ticket asks for it; flag the ticket instead.
- Ask whether real production data could contain inputs the tests do not (old id formats, test trades, partial records). If the PR's proofs only use clean fixtures, list that as a major gap for exit and order paths.

When a question is for Shyam, start it with 'Shyam,' so the board routes it to Needs you; otherwise the question goes to the coordinator."""
)
