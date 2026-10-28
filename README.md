# Mac load tools

`heavy` queues expensive commands and keeps one command active per task. A single controller adjusts heavy capacity from host readings, grows one slot after a healthy window, and cuts capacity on pressure. Fresh noncritical readings restore a baseline of two heavy slots immediately; growth above two waits for the healthy window. Review jobs precede queued build and test jobs. Running heavy workloads pause after sustained warning pressure and resume after recovery. Critical kernel pressure, memory use of at least 95%, or load per core of at least 1.5 requests a pause immediately.

The tools run locally without Multica, network services, API keys, or Homebrew dependencies. Apple Command Line Tools supply Python 3; macOS supplies launchd and taskpolicy. The repository is the source; installed runtime files are private copies with a content digest.

## Install on a Mac

Install Apple Command Line Tools first if needed (`xcode-select --install`). Clone this private repository using your existing GitHub authentication, then run:

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

Install from a clean `main` checkout matching `origin/main`; worktrees are rejected. Run `./install.sh status` and `heavy status`. The installer derives paths from the current user and copies the checkout into `~/.local/lib/mac-ops/<content-digest>`. State and logs live in `~/.local/state/mac-ops`, outside Git. The installation receipt records the main commit and runtime digest. Reinstall after a reviewed checkout update. Existing runtime versions stay available for active supervisors and their watchdogs.

The installer writes `com.shyam.load-backstop` and `com.shyam.board-governor` launchd plists. The backstop service runs the single controller for heavy capacity and board agent limits. The governor plist points to the same controller, stays unloaded to avoid a second service, and shares its lock to prevent duplicate controllers. No Homebrew tool is adopted, so the installer does not invoke brew.

Heavy capacity works without a board installation. Board integration uses `~/.herdr-projects/data/bin/herdr-projects` when available. The local admission gate sets `board.agents` through the board command. A fresh valid noncritical sample restores the floor `min(board ceiling, max(6, active tasks + 1))`, even when this requires a multi-slot raise. Warning cuts cannot cross that floor; critical kernel pressure, memory use of at least 95%, or load per core of at least 1.5 sets the limit to zero. Above the floor, the controller raises by one after 60 healthy seconds only when memory and CPU fit every pending slot. Missing or stale readings never raise the limit. A completed task closes the freed spare capacity back to the active count or ready floor and resets the healthy window. The gate is sampled by the controller; it does not modify the board plugin or depend on an upstream change. The installer does not change worker instructions.

## Use heavy

```sh
heavy xcodebuild -scheme MyApp build
heavy --review python3 check_changes.py
HEAVY_ROLE=review heavy ./review.sh
heavy status
```

Use one heavy command at a time per task. `HERDR_PROJECTS_ID` identifies the task; callers outside the board are grouped by their working directory. Admission also checks fresh CPU, memory, pressure, load and swap readings. Missing capacity or telemetry holds new work. Environment variables cannot raise the safety thresholds.

Direct xcodebuild commands use shared DerivedData and background scheduling. Review commands keep ordinary scheduling. Pause and resume preserve work, but a stopped command retains memory. User interruption and watchdog cleanup remain explicit termination paths.

## Migrate the existing Mac

```sh
./install.sh install --migrate
./install.sh finalize-migration
```

Migration archives the unused Multica sweep and failover plists, stops the old backstop after it resumes its paused jobs, and installs compatibility helpers at the old heavy paths. Active old supervisors keep their original code and registry. New admissions hold while `legacy-registry.json` exists, so two registries cannot admit work concurrently.

`finalize-migration` returns exit 75 while a verified legacy workload or helper remains. Retry after it finishes. Finalization archives the old registry and enables new admissions. Historical logs remain available under the new state directory. Keep compatibility helpers until active file references and board worker instructions have been updated; archive the whole old folder only after the final usage census. Then run `./install.sh archive-legacy` to move it to `~/_archive/multica-codex-20261027` without overwriting an existing archive. Do not run that step while agents still call the old entry point.

## Uninstall

```sh
./install.sh uninstall --dry-run
./install.sh uninstall
```

Uninstall stops the installed launchd controller, moves its plists into `~/Library/LaunchAgents/_archive`, and moves the wrapper into the state backup directory. It preserves runtime versions, logs and job state. The board keeps the last agent limit applied by the controller. Running jobs keep their runtime files. New jobs should not be submitted after uninstall. No files are deleted, and Multica services are not restored.

## Verification and lifecycle

The controller is ported from llmwiki commit `45542a50a2938aaceda41b13806c25b404191e08`. Its memory and swap safety rules remain independent. See [governor states](docs/state-charts/governor.md) and [heavy states](docs/state-charts/heavy.md). Installation and migration states are documented in [installation states](docs/state-charts/installation.md).

Pueue provides priority, runtime parallel counts and pause/resume, but adopting it requires installing its daemon and verifying synchronous caller, exit status, stdin and process identity behavior. GNU parallel sem provides load and memory admission but does not replace board admission or the reviewer queue. `taskpolicy -b` lowers scheduling priority and does not enforce capacity. The existing heavy registry preserves the active supervision contract while adding only the queue ordering and capacity reader that the migration needs.

The [TLA+ verification skill](.agents/skills/verify-governor/SKILL.md) documents the bounded safety and liveness checks. It requires the checksum-pinned TLC jar from the local llmwiki checkout and an existing OpenJDK 17 installation; neither is a runtime dependency. Run `heavy --review bash formal/governor/check.sh` for heavy lifecycle safety and liveness, then `heavy --review bash formal/governor/check-board-floor.sh` for the current board floor, queued-start liveness and above-floor growth. Run these sequentially. Use `heavy python3 verify_capacity.py --mutation-check` for the actual-code checks. The older combined model retains a historical board submodel; the separate board model owns current board claims.
