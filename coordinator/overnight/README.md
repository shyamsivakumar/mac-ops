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
| `overnight intake --dry-run` | Reads the board (`ticket list --fresh --json`) and the open pull requests (`gh pr list` for each allowed repository) into intake records, and prints the record count per repository. Read only: it writes no record and keeps no list of its own. The ticket CLI refreshes its own cache when it reads the board; that cache is the ticket CLI's. |
| `overnight report --dry-run` | Renders the morning report from the shift's own records: the receipts, the parking lot, the shift log and the policy snapshot. It reads no board and keeps no list of its own. Without `--dry-run` it writes `receipts/morning-YYYY-MM-DD.md` and prints where it wrote it. |

Intake is the first part of the spec's rollout plan (T3). The later parts
(filtering, ordering, arming, the tick and the morning report) build on the
same records, in the same module.

## How a pull request joins a ticket

One work item is one record, so a pull request that belongs to a ticket is
part of that ticket's record and not a record of its own. Two signals say
which ticket a pull request belongs to:

1. A keyword reference in the title or the body (`Refs #176`) names a
   GitHub issue number. It decides when the board shows that issue.
2. A branch name that carries a ticket key (`t3/aa-10-fix`) names a board
   ticket by key. The key number and the issue number are different
   counters, so a branch is never read as an issue number.

When the keyword names an issue the board does not show, the branch is still
read. A pull request whose body points at a ticket that has left the board,
and whose branch carries the key of a ticket that is on it, is that ticket's
work. A pull request that names neither is a record of its own.

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

## What the morning report reads

The report is rendered from the records in this folder and from nothing
else. It never invents a count and it never upgrades a claim into proof.

| Record | What the report takes from it |
| --- | --- |
| `receipts/<item>.md` | The state of one item, its check, its gate verdict, its merge time, its builder time and why it stopped. |
| `inbox/parking-lot.md` | The decisions the shift could not make, each with a default and a recommendation. |
| `run/shift-log.md` | How many items were in scope (`planned N items`), whether the full suite ran and with which exit code, and whether the shift stalled. |
| `run/policy.json` | The verify level and `allowance_used_percent`, the share of the plan allowance the night used. |
| `run/armed`, `run/deadline` | The window of the night, in PT. |
| `run/STOP` | Its presence means the shift was stopped. |

### The receipt fields

A receipt is markdown with one `- Key: value` line per field.

| Field | What it holds |
| --- | --- |
| `Item` | One line naming the work. |
| `Repo`, `Ticket` | Where the work is (`MO-222 (#190)`). |
| `State` | `done`, `ready`, `stuck` or `parked`. |
| `PR` | The pull request, when there is one. |
| `Merged` | The PT time the merge landed on GitHub. |
| `Checks` | One check, or several separated by semicolons. Each check is a command in backticks and its exit code: `` `cmd` exit 0 ``. |
| `Gate` | `PASS` or `FAIL`. |
| `Files` | How many files the item touched. |
| `Time used` | The builder time, as `N min`. |
| `Stopped because` | Why the item stopped. |
| `Next` | The next step. |

### The rules the report holds

- A check counts as run only when the receipt names the command and its
  exit code. A check that is claimed with neither never appears as passed:
  the item is stuck, and the check is listed under "Not run, and why".
- An item counts as done only when its receipt holds a check that ran and a
  gate that passed.
- A count that cannot be checked is written as `UNVERIFIED`: the planned
  count without a shift-log summary, the model use when the allowance was
  not readable, the builder time when a receipt records no time, and the
  identity of planned items that have no receipt.
- The report never says a check passed if it did not run.

## Source

This copy is installed by mac-ops. The source of truth is
`coordinator/overnight/README.md` in the mac-ops checkout; edit that, then
reinstall:

```sh
python3 install_coordinator.py
```
