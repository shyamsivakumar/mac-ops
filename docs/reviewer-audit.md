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

`reviewer_audit/manifest.json` (version 2) stores the full replay input:
task description, `git show` diff at the bundle head, saved review proof
(findings, checks, limitations), and agent closing note only when it
references that commit (not a later “final commit” narrative). Cohort,
adjudicated requirement IDs, and input hash cover the same material.
Regenerate with `python3 mo10 freeze`.

## Shadow replay

Each repeat rotates model family (GPT 6.1 Sol, Claude Opus). The prompt
includes the frozen description, source diff, saved proof, and
commit-scoped closing note; requirement IDs are derived locally for
recall. Failed parses and subprocess errors set `error=true` on the
verdict and are excluded from flip and false-block denominators.

## Metrics

| Metric | Definition |
| -------- | ------------ |
| Pairwise flip rate | Share of **valid** repeat pairs with differing result |
| Adjacent transitions | Consecutive valid repeats that change pass/fail |
| Defect recall | Adjudicated requirement IDs caught in any valid repeat |
| False block | Clean bundle (`expected_pass`) with a failing **valid** repeat |
| Recurring requirements | Requirement ID in ≥2 rounds on the **same task** |
| Cross-task prevalence | How often a requirement ID appears in saved reviews |
| Retrospective flips | Saved reviews with identical full input hash |
| Loop median / p90 | Review count per task (`tasks/*/task.json`) |

## Mixed-model judge

Optional bounded questions (evidence layer, boundary exercised) use the
same three families; see `reviewer_audit/judge.py`.

## Related

- LMW-25 drop-in: `~/.herdr-projects/reports/llmwiki/25/report.md`
- Board task bundles: `~/.herdr-projects/data/tasks/<repo>/<n>/`
