# Worktree cleaner (MO-125)

The cleaner discovers repositories under `~/Code` and considers their registered linked worktrees under `~/Code/.worktrees`, `/private/tmp`, `/tmp`, `~/.empryo-hub/worktrees` (the Empryo hub root, overridable with `--hub-root`), and any worktree nested beneath a `.empryo/tmp` directory. It skips the main checkout and keeps a worktree unless every required check passes. A worktree registered anywhere else is held as `worktree_outside_scope`.

## Checks

A branch worktree must be clean, have its exact `HEAD` commit available through GitHub, and have a closed or merged pull request whose head SHA exactly matches that `HEAD`. Any open pull request for the branch blocks removal. A detached worktree must be clean, its exact commit must be available through GitHub, and its latest `HEAD` reflog entry must be at least 24 hours old.

The cleaner queries `emp call emp_thread_list` across all projects, following every cursor with a limit of 100. Two complete passes must agree on thread identity, paths, status, settled state, active run, and pending requests; any change blocks cleanup because the hub has no snapshot token. Both `worktreePath` and `cwd` (including a cwd beneath a worktree) protect a path. Every unfinished thread blocks removal: idle, snoozed, waiting, unknown-status, and completed-but-unsettled threads included. Only explicitly settled terminal threads without an active run or pending request are finished. Missing or malformed path data, hub failures, incomplete pages, duplicate threads, non-progressing cursors, and changing totals fail closed. A full listing is repeated immediately before each removal; HEAD and cleanliness are then checked again. No retired T3 database is read.

The cleaner never deletes remote branches and never uses `git worktree remove --force`. The former SRW and slash-eureka `dbt`/`omni` exclusions were removed in MO-129 with explicit promotion confirmation; every repository now follows the same checks, and a completed review thread's detached worktree is removable only through the same 24-hour detached-idle rule.

## Run a scan

The command defaults to dry-run and prints JSON counts per repository and for scanned worktrees, eligible items, holds, and hold reasons. It writes the current day's dirty or unverified list to `~/Code/coordinator/evidence/worktrees-kept-<date>.md`.

```sh
python3 scripts/worktree-cleaner/cleaner.py --dry-run
```

The daily report is replaced by each scan with the newest snapshot. The append-only `~/.local/state/mac-ops/worktree-cleaner.log` records an attempt before Git runs, then records success or failure. Each entry includes the path, branch, commit, pull request, time, and reason. State files use private permissions.

## LaunchAgent

The checked-in plist runs `scripts/worktree-cleaner/daily.sh` every 900 seconds from the main `~/Code/mac-ops` checkout. The daily script passes `--apply`; manual invocations remain dry-run unless `--apply` is supplied.

After reviewing a dry-run and obtaining explicit authorization to install and enable this production job, a future install can use:

```sh
mkdir -p ~/.local/state/mac-ops/worktree-cleaner/logs ~/Library/LaunchAgents
chmod 700 ~/.local/state/mac-ops/worktree-cleaner
cp scripts/worktree-cleaner/com.shyam.worktree-cleaner.plist ~/Library/LaunchAgents/
DOMAIN=gui/$(id -u)
LABEL=com.shyam.worktree-cleaner
launchctl bootstrap "$DOMAIN" ~/Library/LaunchAgents/$LABEL.plist
launchctl enable "$DOMAIN/$LABEL"
```

This task added the plist but did not install or run it. Run the complete Empryo regression fixture with `python3 verification/worktree-cleaner/check.py`. It creates temporary repositories, a local bare remote, and stub GitHub/Empryo CLIs. It covers cross-project pagination, worktreePath and cwd-only holds, unfinished statuses, incomplete/unavailable listings, late-arriving threads, dirty and unpublished trees, dry-run/apply behavior, hub-root and nested `.empryo/tmp` scope, a completed review thread's detached worktree under the 24-hour rule, out-of-scope paths, and a total GitHub CLI failure holding every candidate. `check.py` delegates to the Empryo proof in `check_empryo.py`; there is no retired T3 fixture or database dependency.

## Limits

GitHub CLI authentication and the Empryo hub/`emp` CLI must be available to the LaunchAgent. Network or state failures block candidates; a failed `emp` listing aborts the whole scan and a failed GitHub call holds every worktree it could not verify. The 24-hour detached age uses the worktree's latest `HEAD` reflog entry; missing reflog data blocks removal. The cleaner scans repository markers beneath `~/Code`; hub worktrees and nested `.empryo/tmp` worktrees are in scope when their owning repository lives beneath `~/Code`, and worktrees owned by repositories outside that root stay held.
