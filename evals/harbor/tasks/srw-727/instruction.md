# SRW-966 · Bot 2 day compiled into the learner ledger

## Goal and why
Shyam asked whether the daily learner tracks all alerts, entries vs exits and misses for both bots. It does not: the learner has no reader for Bot 2, so Bot 2's day (alerts, entries, exits, P&L, refusals) never reaches the learner ledger. Evidence: evidence/learner-coverage-2026-11-11.md in PR #688 (SRW-965, branch docs/srw-965-learner-coverage), Gap 1.

## Context
strategy_daily_shadow.js (the telegram_day_compiled event at lines 488-500), scripts/railway_learner_start.sh:145-173 (the internal-token fetch pattern), bot2/tv_http.js:318-323 (GET /today?date=). Read only the parts named.

## Stated behavior change
Adds learner-ledger data only: one new bot2_day_compiled event. No trading change.

## Scope and non-goals
In strategy_daily_shadow.js, fetch Bot 2's existing `GET /today?date=<day>` with the same internal-token pattern the launcher already uses, and write one `bot2_day_compiled` event next to `telegram_day_compiled`. Non-goals: any change to bot2, the trader, the launcher script, scoring, or learner promotion (stays off).

## Design fit
Lives in strategy_daily_shadow.js, the owner of the learner ledger events. One file, one fetch, one event. If this can only be bolted on, stop and report before coding.

## Acceptance and proof
A run of the shadow script against a Bot 2 /today response (real captured one or the live read-only endpoint) writes one `bot2_day_compiled` event with the response body for that day; when Bot 2 is unreachable the run still finishes and writes the compile it wrote before. State the exact command and output in the PR.

## Must not cause
Any change to what either bot trades, or to the learner's promotion (stays off).

## Data/secrets and stop conditions
No secrets in the repo or the PR. Paper trading only. Stop and report if a line named above has moved or the work needs another file.

## Approval 2026-11-11 15:35 PT
Shyam: "Yes, add it". First copy BOT2_WEBHOOK_SECRET from production bot2-intake to production srw-learner (Railway project 7eee29d1-22a7-42a4-aec0-8e8552c864c5) with the CLI and --skip-deploys, piping the value so it is never printed, echoed, logged or written to a file; report only "set" and a 6-hex hash-prefix match. Change no other variable. Then the learner fetches Bot 2 GET /today?date= with the x-bot2-secret header from that variable (bot2/tv_http.js) and writes a bot2_day_compiled event next to telegram_day_compiled in strategy_daily_shadow.js.

The repository is at `/app`. Make the change there. Do not edit test files.
