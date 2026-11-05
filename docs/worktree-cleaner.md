# Worktree cleaner (MO-125)

**Safety hold:** This tool is inventory-only. Both `--apply` and `--prune` hold every worktree; no worktree or branch is removed. The hub listing excludes archived threads and has no atomic lease preventing a task or process from starting during removal. Git also permits ignored unsaved files, so clean status is not sufficient. Do not install this job as a cleanup solution. Empryo's separate cleanup/merge commands are not governed by this safety hold. The legacy `check.py` fixture expects removals and currently fails; it has not been changed. Run `python3 verification/worktree-cleaner/check_gate_safety.py` for the new hold regressions.

The cleaner discovers repositories under `~/Code` and considers their registered linked worktrees under `~/Code/.worktrees`, `/private/tmp`, `/tmp`, `~/.empryo-hub/worktrees` (the Empryo hub root, overridable with `--hub-root`), and any worktree nested beneath a `.empryo/tmp` directory. It skips the main checkout and keeps a worktree unless every required check passes. A worktree registered anywhere else is held as `worktree_outside_scope`.

## Checks

A branch worktree must be clean, have its exact `HEAD` commit available through GitHub, and have a closed or merged pull request whose head SHA exactly matches that `HEAD`. Any open pull request for the branch blocks removal. A detached worktree must be clean, its exact commit must be available through GitHub, and its latest `HEAD` reflog entry must be at least 24 hours old.

The cleaner queries `emp call emp_thread_list` across all projects, following every cursor with a limit of 100. Two complete passes must agree on thread identity, paths, status, settled state, active run, and pending requests; any change blocks cleanup because the hub has no snapshot token. Both `worktreePath` and `cwd` (including a cwd beneath a worktree) protect a path. Every unfinished thread blocks removal: idle, snoozed, waiting, unknown-status, and completed-but-unsettled threads included. Only explicitly settled terminal threads without an active run or pending request are finished. Missing or malformed path data, hub failures, incomplete pages, duplicate threads, non-progressing cursors, and changing totals fail closed. These are advisory inventory checks, not a removal authorization: archived threads are omitted and snapshots are not atomic with task starts. No retired T3 database is read.

The cleaner never deletes remote branches and never uses `git worktree remove --force`. The former SRW and slash-eureka `dbt`/`omni` exclusions were removed in MO-129 with explicit promotion confirmation; every repository now follows the same checks, and a completed review thread's detached worktree is removable only through the same 24-hour detached-idle rule.

A worktree that contains another checkout inside it is held as `contains_nested_worktree`. `git worktree remove` deletes a worktree's whole folder, so removing a parent would destroy a nested child — or a vendored clone that Git ignores, which Git would otherwise delete without asking — and the nested checkout's own clean, unpushed, pull-request, thread, and process checks would never have run. All worktrees remain held regardless of whether nested content is found. The check covers registered worktrees and nested folders carrying their own `.git`, including ignored dependency folders at any depth. If a folder cannot be read or the scan exceeds its directory budget, the candidate is held as `nested_scan_incomplete` rather than guessed at. Run `python3 verification/worktree-cleaner/check_nested_depth.py` for the deep-nesting regression.

## Run a scan

The command defaults to dry-run and prints JSON counts per repository and for scanned worktrees, eligible items, holds, and hold reasons. It writes the current day's dirty or unverified list to `~/Code/coordinator/evidence/worktrees-kept-<date>.md`.

```sh
python3 scripts/worktree-cleaner/cleaner.py --dry-run
```

The daily report is replaced by each scan with the newest snapshot. The append-only `~/.local/state/mac-ops/worktree-cleaner.log` records an attempt before Git runs, then records success or failure. Each entry includes the path, branch, commit, pull request, time, and reason. State files use private permissions.

## LaunchAgent

If separately installed, the checked-in plist schedules `scripts/worktree-cleaner/daily.sh` every 900 seconds from the main `~/Code/mac-ops` checkout. The daily script passes `--apply`, but removal is disabled. The plist is not managed by `install.py`, so `install.sh` never installs or starts this job: it is installed by hand after review.

After reviewing a dry-run and obtaining explicit authorization to install and enable this production job, the install is:

```sh
mkdir -p ~/.local/state/mac-ops/worktree-cleaner/logs ~/Library/LaunchAgents
chmod 700 ~/.local/state/mac-ops/worktree-cleaner
cp scripts/worktree-cleaner/com.shyam.worktree-cleaner.plist ~/Library/LaunchAgents/
DOMAIN=gui/$(id -u)
LABEL=com.shyam.worktree-cleaner
launchctl enable "$DOMAIN/$LABEL"
launchctl bootstrap "$DOMAIN" ~/Library/LaunchAgents/$LABEL.plist
```

Two things to know before running it. The job executes the copy of `cleaner.py` in the main `~/Code/mac-ops` checkout, so this change must be merged to `main` first; installing from a task worktree still runs the main checkout's copy. The panel's Clean button runs that same main-checkout copy (`empryo/mods/worktrees/scan.sh` calls `$HOME/Code/mac-ops/scripts/worktree-cleaner/cleaner.py`), so the panel is on the old code until the merge lands too. And the job needs `gh` (already on the plist's PATH via `/opt/homebrew/bin`) and `emp` (found through `~/.local/bin`, which `daily.sh` puts on PATH) to be authenticated for the user account that launchd runs as; without them the scan fails closed and removes nothing.

MO-129 changed the cleaner and its proof but deliberately did not install the LaunchAgent and never ran `--apply`; installation waits for Shyam's gate.

Run the complete Empryo regression fixture with `python3 verification/worktree-cleaner/check.py`. It creates temporary repositories, a local bare remote, and stub GitHub/Empryo CLIs. It covers cross-project pagination, worktreePath and cwd-only holds, unfinished statuses, incomplete/unavailable listings, late-arriving threads, dirty and unpublished trees, dry-run/apply behavior, hub-root and nested `.empryo/tmp` scope, a completed review thread's detached worktree under the 24-hour rule, out-of-scope paths, a parent worktree held while a nested worktree lives inside it, and a total GitHub CLI failure holding every candidate. `check.py` delegates to the Empryo proof in `check_empryo.py`; there is no retired T3 fixture or database dependency.

## Limits

GitHub CLI authentication and the Empryo hub/`emp` CLI must be available to the LaunchAgent. Network or state failures block candidates; a failed `emp` listing aborts the whole scan and a failed GitHub call holds every worktree it could not verify. The 24-hour detached age uses the worktree's latest `HEAD` reflog entry; missing reflog data blocks removal. The cleaner also discovers repository owners from linked hub worktrees; owners outside `~/Code` are inventoried and held.
