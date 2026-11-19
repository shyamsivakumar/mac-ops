# MO-1085 · Prompt rule: questions to Shyam end with numbered options and a Recommended line

## Goal and why
Shyam approved (2026-11-17, in the Herdr setup session, relayed by t1j): agent questions to Shyam should be answerable with one key on the board. The board's Needs-you cards will turn a fixed answer format into buttons (herdr/quick-answers, being built by the Herdr session).

## Stated behavior change
Builder, reviewer and gate thread prompts get one rule: when a turn ends by asking Shyam something, end with the question on one line, then 2 to 4 options as lines `1. <option>`, `2. <option>` ..., and a final line `(Recommended: <option text word for word>)`. No other prompt text changes.

## Context
Builder prompt prefix: AGENT-RULES (installed at ~/.coordinator/AGENT-RULES.md, source in mac-ops); gate and review briefs: gate_bar.py and the ticket gate brief in mac-ops. Find every place these prompts come from before editing; one shared sentence is better than three copies if the code allows it.

## Design fit
Add the rule once in the shared rules text that all three prompts include; if there is no shared text, add the identical sentence to each source and note it.

## Scope and non-goals
In: the one rule. Out: any other prompt change; board code (Herdr session).

## Acceptance and proof
`ticket start --dry-run` and `ticket gate --print-brief` on an open ticket show the rule in the builder and gate prompts; the reviewer prompt shows it too. Repo check passes; `Builder check: PASS <full head sha>`.

## Must not cause
Other prompt changes; auto-merge.

## Data/secrets and stop conditions
No secrets. 10 minutes.

The repository is at `/app`. Make the change there. Do not edit test files.
