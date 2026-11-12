# Automatic ticket gates

`coordq gatekeep --dry-run` lists eligible heads without changing queue state.
`coordq gatekeep` queues each eligible head at priority 5000. The existing
`coordq dispatch` job starts it under the existing cap. Installation uses
`./install.sh coordinator` after merge; the installer includes the 60-second
`dev.coordinator.gatekeep` LaunchAgent.

Eligibility requires an open non-draft PR, `Refs #n`, and a
coordinator-ticket receipt on that issue from the authenticated GitHub user.
The dispatch receipt must identify a latest builder run with executedModel evidence.
Claude builders use Sol for review; other builders use Opus 5.5.
Missing executedModel evidence leaves the PR ungated and prints a reason.

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
