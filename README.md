# Mac load tools

`heavy` queues expensive commands and keeps one command active per task. A
single controller adjusts heavy capacity from host readings, grows one slot
after a healthy window, and cuts capacity on pressure. Fresh noncritical
readings restore a baseline of two heavy slots immediately; growth above two
waits for the healthy window. Deploy jobs precede reviews, and reviews precede ordinary jobs. Jobs waiting more than ten minutes move ahead of newer jobs. Only one deploy job can be active at a time.
Running heavy workloads pause after sustained warning pressure and resume after
recovery. Critical kernel pressure, memory use of at least 95%, or the controller's smoothed CPU busy of at
least 95% requests a pause immediately. A supervisor pauses after raw CPU busy
stays at or above 95% for 15 seconds. Heavy admission waits while raw CPU busy
is at or above 95%. Load average is logged, and load per core of at least 2
counts as critical only when a complete sample lacks a CPU reading; a partial sample from a failed collection is critical only at kernel pressure level 4 or memory use of at least 95%, and otherwise holds capacity. Board tasks that are archived or whose herdr socket is gone are not counted as active agents.

The tools run locally without Multica, network services, API keys, or Homebrew
dependencies. Apple Command Line Tools supply Python 3; macOS supplies launchd
and taskpolicy. The repository is the source; installed runtime files are
private copies with a content digest.

## Install on a Mac

Install Apple Command Line Tools first if needed (`xcode-select --install`).
Clone this private repository using your existing GitHub authentication, then
run:

```sh
git clone git@github.com:shyamsivakumar/mac-ops.git ~/Code/mac-ops
cd ~/Code/mac-ops
./install.sh --dry-run
./install.sh
```

Add the wrapper directory to your shell profile if it is absent:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Install from a clean `main` checkout matching `origin/main`; worktrees are
rejected. Run `./install.sh status` and `heavy status`. The installer derives
paths from the current user and copies the checkout into
`~/.local/lib/mac-ops/<content-digest>`. State and logs live in
`~/.local/state/mac-ops`, outside Git. The installation receipt records the main
commit and runtime digest. Reinstall after a reviewed checkout update. Existing
runtime versions stay available for active supervisors and their watchdogs.

Board-worker parity for pi and omp (shared skills, Executor MCP, GPT 6.1 Terra
model ids) is installed from any checkout with `./install.sh agents`; see [board
agent parity](docs/board-agent-parity.md).

Every model the coordinator can start is listed in one file, `coordinator/models.json`;
see [the model list](docs/model-list.md).

Fresh worktrees can use one setup script for npm, pnpm, Bun, uv, hash-locked
pip, Swift package resolve, and CocoaPods. See [shared worktree setup](docs/shared-worktree-setup.md)
for the command, cache behavior, and per-repository setup commands. The script
does not change board settings or install host services.

The installer writes `com.shyam.load-backstop` and `com.shyam.board-governor`
launchd plists. The backstop service runs the single controller for heavy
capacity and board agent limits. The governor plist points to the same
controller, stays unloaded to avoid a second service, and shares its lock to
prevent duplicate controllers. No Homebrew tool is adopted, so the installer
does not invoke brew.

Heavy capacity works without a board installation. Board integration uses
`~/.herdr-projects/data/bin/herdr-projects` when available. The local admission
gate sets `board.agents` through the board command. A fresh valid noncritical
sample restores the floor `min(board ceiling, max(6, active tasks + 1))`, even
when this requires a multi-slot raise. Warning cuts cannot cross that floor;
critical kernel pressure, memory use of at least 95%, or CPU busy of at
least 95% (mean of the last three controller samples) sets the limit to zero.
When the current CPU reading is missing, the board critical check also uses
the last finite CPU reading for up to `max_sample_age_seconds`. The existing
critical load fallback remains active while the current CPU reading is missing.
Smoothed CPU busy of at least 80% is a board warning. Above the floor, the controller raises by one
after 60 healthy seconds only when memory and CPU fit every pending slot.
Missing or stale readings never raise the limit. A completed task closes the
freed spare capacity back to the active count or ready floor and resets the
healthy window. The gate is sampled by the controller; it does not modify the
board plugin or depend on an upstream change. The installer does not change
worker instructions.

## Check a task

Run `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` from the task
worktree. Set the board's `check.command` to that exact command. The check
compares the worktree with the merge base of `origin/main`, checks syntax for
changed Python and shell files, runs existing Python tests that statically import
the changed Python modules, and starts `heavy.py --help`. Use `--plan` to see
the selected files and tests without running them. Dynamic imports and code
without an associated test need separate review.

