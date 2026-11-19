# Model ladder gate

The models are subscriptions, so the gate measures pass rate and quota use, not dollars.

- `run.py` runs each pi-reachable model on each task `--repeats` times through `heavy harbor run -a pi` into `runs/<run-id>/` (gitignored). `--dry-run` prints the plan.
- `score.py <run-dir>` writes `reports/<run-id>.json` and `.md`: pass rate per model, per task type and per split, flaky tasks, and quota use per correct answer. Harbor's `cost_usd` is shown as an informational column only.
- `gate.py <report>...` compares each candidate with the pinned baseline in `baseline.json` and writes `reports/gate-<date>.json`. A promotion also writes `proposals/<date>-models.json` and a `.diff`. It never edits `coordinator/models.json`.

## Quota unit

`providers.json` gives each provider a `quota_unit`: `requests` (assistant turns counted from the pi `trajectory.json`) or `tokens` (Harbor's input plus output token counts). The default is `requests`, and each row states its source. The unit is copied into the run record, so a report carries the unit it was measured in. A quota figure is UNVERIFIED when any trial lacks the data to count it.

## Clear win

On the non-held-out tasks the candidate's pass rate is at least the baseline's minus `max_pass_drop` (0.0), and either its pass rate is higher by `min_pass_gain` (0.10) or its quota per correct answer is at most `max_quota_ratio` (0.67) of the baseline's. On the held-out tasks its pass rate is not below the baseline's by more than `max_pass_drop`. Quota is compared only when both models share a unit; otherwise the candidate can win on pass rate alone, and the report says so. Promotion needs `consecutive_reports` (2) distinct reports that are clear wins and cover the same tasks and repeats as the baseline report.
