# MO-267 · Gatekeep re-gates a dead head forever when the reviewer cannot run

## Goal and why

Gatekeep re-queues a head whose gate died without a verdict on every 30-second run, with no attempt limit and no backoff. When the reviewer cannot run at all (spend limit, auth failure), this becomes an endless loop: the same heads are relaunched every 30 seconds, each launch burns a thread and a set of tokens, and the queue never settles.

Measured 2026-11-14 09:20 and again 10:43 PT: `queue/gatekeep.log` holds 9 queue lines for `catalouge#120:79b0e1fb`, 8 for `mac-ops#291:3ff45c76` and 6 for `catalouge#117:a886dd2d`, all with `reviewer claudeAgent claude-opus-5-5`, and `coordq gatekeep --dry-run` at 10:44 still prints `would queue gate:...` for all three. Each gate fails in about 20 seconds with the reviewer's own message, "You've hit your individual spend limit", and writes no verdict, so the retry logic treats it exactly like a gate that died from a transient fault.

## Context

- The retry arrived in PR #301 (MO-264, issue #298): "Retry gate heads after a gate dies without a verdict". It fixed a real problem and has no stopping condition.
- The retry test lives in `gatekeep_candidates` and prints `regating <repo>#<n>: <sha> (gate died without a verdict)` before queueing.
- A gate that fails for a reviewer-side reason writes no messages and reports `executedModel` null. A gate that dies from a lost thread or a stall looks the same from the queue's side, so the difference has to come from the retry count, not from the failure text.
- Related but separate: MO-266 (#306) fixes the cap-reservation leak that made each of those relaunches hold a slot for ten minutes.

## Scope and non-goals

In scope: cap the automatic re-gate of a given head, and back off between attempts, so a reviewer that cannot run does not cause a launch every 30 seconds. Announce the give-up once in `queue/gatekeep.log` and stop retrying that head until it changes.

Out of scope: which reviewer is chosen, the vendor split, the gate brief, the manual `coordq gate` command (an operator asking for a gate explicitly still gets it), and MO-266's reservation lifecycle.

## Design fit

The change lives in `gatekeep_candidates` and its queue helper inside `coordinator/bin/coordq`, which already owns the dead-gate retry. The retry count belongs in the existing gate state that `gatedHeads` uses, not in a new file. Stop and report before coding if it cannot live there.

## Acceptance and proof

1. With a head recorded as retried twice without a verdict, `coordq gatekeep --dry-run` prints no `would queue gate:` line for that head and one line naming it as given up.
2. A head that has never been retried still gets its first retry, and a head whose sha changes is retried again.
3. An explicit `coordq gate <repo>#<n>` still queues a gate for a given-up head.
4. Paste the dry-run output before and after in the PR body.

## Must not cause

- A gate that died from a transient fault losing its retry.
- Multiple gate launches for one head in a single run.
- Changes to what the gate checks or which reviewer it uses.

## Data/secrets and stop conditions

No secrets, no network beyond `t3mcp` and `gh`. Stop and report if the fix would need a live install in this ticket.

The repository is at `/app`. Make the change there. Do not edit test files.
