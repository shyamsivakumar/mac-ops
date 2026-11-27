# MO-1146 (#743): time-split held-out cases

Source: real answered decisions from `build_labels.py` (coordinator pi session logs). The flagged trace file (3,743 runs) has no options, recommendation or answer, so it cannot become a case the locked scorer reads. Case text is not committed (the repo is public); `install_heldout.py` regenerates it from the local sources.

Cutoff: newest installed label, `2026-11-23T21:00:54.939952+00:00` (computed by the script). A case must be newer, have options, a `recommended_option`, and an `answer` that equals one option, which is what `score.py` needs.

## Run (copies of the installed labels in the scratchpad; the installed dir was not touched)

    score.py locked --arm first-option --baseline random --repeats 5

| Set | n scored | unscored | lift | paired SE | min detectable lift (2 x SE) |
| --- | --- | --- | --- | --- | --- |
| installed held-out (22 ids) | 19 | 3 | 7.37 | 5.12 | 10.24 |
| after `install_heldout.py` (28 ids) | 25 | 3 | 4.00 | 4.47 | 8.94 |

- New cases: 6 (three recut cards, one merge card, one size-exception card, one merge-mac-ops#989).
- Dropped for Ascend, slash-eureka, useascend or a secret pattern: 0 of 6 scorable.
- A second install finds 0 new cases (idempotent).
- 7 more post-cutoff answers exist but score.py cannot count them: 4 have options yes/no with a free-text answer such as "Merge #1057", 3 have no options. Mapping "Merge #1057" to "yes" is a separate change to `pick_option`.
- 60 cases is time-bound: about 6 cases in 4 days (1.5 a day) reach the set.
- The installed labels.jsonl has 5 rows that match the Ascend filter (none held-out). They were not touched.

## Daily 3 answers

`coordq decision answered` writes a `decision_answered` journal row with `item` and `kind` only, no answer text (coordq `cmd_decision`). Daily 3 cards are raised as `daily3-<date>-<label_id>`. build_labels.py reads answers only from `Decisions:` user messages in coordinator pi sessions. No `daily3-` id appears in any session log or decisions.json yet, and PR #1069 states answered cards leave decisions.json without their answers. So answered Daily 3 cards do not reach the set; `daily3.py record` is the only path, and it is manual.