The check also runs Ruff through `uvx ruff@0.14.0` with the pyflakes and bugbear
rule sets (`F,B`). Ruff is pinned, so the check never installs an unpinned tool.
The findings Ruff reports today are listed in `scripts/ruff-baseline.txt` with
their counts; the check fails only on a finding the baseline does not have. Run
`python3 scripts/mac_ops_fast_check.py --write-ruff-baseline` to write the
baseline again after the known findings are fixed. When Ruff or `uvx` is not on
the machine, the proof file records `not run` and the run is incomplete, so it
is not a pass.

The check runs mypy the same way, through `uvx mypy@1.18.2 --strict`, over the
modules listed in `MYPY_TARGETS` (today `board_resources.py`). Both versions live in
`TOOL_VERSIONS` in `scripts/mac_ops_fast_check.py`; change a version there and
nowhere else. A missing `uvx` or mypy is `not run`, never `passed`.

The check writes a proof file, `evidence/check-proof.md` by default and
`evidence/<KEY>-<issue>/check-proof.md` with `--proof`. The file lists every
check the run made, the command that ran it, and whether the check passed,
failed or did not run. A failed check stops the run, so the checks after it are
`not run`. Commit the proof file with the change: the gate brief reads it, so
the reviewer sees which checks ran and which did not, not one claimed line.

CI uses agent checks only; there are no GitHub Actions or Woodpecker workflows.

## Use heavy

```sh
heavy xcodebuild -scheme MyApp build
heavy --review python3 check_changes.py
heavy --deploy python3 merge_window_gate.py
HEAVY_ROLE=review heavy ./review.sh
heavy status
```

Use one heavy command at a time per task. `HERDR_PROJECTS_ID` identifies the
task; callers outside the board are grouped by their working directory.
Admission also checks fresh CPU, memory, pressure, load and swap readings.
Missing capacity or telemetry holds new work. Environment variables cannot raise
the safety thresholds.

No job keeps its slot past 45 minutes, counting time spent paused or asleep. The job's own
watchdog and every heavy command (including `heavy status`) terminate an
overdue job. `HEAVY_MAX_RUNTIME_SECONDS` may lower the ceiling and never raises
it. The terminated command prints `heavy: terminated: wall-clock limit 45m` and
exits 76. After install, any heavy call ends builds already past the ceiling, and
records created before the change get the 45-minute default counted from their
creation.

Direct xcodebuild commands use shared DerivedData and background scheduling.
Review commands keep ordinary scheduling. Pause and resume preserve work, but a
stopped command retains memory. User interruption and watchdog cleanup remain
explicit termination paths.

## Migrate the existing Mac

```sh
./install.sh install --migrate
./install.sh finalize-migration
```

Migration archives the unused Multica sweep and failover plists, stops the old
backstop after it resumes its paused jobs, and installs compatibility helpers at
the old heavy paths. Active old supervisors keep their original code and
registry. New admissions hold while `legacy-registry.json` exists, so two
registries cannot admit work concurrently.

`finalize-migration` returns exit 75 while a verified legacy workload or helper
remains. Retry after it finishes. Finalization archives the old registry and
enables new admissions. Historical logs remain available under the new state
directory. Keep compatibility helpers until active file references and board
worker instructions have been updated; archive the whole old folder only after
the final usage census. Then run `./install.sh archive-legacy` to move it to
`~/_archive/multica-codex-20261027` without overwriting an existing archive. Do
not run that step while agents still call the old entry point.

## Uninstall

```sh
./install.sh uninstall --dry-run
./install.sh uninstall
```

Uninstall stops the installed launchd controller, moves its plists into
`~/Library/LaunchAgents/_archive`, and moves the wrapper into the state backup
directory. It preserves runtime versions, logs and job state. The board keeps
the last agent limit applied by the controller. Running jobs keep their runtime
files. New jobs should not be submitted after uninstall. No files are deleted,
and Multica services are not restored.

## Verification and lifecycle

The [eval scorecard](docs/evals.md) defines hard stops versus scorecard
metrics for governor and controller changes (LMW-25, ship-and-score
2026-10-28).

The controller is ported from llmwiki commit
`45542a50a2938aaceda41b13806c25b404191e08`. Its memory and swap safety rules
remain independent. See [governor states](docs/state-charts/governor.md) and
[heavy states](docs/state-charts/heavy.md). Installation and migration states
are in [installation states](docs/state-charts/installation.md).
The [state chart index](docs/state-charts/README.md) lists the lifecycle charts.

