# Why terra is first in the build list (#633)

Source: all-repos builder model production report, 2026-11-19, 607 PRs, read from
`evidence/MO-633-production/all-repos/production-2026-11-19.md` on branch
`origin/t3/ladder-production-signal`. Rows are the "all" type rows.

| model | PRs | first-gate pass | 90% interval | mean rounds to PASS |
| --- | --- | --- | --- | --- |
| terra (codex/gpt-6.1-terra) | 56 | 0.667 | [0.5, 0.833] | 1.08 |
| minimax (MiniMax-M3.1-Flash) | 29 | 0.174 | [0.043, 0.304] | 1.71 |
| glm (zai/glm-5.3) | 12 | 0.2 | [0.0, 0.4] | 1.33 |
| deepseek (pi/deepseek-flash) | 17 | 0.176 | [0.059, 0.353] | 2.38 |
| sonnet (claudeAgent/claude-sonnet-5-5) | 23 | 0.087 | [0.0, 0.174] | 4.67 |

Cursor has no data in the report.

The pass rate covers PRs whose first gate verdict is known. Terra has 38 PRs with
an unknown verdict, minimax 6, glm 2, deepseek 0, sonnet 0.

## Limits of this signal

Builder assignment was not random, so harder work may have gone to different
models. This is the best available signal, not a controlled test.

Terra is also first in the fix list. Build and fix now share the Codex quota. The
fallback order is unchanged: when Codex is blocked, the build list continues with
minimax.
