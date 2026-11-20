# Prompt quality runs (v2, after the GPT and DeepSeek critiques)

Branch `prompt-quality`. No PR. `briefs/` holds the v1 prints and is superseded; the v2 prints are in `briefs-v2/`.

## What the briefs are built from

Real gate history of mac-ops #480 (3 FAIL heads, then PASS), read from `prompt-study/gates.json`, with the real full shas:
`7f3b81c6...`, `83236ec1...`, `c29c5936...`. The replies are in the old format (no finding blocks), so they go through the legacy parser. No real gate has produced the new block format yet, so the new-format ledger example is synthetic and labelled that way.

Files in `briefs-v2/`:

| File | What it shows |
| --- | --- |
| `gate-mo-480-round1.txt`, `-round2.txt`, `-round3.txt` | mac-ops: round 1, round 2 (2 prior findings in full, full shas, round diff), round 3 |
| `gate-srw-1244-round1.txt`, `-round2-synthetic-head.txt` | SRW: the trading block is present; round 2 uses a made-up current head because #1244 has one real head |
| `ledger-mo-480-from-real-old-format-replies.json` | ledger written from two real old-format FAIL replies (F1 and F2 superseded when the next legacy reply re-listed the open ones, F3 open) |
| `ledger-srw-1244-from-real-old-format-reply.json` | same for SRW |
| `ledger-synthetic-new-format-two-rounds.json` | synthetic new-format replies: blocks, answers `F1 fixed`, `F2 open`, a new F3 |
| `ledger-reply-without-ids-or-findings.json` | a FAIL reply with no blocks and no findings: ledger records `unparsed` (last 1500 chars) and the next brief shows those lines |
| `fix-checklist-mo-480.txt` | the checklist the lane puts in the fix message, from the round 3 reply |

## Word counts, round 1, no proof file, same inputs in both trees

| Repo | Old brief | New brief | Change |
| --- | --- | --- | --- |
| mac-ops | 811 | 609 | -25% |
| SRW | 811 | 725 | -11% (the trading block is back for SRW only) |

The 30% cut of v1 is gone: the finding block format, the clause ids, the three outcomes and the round-diff rules add about 150 words. Round 2 with two prior findings in full: 794 words (mac-ops). Round 3: 769.

## Changes this round

- New `coordinator/bin/gate_findings.py`: block parser, legacy parser, per-PR ledger at `<COORDQ_DIR>/findings/<owner>_<repo>#<pr>.json` (flock plus atomic replace), brief section and fix checklist. Added to `prompt_paths.py` and the two docs that list it.
- `gate_policy.round_context` reads the previous head's gate reply once, records it, and returns the open findings in full. `ticket gate` and `coordq gatekeep` both call it. The lane records the failed reply (not in dry runs) and puts the same checklist in the fix message.
- Bar clauses C1 to C3, M1 to M5. A critical blocks in any round with a trigger and evidence. Round 2 and later: a major blocks only as an open prior ID, in the round diff, or a repair regression with its causal path.
- Round diff is `git diff <prev>..<head>` with full shas; a rebase check and `git range-diff` are named; the `origin/main...` diff is labelled context only on round 2 and later.
- Outcomes: CHECK, PROVIDES, open findings line, VERDICT FAIL if and only if one fails. Missing extra proof is a minor.
- Round cap sentence in every round. Prompt-PR hold (`PROMPT_NO_MERGE`) is unchanged in `gate_policy.py`.
- Trading and blast-radius text only for `TRADING_REPOS` (SRW).
- Existing tests edited to follow the moved text: `tests/test_gate_bar_convergence.py`, and selftest case (f). No new test files.

## Not touched

`coordinator/config/agents/code-reviewer.md` carries its own copy of the severity bar, so the bar still lives in two places. Its pinned phrases still pass. It should read `REVIEW_BAR` or be rewritten in a follow-up.

## Checks

See `check-proof.md`.
