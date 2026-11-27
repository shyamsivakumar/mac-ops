# MO-9001 · Fixture for the ticket section matcher

Type: chore · fixture
Goal and why: A local body that writes the section the way the to-tickets skill writes it.
Context: The skill writes "Data, secrets and stop conditions" and the configured name reads "Data/secrets and stop conditions".
Scope and non-goals: One fixture body and one stub for the GitHub read.
Design fit: The marker check stays inside coordinator/bin/ticket.
Blocked by: None.
Acceptance and proof: Run tests/ticket_start_proof.py and read the three outputs.
CI: python3 -m unittest tests.test_ticket_section_headings.
Must not cause: A missing section passing the check.
Data, secrets and stop conditions: Repo files and the local ticket config only; no secrets and no network writes.
Failure behavior: A missing input exits 2 and writes nothing.
Rollback: Revert the change; the CLI returns to exact matching.
Gate: A reviewer reads the diff and the three outputs.
Finish: A ready PR that carries Refs #469 and the three outputs.
