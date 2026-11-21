# Model ladder gate

The models are subscriptions, so the gate does not use dollars. It measures pass rate with a paired bootstrap, and uses quota only as a tie-break.

- `run.py` runs the baseline and the candidates together in one run (`--models` lists both), each pi-reachable model on each task `--repeats` times through `heavy harbor run -a pi`, into `runs/<run-id>/` (gitignored). `--dry-run` prints the plan.
- `score.py <run-dir>` writes `reports/<run-id>.json` and `.md`: pass rate per model, task type and split, per-task counts, flaky tasks, and turns and tokens per correct answer side by side. Harbor's `cost_usd` is informational only.
- `gate.py <report>` compares every candidate with the baseline model named in `baseline.json`, using the same run only, and writes `reports/gate-<run-id>.json`. A promotion also writes `proposals/<date>-models.json` and a `.diff`. It never edits `coordinator/models.json`.
- `gate.py --self-check <run-id> <model>` splits one model's repeats into two halves and requires the interval to cover zero.

## Decision rule

Every task is used; the held-out flag stays in the set file and the report, and nothing is tuned on it. Tasks that share a `group` in `evals/harbor/sets/ladder.json` are one cluster. For each cluster the pass rate is correct answers over runs. The gate resamples clusters with replacement (10,000 draws, seed 633) and takes the mean difference, candidate minus baseline.

- Promote when the lower bound of the 90% interval is above zero.
- When the interval lies within plus or minus 0.10, the candidate may win on quota alone, but only if both models share a `quota_unit`, both units are `quota_unit_confirmed` in `providers.json`, and its quota per correct answer is at most 0.67 of the baseline's. All three providers are unconfirmed today, so this path is off.
- Otherwise there is no promotion.

The report prints the interval half-width, which is the gap the run can detect at its cluster count. With 18 tasks that is roughly 20 to 25 points; a 10-point call needs 40 to 60 valid tasks.

## Quota unit

`providers.json` gives each provider a `quota_unit` (`requests`: assistant turns counted from the pi `trajectory.json`; or `tokens`: Harbor's input plus output counts), a `quota_unit_source`, and `quota_unit_confirmed`. A quota figure is UNVERIFIED when any trial lacks the data to count it.

## Mining traces for failed runs

`mine_traces.py` flags real Coordinator failures with deterministic rules and no LLM, so a person labels only the flagged runs.

```
python3 evals/ladder/mine_traces.py --since 2026-11-13
```

It reads `ticks.log`, `decisions.md`, `gatekeep.log`, `gatekeep-stuck.txt`, `lanes.log`, `gh-usage.jsonl` and the pi session jsonl under `~/.pi/agent/sessions/` and `~/.pi/agent-coordinator/sessions/`, prints a count per rule, and writes `traces/flagged-<date>.jsonl` (gitignored). `--since` is a UTC date. Logs without timestamps (`gatekeep.log`) are read whole when the file changed since that date. Other flags: `--max-minutes` (long run threshold, default 60), `--samples` (success samples, default 5), `--seed`, `--out-dir`.

Rules: `tool_failure` (error lines in logs; a pi session with 5 or more failed tool calls or an assistant error), `loop` (the same log line or the same pi tool call with the same arguments 3 or more times in a row), `retry`, `rate_limit` (rate limit, API floor and "optional reads stopped" lines, plus minutes with 60 or more `gh` calls in `gh-usage.jsonl`), `context_overflow`, `long_run` (pi session longer than `--max-minutes`). Runs that no rule flags are sampled at random as `success_sample`.

Each row has `run_id` (stable hash of source, rule and first line), `source`, `start`, `end`, `rule` and `excerpt` (up to 300 characters, secrets redacted; pi sessions give only tool names and error text).

## Labels file

A person writes `traces/labels.jsonl` (gitignored), one row per reviewed run:

```
{"run_id": "ab12cd34ef56", "verdict": "fail", "failure_mode": "gatekeep-aborts-on-missing-ticket", "expected_outcome": "the run skips the missing ticket and continues"}
```

`verdict` is `fail` or `pass` (a success sample or a false flag). `failure_mode` is a short name, empty for `pass`. `expected_outcome` is the checkable result a model must produce on that case. The next ticket builds cases from these rows.

