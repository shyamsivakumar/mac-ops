# MO-244 · coordq fix sends the findings for one head only once

## Goal

`coordq fix <repo>#<pr>` queued the failed gate's findings to the builder every
time it was called. On 2026-11-13 the tick and the interactive coordinator both
called it, so SRW #974, #987 and #999 received the same findings twice
(`dispatch.log` 17:51 to 17:56 PT). A builder that already fixed the findings
may redo the work.

## Change

`coordinator/bin/coordq`:

- `fix_key(repo, number, head)` builds the key `fix:{repo}#{n}:{head}`, the
  same shape as the gate key `gate:{repo}#{n}:{head}`.
- `prior_fix(queue, key)` reads the `fixedHeads` map of `queue.json`, the way
  the gates read `gatedHeads`.
- `cmd_fix` refuses a head that already has a fix send, before it reads the
  gate thread, with
  `refused: findings for this head were already sent as coordq #<id>`.
- `cmd_fix` records the key and the queue item id in `fixedHeads` under the
  queue lock, so the check and the append are one step. The check is repeated
  inside the lock, so two callers that race both see the first one.

The loop over the dispatch receipts read the loop variable `key`, which would
have overwritten the fix key. It is now `receipt_key`.

Nothing else changed: the gate selection, the refill, the message text and the
receipt lookup are untouched.

## Behavior

A second `coordq fix` on the same pull request head is refused. A new head
gets a new send.

## Proof

A hermetic rig, no live queue: a temporary `COORDQ_DIR`, a temporary `HOME`,
a stub `t3mcp` and a stub `gh` that serve one pull request at a known head
with a gate thread whose last message ends `VERDICT: FAIL`.

### Two fixes on one head

```
=== head 1111111111111111111111111111111111111111 | queue items before: 0
=== first coordq fix ===
queued a finding for shyamsivakumar/strategy-replay-workbench#974 -> builder thread-builder-251
exit=0
=== queue items after the first fix: 1

=== second coordq fix ===
refused: findings for this head were already sent as coordq #1
exit=1
=== queue items after the second fix: 1

=== fixedHeads in queue.json ===
{
 "fix:shyamsivakumar/strategy-replay-workbench#974:1111111111111111111111111111111111111111": 1
}
items: [(1, 't3_thread_send', 'shyamsivakumar/strategy-replay-workbench#974 gate findings')]
```

The queue grew by one item and the second call refused.

### A new head still gets a fix

```
=== fix on head 1111 (first) ===
queued a finding for shyamsivakumar/strategy-replay-workbench#974 -> builder thread-builder-251
exit=0
=== fix on head 1111 (second) ===
refused: findings for this head were already sent as coordq #1
exit=1
=== queue items: 1

=== fix on the new head 2222 ===
queued a finding for shyamsivakumar/strategy-replay-workbench#974 -> builder thread-builder-251
exit=0
=== queue items: 2
{
 "fix:shyamsivakumar/strategy-replay-workbench#974:1111111111111111111111111111111111111111": 1,
 "fix:shyamsivakumar/strategy-replay-workbench#974:2222222222222222222222222222222222222222": 2
}
```

### The live queue

`~/Code/coordinator/queue/queue.json` was not read nor written by the proof.
It holds no `fixedHeads` after the proof.

## Rollback

Revert the pull request.
