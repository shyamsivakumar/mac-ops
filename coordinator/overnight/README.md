# `.overnight/` — the overnight shift's on-disk contract

The Coordinator does checked work overnight and leaves one morning report.
This folder holds the shift contract, the receipts and the report.

The overnight list is **not** here. The list is the board: GitHub issues
with stage labels, the same backlog the Herdr coordinator panel shows. The
shift reads GitHub, coordq and T3 for state and order, so there is no second
queue and no punch-list file (spec revision 2).

The mac-ops installer (`install_coordinator.py`) creates this folder and its
four subfolders, installs this README, installs the `overnight` command in
`~/.local/bin`, and keeps the folder out of Git in whatever repository
contains the coordinator folder.

## The command

`overnight` is the shift's command line. It lives in `coordinator/overnight/`
in the mac-ops checkout and is installed by the same installer.

| Command | What it does |
| --- | --- |
| `overnight intake --dry-run` | Reads the board (`ticket list --fresh --json`) and the open pull requests (`gh pr list` for each allowed repository) into intake records, and prints the record count per repository. Read only: it writes nothing and keeps no list of its own. |

Intake is the first part of the spec's rollout plan (T3). The later parts
(filtering, ordering, arming, the tick and the morning report) build on the
same records, in the same module.

## Folders

| Folder | What it holds |
| --- | --- |
| `run/` | The shift contract: when the shift is armed, when it must stop, and what it is allowed to do. |
| `receipts/` | One receipt per item, plus the morning report. Receipts are the only proof a tick writes. |
| `inbox/` | What the shift could not decide or could not fix: the parking lot and the snag log. |
| `staging/` | Scratch for work in flight (worktree path, branch, builder notes). It is scratch, not a queue: an empty shift leaves it empty. |

## Files

The names come from the overnight runner spec, section 6 (revision 2).

| File | Who writes | What it holds |
| --- | --- | --- |
| `run/armed` | Arm step | Shift id and start time. Its presence means "on shift". |
| `run/deadline` | Arm step | UNIX epoch for quitting time (default 06:00 PT). |
| `run/policy.json` | Arm step | Snapshot: allow list, slot cap (read only), budget %, stall cap, verify level. |
| `run/STOP` | Shyam (or `overnight.sh stop`) | Stop wins. The shift ends at the next tick. |
| `receipts/<item>.md` | Tick | State, PR link, checks run and result, Opus gate verdict, files changed, time used, why it stopped. |
| `inbox/parking-lot.md` | Tick | Decisions the shift could not make. Each with a default and a recommendation. |
| `inbox/snag-log.md` | Tick | Problems found (flaky test, conflict, dialog) and what the shift did. |
| `run/shift-log.md` | All steps | One line per event, with PT time. |
| `receipts/morning-YYYY-MM-DD.md` | Report step | The morning report: what merged, what is ready, what is stuck and why, and which decisions wait for Shyam. |

There is no `punch-list.md` (spec revision 2): the board is the list, and the
receipts sit beside it.

## Rules this folder keeps

- A receipt is written only after a state change, and an item counts as done
  only when its receipt holds the verify command, its exit code and an Opus
  gate PASS. A model claim alone never counts.
- No secrets. Receipts, logs and the morning report never hold a token, key,
  cookie or `.env` value.
- The folder is scratch for one shift. Nothing here changes merge, push, the
  slot cap or the Ascend rules.

## Source

This copy is installed by mac-ops. The source of truth is
`coordinator/overnight/README.md` in the mac-ops checkout; edit that, then
reinstall:

```sh
python3 install_coordinator.py
```
