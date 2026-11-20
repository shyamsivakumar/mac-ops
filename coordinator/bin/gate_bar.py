"""The review bar the gate brief, the build brief and the fix message all read, so the text lives only once."""

REVIEW_BAR = """Review bar:
- Critical: a secret leak, data loss, or a wrong trade or exit.
- Major: a bug at file:line that is likely in this fleet's real use or hard to undo (a merge or push that should not happen, a lane or queue that stays stuck); say who or what triggers it and how often. Also major: a runtime change outside the ticket, a weakened unrelated test, circular proof, a workflow file.
- Minor: everything else, such as a case that needs an unlikely sequence of events, an attacker inside our own agents, or input our own tools never produce. Minors never fail a PR; list them under "Left for later". Only minors left means PASS."""

BUILDER_GATE_NOTE = (
    "The gate reads your PR against this bar. It checks the repo check result on your exact final head "
    "(the `Builder check: PASS <full sha>` line, or `srw/agent-check` in strategy-replay-workbench), "
    "the proof file, and that every changed line traces to the ticket.")

GATE_BAR = """Merge bar, over any stricter proof wording in the ticket: PASS when no critical or major remains and the repo check passed on this exact head (the status or the `Builder check: PASS <head>` line). Missing proof alone never fails a PR: list each missing item the ticket asked for (a suite run, live or device receipts, acceptance artifacts) as a minor under "Left for later" and post the list as a PR comment before merging. Exception: a diff that changes stop logic, exit logic or trade execution (order placement, fills, sizing, booking of executed trades) needs every proof the ticket asks for, and missing proof is major. Say in one line which bar you applied.
Blast radius: for a change that can stop, skip or delay an order or an exit, say what happens to EVERY open trade, unrelated trades included, if the new check fails or throws. A check that fails closed for all trades over one record is major even if the ticket asks for it; flag the ticket. Proofs on exit and order paths that use only clean fixtures are a major gap: real data may hold old id formats, test trades or partial records.
When a question is for Shyam, start it with 'Shyam,' so the board routes it to Needs you; otherwise the question goes to the coordinator."""