Pueue provides priority, runtime parallel counts and pause/resume, but adopting
it requires installing its daemon and verifying synchronous caller, exit status,
stdin and process identity behavior. GNU parallel sem provides load and memory
admission but does not replace board admission or the reviewer queue.
`taskpolicy -b` lowers scheduling priority and does not enforce capacity. The
existing heavy registry preserves the active supervision contract while adding
only the queue ordering and capacity reader that the migration needs.

The [TLA+ verification skill](.agents/skills/verify-governor/SKILL.md) documents
the bounded safety and liveness checks. It requires the checksum-pinned TLC jar
from the local llmwiki checkout and an existing OpenJDK 17 installation; neither
is a runtime dependency. Run `heavy --review bash formal/governor/check.sh` for
heavy lifecycle safety and liveness, then `heavy --review bash
formal/governor/check-board-floor.sh` for the current board floor, queued-start
liveness and above-floor growth. Run these sequentially. Use `heavy python3
verify_capacity.py --mutation-check` for the actual-code checks. The older
combined model retains a historical board submodel; the separate board model
owns current board claims.

## Board restart of a dead agent

The controller watches the board once a minute. A row whose agent is gone is
remembered; the same row seen again a minute later is handed to the next model
in the board's own order (`worker.agent`, then `worker.fallback`, freshly read
from `herdr-projects show` for each restart), skipping the model that failed. The new agent is told
what happened. The branch and the worktree stay. The watcher uses only the
board's own commands: `stop`, `archive`, `restore`, `delegate --worker.agent`,
`after` and `tell`. Stop on its own leaves the old omp process and model, so
the task is archived and restored before the new delegate. A wait the task
had is put back with `after`.

A task that is archived, research only, blocked on a question, in review or
finishing is never touched, and neither is a `Could not start` whose cause is
the machine rather than the agent. The note to the new agent waits until that
agent is live in the task's pane, and it is dropped if the row has since become
one of those, or if the agent has already gone. One task is restarted at most
three times an hour, and the whole board six times an hour. A restart whose
command fails counts toward those limits. The config switch
`agent_restart` (on by default) turns the watcher off. See the
[restart state chart](docs/state-charts/restart.md).

## Cursor first-message delivery

The [Cursor input gate](docs/cursor-input-gate.md) queues the board's first
brief until its composer is ready and its draft is visible. The guide covers the
user-level install, exact undo, and verification. Its [state
chart](docs/state-charts/cursor-input.md) records the delivery lifecycle.

## Pi first-message delivery

The [Pi input gate](docs/pi-input-gate.md) queues the board's first brief until
Pi's editor is ready, skips the startup update banner race via
`PI_SKIP_VERSION_CHECK`, and merges `quietStartup` in agent settings. Its
[state chart](docs/state-charts/pi-input.md) records the delivery lifecycle.

## Omp first-message delivery

The [Omp input gate](docs/omp-input-gate.md) queues the board's first brief until
Omp's editor is ready, skips first-run setup races via `OMP_SKIP_SETUP`, and
merges `startup.quiet` in agent settings. Its [state
chart](docs/state-charts/omp-input.md) records the delivery lifecycle.

## Omp Cursor retry

[Omp Cursor retry](docs/omp-cursor-retry.md) provides task-local proof copies
and an explicitly opted-in durable runner behind the existing input gate.
The durable runner reapplies the patch after compatible upstream reinstalls
and refuses incompatible versions; production activation requires explicit
approval. On the fault matrix the patch recovered 6 of 6 safe network failures
(stock: 4 of 6) and did not replay a turn after a write, shell or MCP call in
the exercised stalled-stream watchdog cases.
Its [state chart](docs/state-charts/cursor-retry.md) records retry, veto and
durable-launcher publication paths.

## Coordinator

The `coordq` queue and dispatcher, the `ticket` CLI, `coordinator-refresh`,
`coordstart`, launchd jobs, config and Herdr mods live under `coordinator/` and
install with `./install.sh coordinator`. Config installs to `~/.coordinator`.

The installer derives the command and helper manifest from `coordinator/bin/`,
including Python modules such as `tick_health.py`. It preserves relative paths
and excludes Python bytecode caches. Keep command-local imports in that tree.
After writing files, and on an unchanged install, it runs the installed
`coordq status`, `ticket --help`, and `overnight --help` with
`/opt/homebrew/bin/python3`. Each command must exit successfully; queue status
must be a JSON object containing `cap`. Queue configuration must already exist.
A failure restores replaced files and removes files created by the transaction
before any job reload. Incomplete rollback is an explicit error.
`python3 install_coordinator.py status` reports `healthy` and per-command
`smoke_checks` separately from file synchronization (`in_sync`).
The real-HOME requirement and launchd behavior are unchanged.
See the [ticket 358 acceptance receipt](docs/proofs/ticket-358-acceptance.md) for
synthetic rollback evidence and the explicit live acceptance waiver.

