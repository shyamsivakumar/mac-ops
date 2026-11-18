# Automatic ticket gates

`coordq gatekeep --dry-run` lists eligible heads without changing queue state.
`coordq gatekeep` queues each eligible head at priority 5000. The existing
`coordq dispatch` job starts it under the existing cap. Installation uses
`./install.sh coordinator` after merge; the installer includes the 60-second
`dev.coordinator.gatekeep` LaunchAgent.

Eligibility requires an open non-draft PR, `Refs #n`, and a
coordinator-ticket receipt on that issue from the authenticated GitHub user.
The dispatch receipt must identify a latest builder run with executedModel evidence.
A build that no receipt covers is found through the ticket key of the issue
(`MO-233`), as the newest thread that is not a review thread.
The reviewer comes from the `review` list in `models.json` (see
[the model list](model-list.md)). The executed model of the builder run decides
which entries are allowed: an entry of the builder's vendor is skipped, and so
is an entry whose provider is blocked, so the reviewer never shares the vendor
of the builder. The first allowed entry gates the PR.
A router run
reports no executed model, and its route is no evidence either: the chain says
what the router would run, not what it ran, and a block that expired since
the build hides the model it fell back to. A route that can run an Anthropic
model therefore leaves the PR ungated, and a route without one is evidence
that the builder is not Anthropic.
Missing executedModel evidence leaves the PR ungated and prints a reason.

A PR that gatekeep skips on the same head three times is stuck. The stuck
pull requests are written to `queue/gatekeep-stuck.txt`, one line per pull
request (`repo#pr head reason`), and the file holds only the pull requests
that are still stuck. `coordq status` reports the same list, so the
coordinator tick sees a gate that cannot run.

SRW requires a successful srw/agent-check status. Other repositories use the
exact full-head `Builder check: PASS <sha>` line unless a publisher status
exists or their tickets.json entry sets `macPublisher: true`.
External-owner repositories and the named Ascend repositories stop at verdict.
Additional Ascend entries can set `ascend: true`.

Queued heads are saved in queue.json's gatedHeads map in the same atomic write
as their queue item. Keep that map across restarts. A recorded gate whose thread is failed, interrupted, or completed without a
final `VERDICT: PASS` or `VERDICT: FAIL` is queued again on the next run.
The old receipt is cleared under the queue lock. Each head is retried at most
once per run. Live gates, gates with verdicts, and missing receipts stay deduplicated.
Dry-run reports `regating` without writing state. A new head can receive a gate.

A gate that dies without a verdict looks the same whether it lost its thread
or its reviewer could not run at all, so the retry is bounded by count, not by
the failure text. A head is retried at most `COORDQ_GATE_RETRY_LIMIT` times
(two by default), the second and later retries wait `COORDQ_GATE_RETRY_BACKOFF`
seconds (300 by default) after the retry before them, and then the head is
given up: one line `gave up gate:<repo>#<pr>:<head> after <n> retries without
a verdict` in `queue/gatekeep.log`, and nothing is queued for that head again.
The retry count lives with the head's queue item in `gatedHeads`, as
`{id, retries, at, givenUp}`, and a bare queue item id is read as a head with
no retry behind it. The record names the head, so a pull request that pushes a
new head starts again at no retries. An explicit `coordq gate <repo>#<pr>`
still queues a given-up head, because an operator asked for it: it keeps the
retry count and is recorded as undecided again, so a second explicit gate for
the same head is refused while that one is live, and if it dies without a
verdict the head is given up again in one line rather than reopening the
automatic retries.
Dry-run still reads GitHub and builder runs. API or malformed-data errors fail
visibly. This command never merges; the reviewer brief permits merge only after
CHECK and VERDICT pass for the exact head, using --match-head-commit.

## The gate moves down the reviewer chain

A gate run that ends without a `VERDICT:` line is retried once on the next
reviewer of the same head: the next entry of the `review` list in
`models.json` that is not blocked and that the head has not been tried on. A
run that ends `VERDICT: PASS` or `VERDICT: FAIL` is a verdict and is never
retried elsewhere. The head record names the reviewer the gate was launched
on (`reviewer`), so a gate that died before it recorded one still moves down
the chain instead of giving the head up.

The choice of the reviewer and the queue item that carries it happen under
`models.blocked_lock()`, the lock the provider block store holds while it
writes `providers-blocked.json`. A block recorded while that lock is held
cannot land between the choice and the append, so a blocked reviewer is never
queued. The block lock is taken before the queue lock, everywhere.

The first reviewer of a head is chosen before the locks are taken, so it is
checked again under them: a reviewer that was blocked in between is not
queued, and the choice is made again on the free reviewer
(`rechoosing <repo>#<pr>: <reviewer> is blocked`). A head with no free
reviewer waits (`defer <repo>#<pr>: every gate reviewer is blocked`).

A head moves to one other reviewer, once. A head that already moved is not
moved again, backoff or not: the next verdictless run gives it up in one line
(`gave up <head> after one move down the reviewer chain without a verdict`).

A loaded LaunchAgent runs after login. Reboot survival requires a real reboot
and has not been demonstrated by plist validation or local checks.
