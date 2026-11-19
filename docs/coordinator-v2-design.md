# Coordinator v2: one owner of state, leases, events

Status: proposal, 2026-11-19. Nothing is built. No code changes until Shyam reads this and an outside review is done.

V = VERIFIED (I read the code or the live file). I = INFERRED (from names, logs or commit titles).

## 1. Today

Work moves like this. A ticket is a GitHub issue with a `stage:` label (V). `coordq dispatch` refills free slots from the board and launches a build thread in T3 (V). The builder opens a PR that says `Refs #n` (V). `coordq gatekeep` finds an open PR whose head has a passing check, queues a gate thread at priority 5000, and dispatch starts it (V). The gate ends with `VERDICT: PASS` or `FAIL` (V). On PASS the reviewer brief tells the gate itself to run `gh pr merge --match-head-commit` (V, `gate_policy.py`), and the lane driver also has a merge step (`merge_passed_pr`, V). A FAIL goes back to the builder through `coordq fix` or the lane's fix rounds, with a cap of three rounds (V). After the merge, `ticket close` runs and `install.sh coordinator` installs the result (I for the install trigger).

Shared state. Every file below sits in `~/Code/coordinator/` unless a path says otherwise.

| State | Writers | Readers | Lock | Format |
| --- | --- | --- | --- | --- |
| `queue/queue.json` (412 KB; 2,279 gated heads, reservations, action keys) | coordq: create, drop, dispatch, gatekeep, refill, fix (V) | all coordq commands, lane driver through coordq (V) | flock `queue.lock`, tmp + rename (V) | one JSON object, rewritten whole on every save |
| `queue/dispatch-receipts.json` (562 KB) | coordq dispatch, gatekeep retry (V) | gatekeep, lane driver, overnight (V) | none of its own; fixed `.tmp` name (V) | JSON map of request id to thread id |
| `queue/providers-blocked.json` | `models.py` writer, manual edits (V) | every caller that picks a model | two lock files exist, `.lock` and `-blocked.lock` (V) | JSON with expiry |
| `queue/refill-state.json`, `refill.last`, `dispatch.last`, `config.json` (cap 6), `gatekeep-stuck.txt` | coordq (V) | coordq, `coordq status` (V) | `refill.lock` for refill; none for the rest | small JSON or text |
| `loop/lanes-ledger.json` (606 KB) | lane driver only (V) | lane driver | none; plain `open("w")` plus `json.dump`, not atomic (V) | JSON, indent 1 |
| `decisions.json` (Shyam's board) | lane driver, overnight stall alerts, alarms, the board panel (I for the panel) | the board panel | flock `decisions.json.lock`, with a compare-and-swap fallback (V) | JSON item list |
| `mac-ops-owner.json` (owner board) | alarms (V) | owner panel (I) | flock `.lock` (V) | JSON item list |
| `.overnight/run/`: `stall-state.json`, `mute-state.json`, `policy.json`, `shift-log.md` | overnight shift, alarms, the panel for acks (V) | shift | flock on mute state only (V) | JSON and markdown |
| `.overnight/receipts/` (2,017 files) | overnight (V) | overnight, lane driver | none | one file per receipt |
| `loop/.turn_cap.json`, `caps.log` | `turn_cap.py` (V) | itself | none seen | JSON, log |
| GitHub: `coordinator-ticket` comments (intent and receipt ledger), `stage:` labels, `Builder check` line in the PR body, statuses | ticket CLI, builders, publishers (V) | gatekeep, lane driver, overnight (V) | GitHub | comments, labels, text |
| `~/.local/state/mac-ops/heavy-jobs/` (registry, heartbeats, `events.jsonl`) | `heavy.py` (V) | `heavy.py`, governor tick (V) | flock `.lock`, secured directory (V) | one directory per job |
| `~/.cache/coordinator/gh/`, `~/.cache/tickets/`, `~/Library/Logs/coordinator/gh-usage.jsonl` | gateway, ticket CLI (V) | the same | flock on the usage log (V) | cache files, JSONL |
| T3 thread status (outside our disk) | T3 | coordq, lane driver, gatekeep through `t3mcp` (V) | T3 | T3's own |

The tmp files are visible proof of the race. Eight `decisions.json.<pid>.tmp` files from 2026-11-17 19:31 are still on disk (V).

Polling loops, from the LaunchAgent plists and code.

| Loop | Interval | GitHub cost |
| --- | --- | --- |
| `coordq dispatch` | 30 s (V) | T3 reads. Board refill at most every 300 s through the ticket CLI. |
| `coordq gatekeep` | 180 s in the plist; `docs/coordq-gatekeep.md` says 60 s (V, docs are stale) | Per repo: one PR list. Per open PR with `Refs`: an issue-comments read and a statuses read. Skipped below a 1,500-call floor. |
| `overnight shift` running `lane_driver` | 180 s (V) | `ticket list --fresh`, a PR list and an issue list per repo, and per-PR reads. |
| a second `overnight shift` job | 300 s (V plist; whether the two overlap is I) | The same reads. |
| `turn_cap.py` | 60 s, kept alive (V) | None. T3 reads only. |
| `heavy.py` per job | 2 s sample and 2 s watchdog (V) | None. Local. |
| tick | 1,800 s plist, retired by the README (V) | None. |

Measured from `gh-usage.jsonl`, last hour of a 3.7 hour log: ticket CLI 1,151 core and 612 GraphQL calls, coordq 765 core, lane driver 711 GraphQL, overnight 385 GraphQL, a unit-test run 168 core (V). The log counts only calls that pass through `gh_gateway.py`. It is a library each caller imports, not a process, so a plain `gh` call bypasses it and is not counted (V). It has a floor, a cache, ETag conditional reads and caller names. It has no per-caller budget.

## 2. Failure classes

1. No single owner of state. Ten files have different writers, locks and formats. `decisions.json` was written by two unlocked writers (#617, #618). The ledger is still written without a lock or an atomic rename.
2. No leases. A heavy job holds a slot until a reaper notices it is dead (#624, #630, #642). A gate that dies without a verdict is found by a retry counter and a backoff, not by an expired claim. Stall detection is a separate three-tick counter.
3. Polling instead of events. Six loops ask GitHub or T3 for what changed. Quota drain by gatekeep (#616, #619) follows directly.
4. No dependency between build and gate. Two gates ran on one head and the first PASS merged a PR that another gate had failed (#624). Gate uniqueness is a map entry (`gatedHeads`) plus retries, and the merge is a command inside the gate thread, with the lane also able to merge.
5. Shared, unbudgeted API quota. One floor protects everyone equally, so one caller can drain it. A bulk agent job called `gh` directly and did exactly that.
6. Rules enforced by parsing text. The prompt hold read the PR text and missed brief text embedded in code (#626, ticket #631). Blocked-model sends needed replacement threads whose worktree rules took five gate rounds (the #590 line). Gate rounds looped on constructed edge cases until a stopping bar was added (#641). Each rule lives in a prompt or a regex, far from the push or merge it tries to govern.

## 3. Proposal

**(a) One event log and derived views.** Add one SQLite database in WAL mode, owned by a single small writer process (`coordd`). Every state change is an appended event with a type, a key, a timestamp and a JSON body checked against a versioned schema: `ticket.ready`, `build.claimed`, `build.head_pushed`, `gate.claimed`, `gate.verdict`, `merge.done`, `job.claimed`, `quota.spent`. Today's files become views derived from the log: queue, receipts, ledger, boards. The writer regenerates the JSON files, so panels do not change at first.

The alternative is JSON files behind one writer process. It fixes the races with the least change, but it keeps ten formats, whole-file rewrites (412 KB per queue save) and no history. SQLite ships with Python, serves readers during a write, and gives transactions across what are now separate files. I recommend SQLite. The one-writer rule applies to either choice.

**(b) Leases.** A claim is an event with an owner, an expiry and a renewal. Build threads, gates and heavy jobs each claim a unit of work and renew while alive. An expired lease frees the unit. This replaces the heavy reaper, the gate retry counter and backoff, the stall counter and settle-dead logic. The heavy registry keeps its process-identity check; the lease only decides when a slot is free.

**(c) Events instead of polling.** Run a small local relay that receives GitHub webhooks (through a forwarding tunnel) and appends events. Fallback and reconciliation use `gh api` with ETag conditional requests, which cost no core quota on a 304. Gatekeep, the lane's board reads and refill become consumers that wake on events plus one slow reconcile loop. T3 thread status needs the same treatment if T3 offers a subscription; otherwise it stays polled at a low rate.

**(d) Explicit dependencies.** A gate is a task that depends on a build head and carries the key `(repo, pr, head)` with a unique constraint, so one gate per head exists by construction. A merge is a task that depends on that gate's PASS for the same head. A new head cancels the open gate. This removes the `gatedHeads` map and the second-gate class of bug.

**(e) Per-caller budget in the gateway.** Make the gateway one process (or one shared-memory budget file) that every GitHub call must pass. Each caller gets a named share of the hourly quota. Put a `gh` shim first in the PATH of every agent job so direct calls reach the gateway too. Over-budget calls fail fast and name the caller.

**(f) Rules where the truth is.** A git pre-push hook checks pushes, a path rule where the diff exists. GitHub branch protection requires the gate status on the head, where the plan allows it (open question). One process, `coordd`, owns the merge step. The gate thread reports a verdict as an event and no longer runs `gh pr merge`. The prompt hold becomes a check on the actual diff at merge time. The sibling design `docs/risk-tiers-design.md` defines the protected paths this check reads.

## 4. Migration

Each step ships alone and can be turned off.

1. **Gateway budget and shim.** Add per-caller shares and the PATH shim, in log-only mode first, then enforced. Proof: `gh-usage.jsonl` shows every caller, including a direct `gh` call from a test job, and an over-share caller is refused while others continue. Retires the floor-only protection and the quota incidents. This pays off alone.
2. **One writer for `decisions.json`, the owner board and the ledger.** Route all writes through one function in one process, with atomic rename. Proof: a stress run with eight concurrent writers leaves no lost item and no stray tmp file. Retires the lock fallbacks and compare-and-swap.
3. **Event log, dual-write.** Append events beside today's writes, and compare the log to the files nightly. Proof: zero diffs for a week. Retires nothing yet; it builds the evidence.
4. **Leases for heavy jobs and gates.** Proof: kill a job and a gate mid-run; the slot frees at expiry with no reaper. Retires the reaper, the gate retry counter and the stall counter.
5. **Dependencies and merge ownership.** Gate unique per head, merge as a dependent task, gate thread stops merging. Proof: replay #624 (two gates, one head) and see one gate and one merge. Retires `gatedHeads` and the lane's merge step.
6. **Webhooks with ETag reconcile.** Proof: gatekeep core calls per hour drop to near zero while gate start latency falls. Retires the 180 s and 300 s loops.

## 5. What not to do, costs, risks

Do not rewrite in one go. Do not add an external service unless it removes more than it adds. Vercel Board has the right shapes (leases, dependencies, watchers, schema-checked posts, grants, an audit trail), but it is hosted and experimental, so we copy the shapes and keep a local log. Its article does not say what happens when a lease expires, so we define that ourselves.

Costs: four small modules (log, lease, relay, budget) and a view migration. Risks: the single writer becomes a single point of failure, so it needs a restart policy and a read-only fallback to the generated files. Webhooks need a tunnel, a new exposed surface. Branch protection may need a paid plan. Dual-write drift can hide bugs, so step 3 compares before anything is retired.

Open questions for Shyam.

1. Is SQLite as the one source of truth acceptable, or should the JSON files stay the source of truth behind one writer?
2. Does the GitHub plan for these repos allow required status checks on private repos? If not, the merge step stays the only guard.
3. Is a webhook tunnel acceptable, or should the relay stay ETag-only?
4. Should the gate thread stop merging, so the verdict is an event and one process merges?
5. Are both `overnight shift` LaunchAgents (180 s and 300 s) meant to run? The plists suggest overlap.
6. Does T3 offer thread status events, or must we keep polling it?