Agents run in T3 Code through `t3mcp`; `coordq dispatch` starts T3 threads.
See [docs/local-tickets-design.md](docs/local-tickets-design.md).

When live plus queued work is below the cap, `coordq dispatch` also refills
from the board: at most once every five minutes it starts the oldest open
`stage:todo` issues of the repos in `tickets.json` through the `ticket` CLI,
until the running threads and the waiting queue reach the cap. The ticket CLI
decides whether an issue may start. Refusals are cached while the board state
is unchanged, with an expiry that allows another attempt. `coordq dispatch --dry-run` reports what a cycle would do and
starts nothing.

The pi coordinator's own files live under `coordinator/pi/` and install with
the same command: the guard extension and its sandbox profile, the pi
settings, the phone relay note and the `coord-pi`, `coord-ask`,
`coord-phone`, `coord-tick`, `kpane` and `kshow` launchers. The guard, profile and settings
install to `~/.pi/agent-coordinator/`, the launchers to `~/.local/bin/`. They
are copies of the live files, so a change to the guard goes through a pull
request like every other change in this repository.

`kpane <image.svg|image.png> [title] [zoom]` shows a diagram in a big popup
over the coordinator: a Herdr overlay, drawn by the `kpane` mod
(`coordinator/mods/kpane`), that Esc closes. The popup is near the full
window, the picture fills it, and `+`, `-` and `Fit` (or the scroll wheel)
enlarge and shrink it; a zoom of 2 starts at twice the size. `kshow
<image.png>` prints one to the terminal with kitty graphics. Both print usage
and exit non-zero on `-h`, `--help`, no arguments or a file that is not
there. `coord-ask` prints usage the same way and never sends a message that
starts with `-`.

The `dev.coordinator.turncap` job runs the coordinator's turn-cap monitor
(`~/Code/coordinator/loop/turn_cap.py`) and keeps it running, so the
ten-minute turn cap keeps holding after a reboot, from the next login on,
instead of only while someone starts the script by hand. The installer writes
the job and creates `~/Library/Logs/coordinator`, because launchd does not
create the directory a job logs into. Load the job once with
`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.coordinator.turncap.plist`;
it then starts by itself at every later login. The monitor has no lock, so a
second copy would double-interrupt threads: the installer warns when it finds
a hand-started monitor, and that copy is stopped before the job is loaded. The
coordinator runbook still says to restart the monitor by hand after a reboot;
this job now covers that step. The job appends one line per poll pass to
`~/Library/Logs/coordinator/turncap.log`. The dispatch job logs into the
coordinator checkout's own `queue/` directory, which that repository owns.

