"""The review bar the gate brief, the build brief and the fix message all read, so the text lives only once."""

REVIEW_BAR = """Review bar. Every critical or major names the clause it breaks.
- C1 secret leak, C2 data loss, C3 wrong trade or exit: critical. A critical blocks in any round and anywhere in the code, but only with a concrete trigger and evidence.
- M1 a bug at file:line that is likely in this fleet's real use or hard to undo (a merge or push that should not happen, a lane or queue that stays stuck). Also major: M2 a runtime change outside the ticket, M3 a weakened unrelated test, M4 circular proof, M5 a workflow file.
- Minor: everything else, such as a case that needs an unlikely sequence of events, an attacker inside our own agents, or input our own tools never produce. Minors never fail a PR; list them under "Left for later"."""

BUILDER_GATE_NOTE = (
    "The gate reads your PR against this bar. The repo check must pass on your final head, or on an ancestor "
    "whose later commits touch only proof files (the `Builder check: PASS <full sha>` line, or `srw/agent-check` "
    "in strategy-replay-workbench). The gate also reads the proof file and that your diff stays in the ticket. "
    "Its findings come back as numbered blocks (F1, F2) that you answer one by one.")

GATE_BAR = """Merge bar, over any stricter proof wording in the ticket. Three outcomes, each on its own line:
- CHECK: PASS only if the repo check passed on this head, or on an ancestor whose later commits touch only proof files, and the PR head is still this head; else FAIL.
- PROVIDES: the ticket's claims.
- Findings: the count of open critical or major findings.
VERDICT: FAIL if and only if CHECK fails, PROVIDES fails, or a critical or major is open; otherwise PASS. Proof the ticket asks for beyond the repo check (a suite run, live or device receipts, acceptance artifacts) never fails a PR alone: list each missing item as a minor under "Left for later" and post the list as a PR comment before merging. Say in one line which bar you applied.
When a question is for Shyam, start it with 'Shyam,' so the board routes it to Needs you; otherwise the question goes to the coordinator."""

TRADING_BAR = """Trading repo. A diff that changes stop logic, exit logic or trade execution (order placement, fills, sizing, booking of executed trades) needs every proof the ticket asks for, and missing proof is major.
Blast radius: for a change that can stop, skip or delay an order or an exit, say what happens to EVERY open trade, unrelated trades included, if the new check fails or throws. A check that fails closed for all trades over one record is major even if the ticket asks for it; flag the ticket. Proofs on exit and order paths that use only clean fixtures are a major gap: real data may hold old id formats, test trades or partial records."""
