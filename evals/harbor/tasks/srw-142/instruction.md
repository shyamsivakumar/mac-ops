# Deploy rollback image does not boot

# Closing note

The fast-check gate timed out watching `7b21f7ac`.
That SHA was a rebase onto main and was never published.
The gate push is not a force push, so GitHub had no status for it.
The published commit `a3536062` has `ci/woodpecker/push/fast-check` success.
It sat pending in the M1 queue for 58 minutes, then passed.
This branch is back on `a3536062`, so the next gate sees that success.

The rollback fix is unchanged. An empty start argument is accepted.
Any other argument is still refused.
The local Linux replay and `node test_srw228_recovery_guard.js` passed.
No live rollback.

Also noticed:

- `test_telegram_format_jev_fallback.js`: Woodpecker verify failed the
  same `unconsumed_text` assertion on `a3536062` and main. Unrelated.
- `scripts/run_clef_nightly_queue.cjs`: learner crash `Received null`
  in the nightly hash (SRW-218).
- `paper_service.js`: logs already repeated
  `daily_recap_schedule_failed` (SRW-218).

Task: SRW-228 (strategy-replay-workbench/228)

The repository is at `/app`. Make the change there. Do not edit test files.
