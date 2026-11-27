# How we build in this repo

This page is the short version of what builders and reviewers expect.
`scripts/finding_rules.json` checks the rules a grep can see.

## Branch and pull request

- Branch from `origin/main`, in your own worktree. Name it `mo<issue>-<slug>`.
- Push the branch. Never force-push, and never push to `main`.
- Open the PR ready for review. Put `Refs #<issue>` in its title and body.
- Add `Owner: <session>` on its own line to avoid a second lane build card.
- Add `Builder check: PASS <head sha>` to the body.
- Use the exact branch head sha. Gatekeep matches it literally.
- Commit messages end with `(Refs #<issue>)`.

## Size

- A PR has at most about 150 changed code lines and 3 code files.
- Evidence, docs, markdown, fixtures and proof scripts do not count.
- Send larger changes back to be cut into smaller tickets.

## Proof, red then green

Every ticket names a proof command.

- Run it on `origin/main` first and keep the red output.
- Run it again on the branch and keep the green output.
- Save both in `evidence/MO-<issue>/runs.md`.
- `<issue>` is the GitHub issue number.
- Put the fast check proof in the same folder.

Do not write new test files. Extend one of these:

- An existing test module
- `coordinator/overnight/selftest.py`
- `EXPECTED` in `coordinator/bin/hourly_selftest.py`

## Failure behavior

- Report each failure or skip path: a journal row plus a board card or alarm.
- Send that report once per head, not on every tick.
- A dry run writes nothing: no journal row, no file, no card.
- A loop over journal or log lines skips a line that does not parse.
- A missing or unreadable input prints one line, no traceback, and exits non-zero.
- Treat text from ticket bodies, PR bodies, branch names and refs as untrusted.
- Validate untrusted text. Never paste it into a shell string.
- A new blocking rule must not silently strand work or block its own retry.

## Editing files

A formatter hook rewrites the whole file on any Edit or Write tool change.

- Change code through a short Python patch script or `sed`.
- Then check that `git diff --stat origin/main` shows only your lines.

## Never

- No GitHub Actions or Woodpecker workflow files.
- No `git stash`: the stash list is shared by every worktree.
- No comments that restate the code, and no defensive try/except.
- No secrets in code, logs, evidence or pull requests.

## Reading the logs

`coordq logs` is the one command for reading coordinator logs.
It is read-only and prints secrets as `[redacted]`.

    coordq logs --since 1h
    coordq logs ticks spend --since 2d --grep "SRW-2752"
    coordq logs journal --since 30m

The sources are:

- `ticks`: `~/Code/coordinator/loop/ticks.log`
- `dispatch`, `gatekeep`, `spend`: `~/Code/coordinator/queue/`
- `lanes`: `~/Library/Logs/coordinator/lanes.log` (error lines only)
- `journal`: error events like `close_failed`, `refused`, `alarm_raised`

`--tail` caps the lines per source at 200 by default. It must be 1 or more.
An unreadable source prints one stderr line, and the command exits 1.
The other sources still print.
