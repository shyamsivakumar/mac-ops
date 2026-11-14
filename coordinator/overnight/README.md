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
| `overnight order --dry-run` | Orders the whole board and prints the full ordered list: the failing pull requests, then the pull requests with a gate PASS, then the ready tickets that are already 5-minute parts, then the ready tickets that are not split yet. It writes one summary line to `run/shift-log.md` and no list file. |
| `overnight check-pr --repo <repo> --number <n>` | The second check: refuses any Ascend pull request before work starts on it. Read only. It fails closed: a pull request it cannot read is refused, not passed. |
| `overnight report --dry-run` | Renders the morning report from the shift's own records: the receipts, the parking lot, the shift log and the policy snapshot. It reads no board and keeps no list of its own. Without `--dry-run` it writes `receipts/morning-YYYY-MM-DD.md` and prints where it wrote it. |
| `overnight shift --dry-run` | The command the launchd job fires. It decides which part of the night it is from the Mac's local clock: the start (22:00–23:59) reads the board and writes nothing, the report (06:00–07:29) writes the morning report, and any other time does nothing. `--at start` or `--at report` forces a part, for a manual run. |

Intake is the first part of the spec's rollout plan (T3). The later parts
(filtering, ordering, arming, the tick and the morning report) build on the
same records, in the same module.

## The order

The order is the spec's, and it is the whole board: no cap and no list
file.

| Group | What is in it |
| --- | --- |
| Failing pull requests | A pull request that is open and whose checks show a failure. `gh pr checks` answers for each one; a pull request with no checks at all is not a failure. |
| Pull requests with a gate PASS | A pull request whose head the gate has looked at, where the gate's own message ends with `VERDICT: PASS`. The gate thread is found in the coordinator's dispatch receipts (`gate:<repo>#<pr>:<head>`), so a gate for an older head is never a verdict for the current one. |
| Ready tickets already split into 5-minute parts | A ready ticket whose own text says it is a bounded slice: a light build slice, a light chore, or a part that says how many minutes it takes. |
| Ready tickets not yet split | Every other ready ticket. The shift splits it first, then adds the parts. |

A ticket is ready when the board's stage is `todo`. A ticket in another
stage is not ready and is not work, so the list says so instead of
dropping it. A pull request that is open and neither failing nor gate
PASS is in flight: it is not work for the night, and the list says that
too.

Inside a group the order is the board's: the priority label first, then
the items whose blockers are met, then the board's own order. A blocker
is met when its issue is closed, so it is not on the open issue list. A
blocker the shift cannot check is treated as unmet, so the shift does
not start work whose order it cannot prove.

The order writes one line to `run/shift-log.md`: the planned count and
the counts per repository and per state. That line is the night's record
of what was in scope, and the morning report reads it for the planned
count. It holds no list: the board is the list.

`--dry-run` means no work, and the two commands read it differently on
purpose. `overnight report --dry-run` prints the report and writes no
file. `overnight shift --dry-run` writes the morning report, because the
report is the record of the night, not work.

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


## The launchd job

`coordinator/launchd/dev.coordinator.overnight.plist` in the mac-ops
checkout is the job `dev.coordinator.overnight`. The mac-ops installer
copies it into `~/Library/LaunchAgents` with the rest of the coordinator
jobs, so the job and the command always come from the same checkout.

The job fires twice a night, and the clock picks the part. The clock is the
Mac's local clock, the clock launchd itself uses, so a run that fires
always matches the part it is for:

| Local time | What runs |
| --- | --- |
| 22:30 | The shift start. In dry-run mode it reads the board and writes nothing. |
| 06:30 | The morning report. It writes `receipts/morning-YYYY-MM-DD.md` and nothing else. |

The windows are an hour wide rather than a minute, so a Mac that wakes
late still writes the report (until 07:29). A run outside both windows
does nothing and exits 0.

The Mac must run on Pacific time for these to be the spec's 22:30 and
06:30 PT. If the Mac's clock is not on Pacific time, the job still runs
the right part, because the dispatch reads the same clock launchd fires
on, and it says so in the log.

The job runs in dry-run mode (`shift --dry-run`) until the arm and tick
parts (T4, T5) land. A dry night does no work, so the morning report is the
only file it writes. A real shift is not started by the job yet: without
`--dry-run` the start refuses and says so, rather than pretending to work.

The job has no `RunAtLoad`, so a night does not start at every boot. It
takes no lock: launchd never starts a second copy of a running job, and
the two runs are eight hours apart.

Load it after the install:

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.coordinator.overnight.plist
launchctl print gui/$(id -u)/dev.coordinator.overnight
```

Its log is `~/Library/Logs/coordinator/overnight.log`.

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
| `receipts/<item>.md` | The state of one item, its check, its gate verdict, its merge time, its builder time and why it stopped. The merge time is the one the shift wrote after it checked GitHub, so the report does not call GitHub again. |
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
- An item counts as done only when its receipt holds a check that ran and
  passed, and a gate that passed. A check that failed leaves the item
  stuck, whatever the gate says.
- `done` counts the items that merged, and `ready` counts the items that
  hold a passing gate but wait for a merge right the shift does not have.
  The counts and the lists agree item for item.
- The report says how the shift ended in one of the four ways the spec
  allows: `deadline`, `all done`, `STOP` or `stall`. When the records
  explain none of them, it says `UNVERIFIED`.
- A count that cannot be checked is written as `UNVERIFIED`: the planned
  count without a shift-log summary, the model use when the allowance was
  not readable, the builder time when a receipt records no time or a
  planned item has no receipt, and the identity of planned items that
  have no receipt.
- The full suite counts as run only when the shift log records its command
  and its exit code.
- The report never says a check passed if it did not run.
- The report exits non-zero when the folder that holds the records does
  not exist, so a wrong folder is not a calm empty report.

## Source

This copy is installed by mac-ops. The source of truth is
`coordinator/overnight/README.md` in the mac-ops checkout; edit that, then
reinstall:

```sh
python3 install_coordinator.py
```