The `dev.coordinator.inbox` job (mac-ops #964) runs one shadow pass of the
event inbox worker (`inbox_worker.py`) every 60 seconds, for the 48-hour shadow run.
Each pass replays the journal into the inbox database and, when a batch is
due, writes one `inbox_would_wake` journal row. It sends nothing, calls no
model and writes nothing to GitHub: the job sets `COORD_INBOX_SHADOW=1` and has
no journal hook, and the worker refuses to run (exit 2) when shadow mode is
off. It polls open pull requests and the CI status of mac-ops and
strategy-replay-workbench with read-only `gh` calls, at most once every 300
seconds (`COORD_INBOX_POLL_EVERY`); a quota below the gateway floor skips that
poll with one log line. It logs a line only when a batch ran or a pass
failed, to `~/Library/Logs/coordinator/inbox.log`. To stop it, run
`launchctl bootout gui/$(id -u)/dev.coordinator.inbox`, move the installed
`~/Library/LaunchAgents/dev.coordinator.inbox.plist` out of `LaunchAgents` (launchd
loads it again at the next login otherwise), and remove
`coordinator/launchd/dev.coordinator.inbox.plist` from the repo, so the
installer does not write it again.

The `dev.coordinator.tick` job runs again (MO-250, mac-ops #267): it fires
the tick every 30 minutes, on DeepSeek, and the installer leaves it alone
(the retired set is empty). The tick reads the whole board but starts no
tickets: the shift and `coordq`'s refill own board intake, so there is one
intake owner. The tick decides, gates, routes failures and reports drift.
The shift's own launchd job (`dev.coordinator.lanes`) fires the shift on
a fixed interval, every day, and is never unarmed. The shift's runbook is
`coordinator/overnight/README.md` in this checkout. The launcher
(`~/.local/bin/coord-tick`) is installed as a tool too: it runs one
ephemeral headless pi (`pi --no-session`, so it never becomes the newest
session that `coord-ask`, the phone relay or the Herdr panel read), it takes
a lock at `~/.local/state/mac-ops/coord-tick.lock` so two ticks never
overlap, and a run over ten minutes is killed. The job's plist pins the
model with `COORD_TICK_MODEL=morph/morph-dsv41flash`, so a tick costs
Morph credits and not Claude plan credits; the launcher's default model
is the same one, and `COORD_TICK_MODEL` overrides it for a manual run.
Only the `ALERT:` lines of a
tick reply are sent to the live pi coordinator terminal; a `NOOP` reply sends
nothing. `coord-pi` exports `COORD_WAKE=0`, so the coordinator session's own
30-minute wake stays off and `/tick` and `/wake on` remain for manual use.

Two stop rules in `coordinator/bin/tick_health.py` (MO-1270, mac-ops #971) add
alarm lines to `tick_alarm()`, so `coord-tick`, `coordq status` and the shift
show them. A held-approval alarm names each PR whose newest `loop code hold` or
`prompt hold` on its newest head is older than `COORD_HELD_HOURS` (default 6)
with no later `merged` or `merged_outside_lane`; it stops after 7 days. An
idle alarm fires when the last `COORD_IDLE_TICKS` (default 8) finished ticks
(`exit=0` in `tick.log`) left no journal row with `data.via_tick` and a gate
FAIL on a PR's newest head has waited through all of them. Both ship off:
`COORD_STOP_RULES=on` turns them on, and any other value reads no file and
prints nothing. A limit that is unset, empty, zero, negative or not a number
uses the default.
Before a PR is named, the rules read it once through `gh_gateway` (`repos/<repo>/pulls/<n>`)
and drop it when it is closed, merged or on another head than the alarmed one
(MO-1272, mac-ops #979). A PR whose state could not be read (failed or bad answer,
invalid repo name, exhausted budget, no `gh`) stays in the alarm with
`(state not read)`. One call reads at most 10 PRs, each with a 10 second timeout and
30 seconds in all; the rest stay as not read. A read answered from the gateway
cache can be up to 2 minutes old (`LIST_TTL`), so a PR merged in the last 2 minutes can alarm
once more. With the switch off nothing is read and `gh_gateway` is not imported.

## Agent session traces (MO-124)

Read-only traces of every T3 build-session run on this Mac, scrubbed and stored
under `~/.local/state/mac-ops/session-traces/`, with a daily eval table in
`session-evals/`. Optional PostHog export uses the same free store as SRW-619
when `POSTHOG_API_KEY` is set (ask the coordinator before creating a key). See
[docs/session-traces.md](docs/session-traces.md); daily command:
`./scripts/session-traces/daily.sh`.

## Worktree cleaner (MO-125)

The [worktree cleaner](docs/worktree-cleaner.md) checks GitHub, local Git state,
and T3 thread state before removing a worktree. Its LaunchAgent runs every 15
minutes when installed; the command defaults to a dry run.

## SRW boot images (MO-160)

Every SRW boot check builds one image per commit, so the boot image tags
accumulate. The prune script lists the images older than 24 hours and
removes them only with `--apply`; the image of the current SRW `main` and
every image a container still uses are kept. See
[docs/srw-image-prune.md](docs/srw-image-prune.md); command:
`python3 scripts/srw_image_prune.py`.

## Reviewer agreement audit (MO-10)

Advisory weekly scorecard for board reviewer flip rate, defect recall, false
blocks, and loop percentiles. Shadow replay uses live `reviewer.instructions`
(ship-and-score). See
[docs/reviewer-audit.md](docs/reviewer-audit.md); weekly command:
`./scripts/weekly-reviewer-scorecard.sh` (or `python3 mo10 scorecard --heavy
--review-policy board --out <report-dir>`).

The [automatic ticket gate](docs/coordq-gatekeep.md) queues checked PR heads through coordq.
The [one pull request gate](docs/ticket-gate.md) (`ticket gate owner/repo#number`) builds the same brief by hand for one pull request.

The [coordinator board snapshot command](docs/coord-watch.md) collects bounded read-only events for the lane.
