# Builder model production signal, 2026-11-19

227 PRs, each counted once. Repos: ['shyamsivakumar/mac-ops']. Since: start.

Builder model assignment is not random: harder work may go to different models. Compare models only within a ticket type.

Unknown or missing gate verdicts are never counted as a pass. The pass rate covers PRs whose first gate verdict is known; the unknown column counts the rest. Rounds to PASS count gated heads up to the first PASS. Abandoned means closed unmerged.

| model | type | PRs | first-gate pass | 90% interval | unknown | mean rounds | median rounds | abandoned |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| claudeAgent/claude-sonnet-5-5 | all | 18 | 0.111 | [0.0, 0.222] | 0 | 1 | 1.0 | 0.444 |
| claudeAgent/claude-sonnet-5-5 | design | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | - | - | 0.0 |
| claudeAgent/claude-sonnet-5-5 | standard | 17 | 0.118 | [0.0, 0.235] | 0 | 1 | 1.0 | 0.471 |
| codex/gpt-6.1-sol | all | 48 | 0.571 | [0.286, 0.857] | 41 | 1.83 | 1.0 | 0.0 |
| codex/gpt-6.1-sol | risky | 40 | 0.571 | [0.286, 0.857] | 33 | 1.83 | 1.0 | 0.0 |
| codex/gpt-6.1-sol | standard | 8 | - | - | 8 | - | - | 0.0 |
| glm/zai/glm-5.3 | all | 7 | 0.0 | [0.0, 0.0] | 0 | - | - | 0.571 |
| glm/zai/glm-5.3 | risky | 3 (too few) | 0.0 | [0.0, 0.0] | 0 | - | - | 0.667 |
| glm/zai/glm-5.3 | standard | 4 (too few) | 0.0 | [0.0, 0.0] | 0 | - | - | 0.5 |
| minimax/minimax/MiniMax-M3.1-Flash | all | 18 | 0.2 | [0.067, 0.4] | 3 | 1.8 | 1 | 0.444 |
| minimax/minimax/MiniMax-M3.1-Flash | chore | 1 (too few) | - | - | 1 | - | - | 0.0 |
| minimax/minimax/MiniMax-M3.1-Flash | design | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | 2 | 2 | 0.0 |
| minimax/minimax/MiniMax-M3.1-Flash | risky | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | - | - | 1.0 |
| minimax/minimax/MiniMax-M3.1-Flash | standard | 15 | 0.231 | [0.077, 0.462] | 2 | 1.75 | 1.0 | 0.467 |
| pi/claude-sonnet-5-5 | all | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | 3 | 3 | 0.0 |
| pi/claude-sonnet-5-5 | design | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | 3 | 3 | 0.0 |
| pi/deepseek/deepseek-flash | all | 6 | 0.0 | [0.0, 0.0] | 0 | 2 | 2 | 0.167 |
| pi/deepseek/deepseek-flash | chore | 1 (too few) | 0.0 | [0.0, 0.0] | 0 | 2 | 2 | 0.0 |
| pi/deepseek/deepseek-flash | standard | 5 | 0.0 | [0.0, 0.0] | 0 | - | - | 0.2 |
| router/task/chore | all | 22 | 0.667 | [0.417, 0.917] | 10 | 1.45 | 1 | 0.0 |
| router/task/chore | chore | 22 | 0.667 | [0.417, 0.917] | 10 | 1.45 | 1 | 0.0 |
| router/task/research | all | 11 | 0.7 | [0.4, 0.9] | 1 | 1.12 | 1.0 | 0.182 |
| router/task/research | research | 11 | 0.7 | [0.5, 0.9] | 1 | 1.12 | 1.0 | 0.182 |
| router/task/standard | all | 80 | 0.708 | [0.604, 0.812] | 32 | 2.27 | 1.0 | 0.05 |
| router/task/standard | standard | 80 | 0.708 | [0.604, 0.812] | 32 | 2.27 | 1.0 | 0.05 |
| router/task/ui | all | 1 (too few) | 1.0 | [1.0, 1.0] | 0 | 1 | 1 | 0.0 |
| router/task/ui | ui | 1 (too few) | 1.0 | [1.0, 1.0] | 0 | 1 | 1 | 0.0 |
| unknown | all | 15 | 0.133 | [0.0, 0.267] | 0 | 3.88 | 2.0 | 0.067 |
| unknown | standard | 11 | 0.091 | [0.0, 0.273] | 0 | 1.75 | 2.0 | 0.091 |
| unknown | unknown | 2 (too few) | 0.5 | [0.0, 1.0] | 0 | 3.5 | 3.5 | 0.0 |
| unknown | untyped | 2 (too few) | 0.0 | [0.0, 0.0] | 0 | 8.5 | 8.5 | 0.0 |
