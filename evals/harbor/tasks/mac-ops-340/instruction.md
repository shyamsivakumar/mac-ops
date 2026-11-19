# MO-1000 · Restrict gate fallback to explicit Astra quota exhaustion

## Goal and why

Restrict gate fallback to explicit Astra quota exhaustion

## Context

Refs #335. Remaining work re-cut after orphaned builder receipt #4640. Thread read returned thread_not_found; no builder report or branch could be recovered. Start from origin/main (inspected 8c93527bba09fcda8c3cf033c7ca9aa11ee9f5b0). Lane: /Users/shyamsivakumar/Code/coordinator/specs/lane.md.

## Scope and non-goals

One five-minute builder turn. quota_failure, fallback_reviewer and both existing dispatch-failure and completed/no-verdict callers. Accept explicit quota exhaustion only when the failed selection is ASTRA_MODEL; select OPUS_MODEL once. Reject generic 429, rate_limit alone, transport errors, missing verdicts, unknown models, non-Astra quota and exhausted Opus. Remove gateReviewers history as independent switching permission. Preserve builder fallback. Do not implement the infrastructure retry counter in this slice. No live operations or workflow files.

## Design fit

Existing coordinator/bin/coordq owns routing. Reuse existing model constants and queue state; no parallel controller.

## Acceptance and proof

Inspect both callers and refusal cases against the stated scope. External pass criterion: exact-head agent check and reviewer confirm the stated routing. Device, owner and live-service tests are waived by Shyam.

## Must not cause

No secret reads, test weakening, main pushes, force pushes, bypasses or unrelated changes.

The repository is at `/app`. Make the change there. Do not edit test files.
