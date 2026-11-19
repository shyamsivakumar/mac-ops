# Builder model production signal, 2026-11-19

607 PRs, each counted once. Repos: all. Since: start.

Builder model assignment is not random: harder work may go to different models. Compare models only within a ticket type.

Unknown or missing gate verdicts are never counted as a pass. The pass rate covers PRs whose first gate verdict is known; the unknown column counts the rest. Rounds to PASS count gated heads up to the first PASS. Abandoned means closed unmerged.

| model | type | PRs | first-gate pass | 90% interval | unknown | mean rounds | median rounds | abandoned |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| claudeAgent/claude-sonnet-5-5 | all | 23 | 0.087 | [0.0, 0.174] | 0 | 4.67 | 1 | 0.348 |
| claudeAgent/claude-sonnet-5-5 | design | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | - | - | 0.0 |
| claudeAgent/claude-sonnet-5-5 | risky | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | - | - | 0.0 |
| claudeAgent/claude-sonnet-5-5 | standard | 21 | 0.095 | [0.0, 0.19] | 0 | 4.67 | 1 | 0.381 |
| codex/gpt-6.1-sol | all | 187 | 0.704 | [0.593, 0.796] | 133 | 1.35 | 1 | 0.016 |
| codex/gpt-6.1-sol | design | 71 | 0.826 | [0.696, 0.957] | 48 | 1.24 | 1 | 0.014 |
| codex/gpt-6.1-sol | risky | 97 | 0.633 | [0.5, 0.767] | 67 | 1.4 | 1 | 0.021 |
| codex/gpt-6.1-sol | standard | 19 | 0.0 | [0.0, 0.0] | 18 | 3 | 3 | 0.0 |
| codex/gpt-6.1-terra | all | 56 | 0.667 | [0.5, 0.833] | 38 | 1.08 | 1 | 0.054 |
| codex/gpt-6.1-terra | chore | 5 | 0.0 | [0.0, 0.0] | 4 | - | - | 0.0 |
| codex/gpt-6.1-terra | design | 4 (too few) | 0.0 | [0.0, 0.0] | 2 | - | - | 0.0 |
| codex/gpt-6.1-terra | risky | 20 | 1.0 | [1.0, 1.0] | 17 | 1 | 1 | 0.1 |
| codex/gpt-6.1-terra | standard | 27 | 0.75 | [0.583, 0.917] | 15 | 1.1 | 1.0 | 0.037 |
| glm/zai/glm-5.3 | all | 12 | 0.2 | [0.0, 0.4] | 2 | 1.33 | 1 | 0.333 |
| glm/zai/glm-5.3 | chore | 1 (too few) | 1.0 | [1.0, 1.0] | 0 | 1 | 1 | 0.0 |
| glm/zai/glm-5.3 | research | 1 (too few) | - | - | 1 | - | - | 0.0 |
| glm/zai/glm-5.3 | risky | 4 (too few) | 0.0 | [0.0, 0.0] | 1 | - | - | 0.5 |
| glm/zai/glm-5.3 | standard | 6 | 0.167 | [0.0, 0.5] | 0 | 1.5 | 1.5 | 0.333 |
| minimax/minimax/MiniMax-M3.1-Flash | all | 29 | 0.174 | [0.043, 0.304] | 6 | 1.71 | 1 | 0.448 |
| minimax/minimax/MiniMax-M3.1-Flash | chore | 1 (too few) | - | - | 1 | - | - | 0.0 |
| minimax/minimax/MiniMax-M3.1-Flash | design | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | 2 | 2 | 0.0 |
| minimax/minimax/MiniMax-M3.1-Flash | research | 6 | 0.167 | [0.0, 0.5] | 0 | 1.5 | 1.5 | 0.5 |
| minimax/minimax/MiniMax-M3.1-Flash | risky | 6 | 0.0 | [0.0, 0.0] | 3 | - | - | 0.5 |
| minimax/minimax/MiniMax-M3.1-Flash | standard | 15 | 0.231 | [0.077, 0.385] | 2 | 1.75 | 1.0 | 0.467 |
| pi/claude-sonnet-5-5 | all | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | 3 | 3 | 0.0 |
| pi/claude-sonnet-5-5 | design | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | 3 | 3 | 0.0 |
| pi/deepseek/deepseek-flash | all | 17 | 0.176 | [0.059, 0.353] | 0 | 2.38 | 2.0 | 0.059 |
| pi/deepseek/deepseek-flash | chore | 2 (too few) | 0.0 | [0.0, 0.0] | 0 | 2 | 2.0 | 0.0 |
| pi/deepseek/deepseek-flash | design | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | 5 | 5 | 0.0 |
| pi/deepseek/deepseek-flash | risky | 3 (too few) | 0.0 | [0.0, 0.0] | 0 | - | - | 0.0 |
| pi/deepseek/deepseek-flash | standard | 11 | 0.273 | [0.091, 0.545] | 0 | 2 | 1 | 0.091 |
| router/task/chore | all | 57 | 0.655 | [0.517, 0.793] | 28 | 1.26 | 1 | 0.018 |
| router/task/chore | chore | 57 | 0.655 | [0.517, 0.793] | 28 | 1.26 | 1 | 0.018 |
| router/task/research | all | 21 | 0.778 | [0.611, 0.944] | 3 | 1.12 | 1.0 | 0.095 |
| router/task/research | research | 21 | 0.778 | [0.611, 0.944] | 3 | 1.12 | 1.0 | 0.095 |
| router/task/standard | all | 157 | 0.667 | [0.586, 0.747] | 70 | 2.97 | 1.0 | 0.051 |
| router/task/standard | large | 1 (too few) | 1.0 | [1.0, 1.0] | 0 | 1 | 1 | 0.0 |
| router/task/standard | standard | 156 | 0.663 | [0.581, 0.744] | 70 | 3 | 1 | 0.051 |
| router/task/ui | all | 17 | 0.364 | [0.182, 0.636] | 6 | 1.86 | 1 | 0.176 |
| router/task/ui | ui | 17 | 0.364 | [0.182, 0.636] | 6 | 1.86 | 1 | 0.176 |
| unknown | all | 30 | 0.24 | [0.12, 0.36] | 5 | 3.08 | 2 | 0.033 |
| unknown | chore | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | - | - | 0.0 |
| unknown | design | 2 (too few) | - | - | 2 | - | - | 0.0 |
| unknown | standard | 13 | 0.167 | [0.0, 0.333] | 1 | 1.6 | 2 | 0.077 |
| unknown | ui | 2 (too few) | - | - | 2 | - | - | 0.0 |
| unknown | unknown | 6 | 0.5 | [0.167, 0.833] | 0 | 2.8 | 1 | 0.0 |
| unknown | untyped | 6 | 0.167 | [0.0, 0.5] | 0 | 6 | 7 | 0.0 |
