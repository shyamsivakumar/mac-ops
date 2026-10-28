# Reviewer agreement and loop audit

Advisory scorecard for board reviewers (LMW-25 eval 3, MO-10).
Measures flip rate, defect recall, false blocks, recurring requirement
IDs, and review-round loops. **Never blocks a merge.**

## Commands

```sh
cd ~/Code/mac-ops   # or this worktree
python3 mo10 freeze
python3 mo10 loops

# Weekly scorecard (20+ bundles, 5 shadow repeats, mixed models via heavy --review)
python3 mo10 scorecard --out ~/.herdr-projects/reports/mac-ops/10
```

Smoke test without LLM cost:

```sh
python3 mo10 scorecard --out /tmp/mo10-smoke --deterministic --limit 5
```

## Frozen benchmark

`reviewer_audit/manifest.json` lists task id, review round, commit,
cohort (`regression-bad`, `regression-clean`, `history`), adjudicated
requirement IDs, and input hash. Regressions include LMW-10 rounds,
SRW-61, SRW-86 (clean), SRW-73/77 clean passes, plus history to reach
≥20 bundles.

## Shadow replay

Each repeat rotates model family: MiniMax 3.1 Flash (`pi`), GPT 6.1 Sol
(`codex exec`), Claude Opus (`claude -p`). Runs go through
`heavy --review` one job at a time. The prompt is JSON-only pass/fail
plus findings; requirement IDs are derived locally for recall.

## Metrics

| Metric | Definition |
| -------- | ------------ |
| Flip rate | Repeat pairs that change pass/fail on identical input |
| Defect recall | Adjudicated requirement IDs caught in any repeat’s findings |
| False block | Clean bundle (`expected_pass`) failed in any repeat |
| Recurring requirements | Stable IDs repeated across review rounds |
| Loop median / p90 | Review count per task (`tasks/*/task.json`) |

## Mixed-model judge

Optional bounded questions (evidence layer, boundary exercised) use the
same three families; see `reviewer_audit/judge.py`.

## Related

- LMW-25 drop-in: `~/.herdr-projects/reports/llmwiki/25/report.md`
- Board task bundles: `~/.herdr-projects/data/tasks/<repo>/<n>/`
