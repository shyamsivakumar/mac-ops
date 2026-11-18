# Worktree cleaner (MO-125)

The cleaner discovers repositories under `~/Code` and considers their registered linked worktrees only under `~/Code/.worktrees`, `/private/tmp`, or `/tmp`. It skips the main checkout and keeps a worktree unless every required check passes.

## Checks

A branch worktree must be clean, have its exact `HEAD` commit available through GitHub, and have a closed or merged pull request whose head SHA exactly matches that `HEAD`. Any open pull request for the branch blocks removal. A branch worktree without a closed pull request is removed only when every commit of the worktree is already on the remote default branch (`origin/main` or `origin/master`): no unpushed commits, `HEAD` an ancestor of the remote default branch, and `HEAD` available through GitHub. A detached worktree must be clean, its exact commit must be available through GitHub, and it is removed when it is already on the remote default branch or when its latest `HEAD` reflog entry is at least 24 hours old.

The cleaner runs `t3mcp call t3_thread_list` across all projects with the statuses preparing, queued, starting, running and waiting, following every cursor with a limit of 100. It then reads each listed thread with `t3_thread_read` and takes `thread.worktreePath`. Two complete passes must agree on thread identity and path; any change blocks cleanup because T3 has no snapshot token. Every live thread whose `worktreePath` is a worktree or sits beneath one blocks removal with the reason `t3_thread_unfinished`. Threads in other statuses (idle, completed, failed, interrupted) do not block. T3 failures, malformed or missing path data, incomplete pages, duplicate threads, non-progressing cursors, and changing totals fail closed. A full listing is repeated immediately before each removal; HEAD and cleanliness are then checked again.

The cleaner never deletes remote branches. It removes a worktree with `git worktree remove` and prunes stale registrations afterwards. It uses `--force` only for a worktree whose every change is an agent bootstrap file, so the bootstrap files are discarded; a worktree with any other change is never forced, and a worktree with uncommitted work stays in "needs a look". It excludes SRW, the Ascend repositories (`ascend`, `ascend-mcp`, `slash-eureka`) and the slash-eureka `dbt` and `omni` repositories based on checkout path or GitHub identity. Those exclusions are in code and need explicit promotion confirmation before they are changed.

## Agent bootstrap files

The files an agent bootstrap leaves in a worktree are not the user's work, so they do not make a worktree dirty: `.specstory/`, `.agents/legacy-instructions.md`, and an `AGENTS.md` that gained exactly the standing agent rules block. The `AGENTS.md` rule holds only when the file added lines and removed none, and the added lines match a known rules file line for line, in order (`coordinator/config/AGENT-RULES.md`, `runtime/pi/AGENTS.md`, `runtime/omp/AGENTS.md`, or the installed agent rules). A part of the block, or one rule added by hand, is real work: the cleaner cannot recognise the bootstrap exactly, so it keeps the worktree. A rename is a bootstrap change only when both the source and the destination are bootstrap files; a rename of a real file into `.specstory/` is real work. Any other change to `AGENTS.md` is real work.

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

This task added the plist but did not install or run it. Run the complete T3 regression fixture with `python3 verification/worktree-cleaner/check.py`. It creates temporary repositories, a local bare remote, and stub GitHub and `t3mcp` CLIs. It covers pagination, worktreePath holds, live and non-live statuses, incomplete/unavailable listings, late-arriving threads, dirty and unpublished trees, and dry-run/apply behavior. `check.py` delegates to the proof in `check_t3.py`.

Run `python3 verification/worktree-cleaner/check_bootstrap.py` for the bootstrap-aware behaviour: a worktree that holds the exact bootstrap block is removed, a worktree with one rule added by hand or a real file renamed into `.specstory/` is kept, a worktree that also holds real work is kept, a branch whose commits are already on the remote default branch is removed without a pull request, an unpublished branch is kept, and an Ascend repository is never touched.

## Limits

GitHub CLI authentication and `t3mcp` (with a signed-in T3 session) must be available to the LaunchAgent. Network or state failures block candidates. The 24-hour detached age uses the worktree's latest `HEAD` reflog entry; missing reflog data blocks removal. The cleaner scans repository markers beneath `~/Code` and does not inspect worktrees owned by repositories outside that root.
