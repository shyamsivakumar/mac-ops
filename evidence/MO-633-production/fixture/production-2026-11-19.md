# Builder model production signal, 2026-11-19

4 PRs, each counted once. Repos: all. Since: start.

Builder model assignment is not random: harder work may go to different models. Compare models only within a ticket type.

Unknown or missing gate verdicts are never counted as a pass. The pass rate covers PRs whose first gate verdict is known; the unknown column counts the rest. Rounds to PASS count gated heads up to the first PASS. Abandoned means closed unmerged.

| model | type | PRs | first-gate pass | 90% interval | unknown | mean rounds | median rounds | abandoned |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| codex/gpt-a | all | 4 (too few) | 0.333 | [0.0, 0.667] | 1 | 2 | 2.0 | 0.25 |
| codex/gpt-a | feature | 4 (too few) | 0.333 | [0.0, 0.667] | 1 | 2 | 2.0 | 0.25 |
