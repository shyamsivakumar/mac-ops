# MO-1134 · Provider blocks expire at their until time, and every written block carries expires_at

## Goal and why

#680 (MO-1122) was started, its builder finished, and nothing landed: no
branch, no pull request. This is the first of two tickets that carry its
remaining work. A provider block with an `until` time but no numeric
`expires_at` never expires, so `openai-api:gpt-6.2-astra` stays blocked past
its `until` and astra-api, the first review entry, is skipped on every gate.

## Context

- `expiry(entry)` in `coordinator/bin/models.py` (about line 256) returns
  `entry["expires_at"]` as a float, and infinity for anything that is not a
  finite number, so an entry with only `until` is permanent.
- `blocked_identities` (about line 272) keeps entries where
  `expiry(entry) > now`, and `read_blocked_file` reads the file under
  `COORDQ_DIR` (`blocked_path`). `block_provider` (about line 288) is the
  writer and takes `blocked_lock`.
- The file is `providers-blocked.json` in the queue dir. Its live entries are
  data: read it to build the replay, do not edit it in the PR.
- Unknown-model entries are those whose model is no longer in `models.json`.
  Stale glm and minimax entries are in the file today.

## Scope and non-goals

In:

- `coordinator/bin/models.py`: `expiry` honours `until` when `expires_at` is
  absent; `block_provider` always writes `expires_at`; the reader prunes
  expired and unknown-model entries.
- `evidence/MO-1134/check-proof.md`: the check proof for the final head.

Out:

- No change to manual blocks (an entry with no `until` and no `expires_at`).
- No edit of the live `providers-blocked.json` in the PR.
- No change to `models.json`.
- The `coordinator/overnight/selftest.py` replays are the next ticket, #1135.

## Design fit

`models.py` owns the block list, its reader and its writer, so the `until`
rule and the always-write-`expires_at` rule both live there and the reader and
writer cannot drift again.

Requires: `origin/main` at `0abe7c50` or later.
Provides: a provider block ends at its `until` time, every written block
carries `expires_at`, and expired and unknown-model entries are pruned on
read.

## Acceptance and proof

1. A block written by `block_provider` has a numeric `expires_at`; show the
   written entry in the proof.
2. An entry with only a past `until` is not blocked, and one with a future
   `until` is blocked; show both in the proof.
3. A manual block with no `until` stays blocked, and an unknown-model entry
   is pruned; show both in the proof.
4.
   evidence/MO-1134/check-proof.md` passes on the final head, and the proof
   file is committed with the change.
5.
   exact head.

Device, handset and live-service testing is waived (Shyam 2026-11-14: "no
testing is needed lets just finish backlog building everything").

## Must not cause

- No manual block (no `until`) pruned or expired.
- No live block lost: an entry with a future `until` or `expires_at` stays
  blocked.
- No write to the live `providers-blocked.json` during the proof.
- No weakening of an existing test to make the check pass.

The repository is at `/app`. Make the change there. Do not edit test files.
