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
python3 mo10 scorecard --heavy \
  --out ~/.herdr-projects/reports/mac-ops/reviewer-weekly/$(date +%F)

# Automation wrapper (loads board reviewer.instructions, vs MO-10 baseline):
./scripts/weekly-reviewer-scorecard.sh
# Or under load: ~/.local/bin/heavy --review ./scripts/weekly-reviewer-scorecard.sh

# MO-18 rerun with explicit baseline (ship-and-score vs legacy major/critical gate):
python3 mo10 scorecard --heavy --review-policy board \
  --baseline-scorecard ~/.herdr-projects/reports/mac-ops/10/scorecard.json \
  --out ~/.herdr-projects/reports/mac-ops/18
```

Smoke test without LLM cost:

```sh
python3 mo10 scorecard --out /tmp/mo10-smoke --deterministic --limit 5
```

## Frozen benchmark

`reviewer_audit/manifest.json` (version 3) stores the full replay input:
task description, **base-to-head** `git diff` for the reviewed change (with
`diff_base` identity), saved review proof (findings, checks, limitations),
and agent closing note only when it references that commit. Regenerate with
`python3 mo10 freeze`.

## Shadow replay

Each repeat rotates model family (GPT 6.1 Sol, Claude Opus). The prompt
includes the frozen description, source diff, saved proof, commit-scoped
closing note, and **current `reviewer.instructions`** from
`herdr-projects show --repo mac-ops` (ship-and-score pass rule). Use
`--review-policy legacy` to reproduce the MO-10 major/critical gate.
Requirement IDs are derived locally for recall. Failed parses and subprocess
errors set `error=true` on the verdict and are excluded from flip and
false-block denominators.

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
- MO-10 baseline scorecard (legacy policy): `~/.herdr-projects/reports/mac-ops/10/scorecard.json`
- Board task bundles: `~/.herdr-projects/data/tasks/<repo>/<n>/`

### Weekly automation (optional)

```sh
herdr-projects automations add "mac-ops reviewer scorecard" \
  --schedule "mon 09:00" --repo mac-ops \
  --prompt 'Run scripts/weekly-reviewer-scorecard.sh; report vs MO-10 baseline'
```
