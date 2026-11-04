# Worktree cleaner (MO-125)

The cleaner discovers repositories under `~/Code` and considers their registered linked worktrees only under `~/Code/.worktrees`, `/private/tmp`, or `/tmp`. It skips the main checkout and keeps a worktree unless every required check passes.

## Checks

A branch worktree must be clean, have its exact `HEAD` commit available through GitHub, and have a closed or merged pull request whose head SHA exactly matches that `HEAD`. Any open pull request for the branch blocks removal. A detached worktree must be clean, its exact commit must be available through GitHub, and its latest `HEAD` reflog entry must be at least 24 hours old.

The cleaner reads `~/.t3/userdata/statev2.sqlite` in read-only mode. A missing database, an unrecognized schema, malformed thread data, an unknown status, or an active T3 run for that exact worktree blocks removal. The status check includes runs, provider threads and sessions, runtime requests, subagents, and pending worktree launch records. The database is read again immediately before each removal.

The cleaner never deletes remote branches and never uses `git worktree remove --force`. It excludes SRW and the slash-eureka `dbt` and `omni` repositories based on checkout path or GitHub identity. Those exclusions are in code and need explicit promotion confirmation before they are changed.

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

This task added the plist but did not install or run it. The integration fixture is `python3 verification/worktree-cleaner/check.py`. It creates temporary repositories, a local bare remote, a stub GitHub CLI, and an isolated T3 database, then tests both dry-run and apply behavior.

## Limits

GitHub CLI authentication and the local T3 database must be available to the LaunchAgent. Network or state failures block candidates. The 24-hour detached age uses the worktree's latest `HEAD` reflog entry; missing reflog data blocks removal. The cleaner scans repository markers beneath `~/Code` and does not inspect worktrees owned by repositories outside that root.
