# Prompt quality runs

Branch `prompt-quality`, drafted 2026-11-20. No PR. Full briefs are in `evidence/prompt-quality/briefs/`.

## Word counts (round 1, instructions only, proof file body excluded)

The proof file body is data the builder wrote, so it is left out. Totals include it.

| Brief | Old instructions | New instructions | Change | Old total | New total |
| --- | --- | --- | --- | --- | --- |
| mac-ops #687 gate | 844 | 589 | -30.2% | 1035 | 780 |
| strategy-replay-workbench #1552 gate | 844 | 589 | -30.2% | 2104 | 1849 |

Simulated later rounds (prior findings read from a real earlier gate thread, ledger and receipts in a temp dir):

| Brief | Instruction words |
| --- | --- |
| mac-ops #687, round 2, 2 prior findings | 710 |
| SRW #1552, round 3, 2 prior findings plus the open-findings instruction | 762 |

Build brief, mac-ops #674: 942 words before, 1102 after (+160 words: the short bar and one line on what the gate checks).

## Commands

Read-only. Old briefs come from `git archive origin/main coordinator` into a temp dir.

```
python3 coordinator/bin/ticket gate shyamsivakumar/mac-ops#687 --print-brief
python3 coordinator/bin/ticket gate shyamsivakumar/strategy-replay-workbench#1552 --print-brief
COORDQ_DIR=<tmp> COORDQ_LANE_LEDGER=<tmp>/ledger.json python3 coordinator/bin/ticket gate <ref> --print-brief
```

The round 2 and 3 runs are simulated: the temp ledger says one (mac-ops) or two (SRW) failed reviews, and the temp `dispatch-receipts.json` points at a real past FAIL gate thread of another PR (mac-ops #480, SRW #1244), read with `t3_thread_read`. PR #687 and #1552 have no failed gates of their own.

Build brief: `ticket start <ref> --print-brief` crashes with `KeyError: 'reviewerAlias'` on every ticket tried (#708, #674, #604, #514, #685), in the old tree and the new one, because each was refused and the refusal path builds no reviewer alias. The build briefs were printed by calling `assemble_brief` on the parsed #674 ticket in both trees. That bug is old and not touched here.

## Key excerpts

Round 2 block (new):

```
Previous reviewed head: <prev>; review `git diff <prev>...<head>`. A major must be an unresolved prior critical or major, or sit in lines changed since that head; a new edge case in unchanged code is minor. Say for each prior finding whether it is fixed or open; an open one blocks.
Prior critical and major findings:
- Major — `coordinator/overnight/lane_driver.py:724–725`: ...
```

Round 3 adds the open-findings instruction (`gate_policy.OPEN_FINDINGS_INSTRUCTION`) and "With no PASS the PR is re-cut into smaller PRs or goes to Shyam: no 4th review."

## Checks

See `check-proof.md` (the mac-ops fast check, which runs the unittest suite and the overnight selftest) once it is committed. The fast check ran through `heavy` with a temp `COORDQ_DIR`.
