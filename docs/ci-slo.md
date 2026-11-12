# CI SLO

Measure wait / run / total (p50, p95) per repo and workflow, classify failures
as code / infra / flaky, and target p95 total ≤ 15 minutes with zero infra
failures over a working day.

CI is agent checks only. The Woodpecker report, scheduled job, workflow lint
and server timeout configuration were retired by MO-183.
See [shutdown and rollback evidence](../evidence/MO-183/decisions.md).
