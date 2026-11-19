# SRW-1216 · Exit watchdog, minimal (re-cut of #1314)

## Goal and why
Re-cut of SRW-1210 PR #1314 (+4165 lines, 3 failed review rounds). Shyam wants a page whenever an exit that is due never reaches the broker.

## Stated behavior change
One small job (inside the existing srw659 alarm service) that every 60 s in market hours, for Bot 1 and Bot 2, reads broker positions and open orders and the bot's own exit decisions, and pages once per trade when the bot has decided an exit (or a CLOSE card is queued, or a 0DTE position is open after 15:50 ET) and no sell order for that position reached the broker within 60 s. It never places orders. Reuse whatever pieces of #1314 are correct.

## Context
PR #1314 branch t3/exit-watchdog-alerts; evidence/bot1-close-2026-11-18/.

## Scope and non-goals
In: the detection and one page per trade. Out: dashboards, history, anything else in #1314.

## Acceptance and proof
Replay of 2026-11-18 13:53 ET (TH-261118-02181/02182 CLOSE cards queued, no sell) pages both within 60 s; a normal replay pages nothing.

## Must not cause
Orders; repeat pages for one trade.

## Design fit
Smallest possible change in the existing owner module; HARD LIMIT about 200 changed lines including tests.

## Interface

The tests use these names and signatures, which the change must provide (names only, no behaviour implied):

- new file `scripts/srw1322_exit_watchdog.cjs`
- `scripts/srw1322_exit_watchdog.cjs`: `function closeDecisions(cards, symbols)`
- `scripts/srw1322_exit_watchdog.cjs`: `function traderDecisions(trades)`
- `scripts/srw1322_exit_watchdog.cjs`: `function botDecisions(trades)`
- `scripts/srw1322_exit_watchdog.cjs`: `function wakeDelayMs({ dueMs, nowMs, intervalMs, lastCheckMs })`
- `scripts/srw1322_exit_watchdog.cjs`: `function createExitWatchdog({ readBroker, readDecisions, page, now = Date.now, graceMs = GRACE_MS, stateFile = null, log = ()`
- `scripts/srw1322_exit_watchdog.cjs`: `function createAlpacaBrokerSource({ key, secret, base = ALPACA_PAPER_BASE, fetchImpl = fetch, now = Date.now })`
- `scripts/srw1322_exit_watchdog.cjs`: `function renderExitMiss(miss)`
- `scripts/srw659_alarm_service.cjs`: `function createExitWatchdogForService({ token, publisherId, channels, bots, alerter, trader = null, log = alarm641.line })`
- `scripts/srw659_alarm_service.cjs`: `method readDecisions()`

The repository is at `/app`. Make the change there. Do not edit test files.
