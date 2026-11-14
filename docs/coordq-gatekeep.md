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
Claude builders use Sol for review; other builders use Opus 5.5.
The executed model of the builder run decides the reviewer: a run that
executed a Claude or Anthropic model gets Sol, every other builder gets Opus
5.5, so the reviewer never shares the vendor of the builder. A router run
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
as their queue item. Keep that map across restarts. A failed or dropped gate is
not automatically requeued for the same head. A new head can receive a gate.
Dry-run still reads GitHub and builder runs. API or malformed-data errors fail
visibly. This command never merges; the reviewer brief permits merge only after
CHECK and VERDICT pass for the exact head, using --match-head-commit.

A loaded LaunchAgent runs after login. Reboot survival requires a real reboot
and has not been demonstrated by plist validation or local checks.
