"""The merge bar that every gate brief carries.

Shyam set the bar on 2026-11-16: "yes merge when code is correct". The
text lives here once, so the two brief builders read the same paragraph
instead of each carrying a copy of its own.
"""

GATE_BAR = """Merge bar (Shyam, 2026-11-16). This overrides any stricter proof wording in the ticket.

PASS when all of these hold:
- The diff is correct: no bug you can point to at file:line.
- The diff is scoped to the ticket: no runtime change outside it, no weakened unrelated test, no workflow file, no secret.
- The repo check passed on this exact head (the status or the `Builder check: PASS <head>` line).

Missing proof does not block. If the ticket asks for evidence the builder could not produce (a complete suite run, live or device receipts, acceptance artifacts), list each missing item as a minor finding headed "Left for later" and post that list as a PR comment before merging. Do not FAIL for missing proof alone.

Exception, full proof bar kept: if the diff changes stop logic, exit logic, or trade execution (order placement, fills, sizing, booking of executed trades), every proof the ticket asks for is required, and missing proof is a major finding.

Say in one line which bar you applied and why."""
