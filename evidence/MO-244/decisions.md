# MO-244 · coordq fix sends the findings for one head only once

## Goal

`coordq fix <repo>#<pr>` queued the failed gate's findings to the builder every
time it was called. On 2026-11-13 the tick and the interactive coordinator both
called it, so SRW #974, #987 and #999 received the same findings twice
(`dispatch.log` 17:51 to 17:56 PT). A builder that already fixed the findings
may redo the work.

## Change

`coordinator/bin/coordq`, in `cmd_fix` only:

- The key of a fix send is `fix:{repo}#{n}:{head}`, the same shape as the gate
  key `gate:{repo}#{n}:{head}`.
- The queue keeps those keys in a `fixedHeads` map in `queue.json`, the way the
  gates keep theirs in `gatedHeads`.
- `cmd_fix` refuses a head that already has a fix send with
  `refused: findings for this head were already sent as coordq #<id>`. The
  check runs twice, once before the gate thread is read and once inside the
  queue lock next to the append, the same shape as the gate's own two checks.
  Nothing is added to the queue when the call is refused.
- The loop over the dispatch receipts read the loop variable `key`, which
  would have overwritten the fix key. It is now `receipt_key`.

Nothing else changed: the gate selection, the refill, the message text and the
receipt lookup are untouched.

## Behavior

A second `coordq fix` on the same pull request head is refused. A new head
gets a new send.

## Proof

`evidence/MO-244/prove_fix_dedupe.sh` is the rig: a temporary `COORDQ_DIR`, a
temporary `HOME`, a stub `t3mcp` and a stub `gh` that serve one pull request
at a known head whose gate thread ends `VERDICT: FAIL`. The live queue is
never read nor written.

```
=== queue items before: 0

=== first fix on head 1111111111111111111111111111111111111111
queued a finding for shyamsivakumar/strategy-replay-workbench#974 -> builder thread-builder-251
exit=0
=== queue items after the first fix: 1

=== second fix on head 1111111111111111111111111111111111111111
refused: findings for this head were already sent as coordq #1
exit=1
=== queue items after the second fix: 1

=== first fix on the new head 2222222222222222222222222222222222222222
queued a finding for shyamsivakumar/strategy-replay-workbench#974 -> builder thread-builder-251
exit=0
=== queue items after the fix on the new head: 2

=== fixedHeads
{
 "fix:shyamsivakumar/strategy-replay-workbench#974:1111111111111111111111111111111111111111": 1,
 "fix:shyamsivakumar/strategy-replay-workbench#974:2222222222222222222222222222222222222222": 2
}
items: [(1, 't3_thread_send', 'shyamsivakumar/strategy-replay-workbench#974 gate findings'), (2, 't3_thread_send', 'shyamsivakumar/strategy-replay-workbench#974 gate findings')]
```

The queue grew by one item on the first call, the second call refused, and a
new head got its own send.

### The live queue

`~/Code/coordinator/queue/queue.json` was not read nor written by the proof.
It holds no `fixedHeads` after the proof.

## The limit this keeps

`fixedHeads` is never cleared, the same as `gatedHeads`. A head that was fixed
and then dropped from the queue, or whose send failed three times, cannot be
fixed again without editing `queue.json` by hand. The ticket keeps that out of
scope.

## Rollback

Revert the pull request.
