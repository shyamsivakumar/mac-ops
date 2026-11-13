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
| `overnight filter --dry-run` | Filters the board and prints every drop with its reason. Read only. It fails closed: it exits non-zero and drops what it could not check. |
| `overnight check-pr --repo <repo> --number <n>` | The second check: refuses any Ascend pull request before work starts on it. Read only. It fails closed: a pull request it cannot read is refused, not passed. |

Intake is the first part of the spec's rollout plan (T3). The later parts
(filtering, ordering, arming, the tick and the morning report) build on the
same records, in the same module.

## What the filter drops

The filter reads the board, the tickets' own text and the coordinator's
decisions log. It keeps no list of its own and writes nothing.

| Drop | How it is found |
| --- | --- |
| Ascend work | A key from the spec's list (AUH, MCP, OPS, DBT, OMN), or a repository the merge gate refuses: the same repository rule and the same per-repository `ascend` flag the gate uses in `coordinator/bin/coordq`, so the shift and the gate agree on what Ascend is. |
| A repository off the allow list | The allow list is the board config (`coordinator/config/tickets.json`), the same list intake uses. |
| A ticket marked `hold` | The word `HOLD` in capitals at the start of a line of the ticket's own text. |
| A ticket marked `needs Shyam` | The phrase `needs Shyam` with its question (`Needs Shyam: ...`, "needs Shyam to ..."), and not "needs Shyam's OK". |
| A ticket marked `design needed` | The phrase `design needed` with what it waits for (`design needed: ...`, "design needed before ..."). |
| An open question in the decisions log | The last line of `loop/decisions.md` that is about the ticket holds or parks it, opens it, asks it as `Q: ...`, or asks Shyam a question that was never answered. |

A mark is the marked form and it stands at the start of a line or of a
clause, so a ticket that only talks about holding a position, or about a
decision that needs Shyam later, is not marked. The decisions log is
append-only history, so the last line that is about a ticket decides: a
hold outlives the question it was asked in, and a line that answers the
question closes it.

The filter prints every drop with its reason, and it fails closed. A
ticket whose text could not be read, a ticket whose open question could
not be checked, a stale board and a missing decisions log all end in a
non-zero exit: the filter never returns a list it could not fully check.
The second check, `check-pr`, refuses an Ascend pull request by
repository, by the board config's `ascend` flag, or by any Ascend key its
branch or its body carries.

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

## Source

This copy is installed by mac-ops. The source of truth is
`coordinator/overnight/README.md` in the mac-ops checkout; edit that, then
reinstall:

```sh
python3 install_coordinator.py
```
