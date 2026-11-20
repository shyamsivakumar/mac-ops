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
| `overnight shift` | The command the launchd job fires. Every run is one cycle: it reads the policy snapshot, reads the whole board under the snapshot's allow list, works it (there is no item cap and no allowance stop) and writes a receipt for every item whose state changed. The shift runs 24x7, so there is no night window and no part of the night, and the shift is never armed. The first cycle of the morning writes the day's morning report, so Shyam reads one report in the morning; `--report` writes it on demand, and `--dry-run` does no work on the board. |
| `overnight policy` | Writes the policy snapshot the shift reads on every cycle: `run/policy.json`. The allow list, the queue's slot cap (read only, never raised), the stall cap, the retry cap and the verify level. There is no item cap and no allowance stop. It writes no `run/armed` and no `run/deadline`, and it can run again at any time. |
| `overnight receipt` | Writes the receipt of every item whose state the shift can see (spec part T5b): the state, the pull request, the checks and their exit codes, the gate's verdict, the files it touches, the builder's own time and why the item stopped. It reads GitHub, the queue and the threads, so a receipt never carries a model claim. `--repo` and `--number` write the receipt of one item, `--items N` writes the receipts of the first N items of the shift's order, and `--fixture` writes the receipt of a fixture item (the budget proof). `--dry-run` prints the receipt and writes no file. |
| `overnight budget` | Shows what the per-item budget does with one item (spec part T8a): within the budget, over the soft budget, stopped at the hard budget, or parked for want of fix tries. It reads one item (`--repo` and `--number`) or a fixture (`--fixture`), and it writes nothing: the cycle writes the receipt, and this command shows the stop before the night does it. |
| `overnight close --repo <repo> --number <n>` | Closes a ticket's issue, and only when the receipt holds the evidence (spec part T6): a check command, its exit code and a gate PASS on the pull request. A receipt with a claim but no exit code leaves the issue open, and the command says which record is missing. `--dry-run` says what the close would run and closes nothing. |
| `overnight check-head --repo <repo> --number <n>` | Checks a pull request's head against the checks that ran on it, and exits 0 only when such a check ran and passed. It is the command a receipt records. Exit 1 means a check ran and did not pass; exit 2 means no check ran on the head (or the head could not be read), which is a refusal. The builder's own line in the pull request body is a claim about the check, so it never counts. |
| `overnight attend` | The attended first night (spec part T13). The command a person runs when they sit down to watch. The shift arms itself, reads the board, takes the small items the board shows and observes each one for real: its pull request, its checks, the gate's verdict and the files it touches. It writes one receipt per item, the shift log and the morning report. It runs no merge, no push and no builder. |
| `overnight redact` | Prints a text with every secret pattern redacted (spec part T7a). It is the redaction the shift writes with, made visible: the fake key goes in and does not come out. It writes nothing. |
| `overnight park` | Writes the shift's two inbox files (spec part T10): `inbox/parking-lot.md` holds the decisions the shift could not make, each with a default and a recommendation, and `inbox/snag-log.md` holds the problems it found and what it did about them. It reads the board, the queue's own records and the threads that hold the work, so it keeps no second queue. A pending approval request is parked with its exact text and is never answered: the module has no call that answers a request. `--dry-run` prints both files and writes none, and `--fixture` parks the pending request of one fixture thread. |

Intake is the first part of the spec's rollout plan (T3). The later parts
(filtering, ordering, the policy snapshot and the work parts) build on the
same records, in the same module.

The pi tick is retired. `dev.coordinator.tick` (the headless pi run that
followed `loop/tick.md` every 30 minutes) no longer runs, and `loop/tick.md`
is no longer the runbook for board work: this file and the shift's own
records are. The mechanical jobs stay as they are: `dev.coordinator.dispatch`
starts queued items and refills slots every 30 s, `dev.coordinator.gatekeep`
queues a gate for every open pull request head every 60 s, and
`dev.coordinator.turncap` caps turns.

## The board's calls are bounded

Every call the module makes to the outside world (`gh`, the ticket CLI,
`t3mcp`) runs in a process group of its own and gets a timeout. A call that
hangs has its whole group killed, so the wait ends when the timeout ends and
not later, and no member of the group outlives the call.

A call the caller can do without is skipped: the skip names the command that
was skipped, it is written to `~/Library/Logs/coordinator/skips.log` where
the next reader finds it even when the reader was a model, and the read
carries on. The board read (`overnight board --json`) reads its
repositories at the same time, so one stalled repository costs one timeout
and not one per repository, and it has a budget of its own (240 seconds) so
a slow GitHub cannot use the whole tick. A repository whose ticket text
could not be read is not on the board: its tickets are never classified and
never acted on, and it is named in the output and in the board's payload.

## The policy snapshot

The shift runs 24x7 and is never unarmed (spec revision 3). There is no
`run/armed` and no `run/deadline`, and the shift always runs. What is left
of the arm step is the policy snapshot, and it is the whole contract:

```sh
overnight policy
```

| Field | What it holds |
| --- | --- |
| `allow` | The repositories the shift may touch, from the board config (`coordinator/config/tickets.json`). The cycle reads and orders only these repositories. |
| `slot_cap` | The queue's own slot cap, read from the coordq config (`$COORDQ_DIR/config.json`). It is read only and never raised. |
| `stall_cap` | Cycles with no new work before the shift ends as a stall. |
| `retry_cap` | Fix tries per item before the item is parked. |
| `soft_budget_minutes` | The soft builder-time budget per item. The builder is asked to wrap up when it is over it. |
| `hard_budget_minutes` | The hard builder-time budget per item. The item is stopped and written up when it is over it. It can never be above the ten-minute turn cap. |
| `verify_level` | How much each item is checked. It is `balanced` for v1. |
| `written_at` | When the snapshot was written, in Pacific time. |

There is no item cap and no allowance stop: the whole backlog is in scope
and model use is never a stop condition. A reader that looks for a cap on
the items or on the model finds none, and that is the rule.

The shift reads the snapshot on every cycle. A cycle that would work the
board and finds no snapshot refuses and says so: a cycle with no contract
does no work. A snapshot that is missing one of the five contract fields,
or that holds the wrong kind of value, is not a contract, and the cycle
refuses it too. The command refuses to write a snapshot at all when the
queue's slot cap cannot be read: a contract without the cap is not a
contract. A dry run reads the board without one and says that it did.

The Ascend rule still wins over the snapshot. The cycle reads the
repositories the snapshot names, minus the ones the merge gate would
refuse, so a hand-edited snapshot cannot make the shift read Ascend
work.

`run/STOP` still stops the shift at the next cycle, and it wins over every
other rule. The morning report still runs: it is the record of the night,
and it says that the night ended with STOP.

Writing the snapshot again replaces it with the same contract, so the
command can run on every boot. The write is atomic, so a cycle that reads
while the snapshot is being written reads the old one or the new one. The
command never writes the queue's config, and it never touches the merge,
push, slot cap or Ascend rules.

## The order

The order is the spec's, and it is the whole board: no cap and no list
file.

| Group | What is in it |
| --- | --- |
| Failing pull requests | A pull request that is open and whose checks show a failure. `gh pr checks` answers for each one; a pull request with no checks at all is not a failure. |
| Pull requests with a gate PASS | A pull request whose head the gate has looked at, where the gate's own last message in the thread's latest run ends with `VERDICT: PASS` and carries the line `CHECK: PASS <head>`. The gate thread is found in the coordinator's dispatch receipts (`gate:<repo>#<pr>:<head>`), so a gate for an older head is never a verdict for the current one, and a later run of the same thread replaces an earlier verdict. |
| Ready tickets already split into 5-minute parts | A ready ticket whose own text says it is a bounded slice: a light build slice, a light chore, or a part that says how many minutes it takes. |
| Ready tickets not yet split | Every other ready ticket. The shift splits it first, then adds the parts. |

A ticket is ready when the board's stage is `todo`. A ticket in another
stage is not ready and is not work, so the list says so instead of
dropping it. A pull request that is open and neither failing nor gate
PASS is in flight: it is not work for the night, and the list says that
too.

Inside a group the order is the board's: the priority label first, then
the items whose blockers are met, then the repository and the issue
number. A blocker is met when its issue is closed, so it is neither on
the open issue list nor missing from the closed one. A blocker the shift
cannot check is not a met blocker, so it is reported as blocked.

A blocked item is not left out. It stays in its group, is marked with the
blocker that holds it, and is ordered after the items that are ready, so
the night sees it and knows why it waits.

The order writes one line to `run/shift-log.md`: the planned count and
the counts per repository and per state (failing, gate PASS, split,
unsplit, in flight and not ready). A count the shift could not check is
written as `UNVERIFIED`, never as a zero. That line is the night's record
of what was in scope, and the morning report reads it for the planned
count. It holds no list: the board is the list.

`--dry-run` means no work, and the two commands read it differently on
purpose. `overnight report --dry-run` prints the report and writes no
file. `overnight shift --dry-run` does no work on the board and writes
only the cycle's line in the shift log, because that line is the cycle's
record, not work.

## The receipt per item

A receipt is the only proof the shift has, so it is written on every state
change of an item and is rewritten when the item's state or its evidence
changes. A receipt that says the same thing is left alone, so the folder
holds the record of the state changes and not a copy of the same state
every cycle.

```sh
overnight receipt --repo shyamsivakumar/mac-ops --number 181
overnight receipt --items 3
```

A cycle writes the receipts: a real `overnight shift` cycle reads the
board under the policy snapshot, writes the receipt of every item it sees
and writes one line per receipt to the shift log. It still starts no
builder and works no board item, so a cycle that cannot start work still
leaves the record of what it saw. A dry run writes no receipt.

Every field is read, never claimed:

| Field | Where it comes from |
| --- | --- |
| `State` | What the pull request and the gate really show: `done` when GitHub says the pull request merged, `ready` when the gate passed and the shift has no merge right, `stuck` for everything else. |
| `PR` | The pull request the board links to the item. |
| `Checks` | `overnight check-head --repo <repo> --number <n>` and its exit code. A check counts as run only when the receipt names the command and its exit code. |
| `Failing checks` | The checks that failed, as GitHub names them. |
| `Gate` | The gate's own last line (`VERDICT: PASS` or `VERDICT: FAIL`) read from the gate thread of that head, or from the pull request's own review when there is no gate thread. `UNKNOWN` when neither can be read. |
| `Files` | How many files the pull request touches. |
| `Builder thread` | The thread the coordinator built the pull request in. |
| `Time used` | The builder's own time: the sum of the minutes its thread's own runs took. The idle time between two runs is not builder time. A night that ran no builder says `0 min`. |
| `Observed` | How long the shift spent looking at the item, in seconds. |
| `Stopped because` | Why the item stopped, derived from the evidence above. |
| `Next` | The next step, derived from the evidence above. |

The receipt never carries a model claim where a proof belongs: the gate
verdict comes from the gate, the checks come from the command that ran
them and the builder time comes from the thread's own times. The cycle
writes the receipt, so no agent writes one by hand.

## The evidence rule for a done item

An item counts as done, and the coordinator closes its issue, only when the
receipt records a command, its exit code and a gate PASS on the pull
request. A model claim alone never counts.

The rule lives in one place in the module (`evidence_holds`), and three
things read it:

| Reader | What it does with the rule |
| --- | --- |
| The receipt writer | A pull request that merged is `done` only when the receipt holds the evidence. When it does not, the receipt says `stuck` and says which record is missing: "a check has no exit code, so it did not run" or "the gate did not pass". A receipt never claims a done item it cannot show. |
| The morning report | The report keeps the rule it already held: a check that did not run leaves the item stuck, whatever the receipt's own state says. |
| `overnight close` | The close step. It reads the receipt of the ticket and closes the issue only when the receipt holds the evidence. |

```sh
overnight close --repo shyamsivakumar/mac-ops --number 182
overnight close --repo shyamsivakumar/mac-ops --number 182 --dry-run
```

The close step finds the receipt by the fields it holds (the repository and
the issue number in its `Ticket` line), so the folder of receipts stays the
only record of what the shift did. The `Ticket` line names the ticket's
issue, never its pull request: the board numbers issues and GitHub numbers
pull requests in different counters, so the receipt holds both, the issue
in `Ticket` and the pull request in `PR`. The close addresses the issue
only, and it takes the number from the receipt it found, so a close can
never land on another ticket's issue. There is no switch that names a
receipt file, so a receipt for one ticket can never close another issue.

It refuses with a non-zero exit when there is no receipt for that issue,
when the receipt holds no check, a check with no exit code, a check that
failed, a gate that did not pass, or a state that is not `done`. The issue
then stays open, and the refusal names the record that is missing.

The close step writes nothing but the close itself. It does not merge, does
not push and does not touch the slot cap or the Ascend rules. It has no
caller yet: the gate's own brief still closes a ticket after its merge
(`coordinator/bin/coordq`), and that path is unchanged by this part.

## The check a receipt records

A check counts as run only when the receipt names the command and its exit
code, so the receipt writer records the command it really ran:
`overnight check-head --repo <repo> --number <n>`.

That command reads the checks that ran on the pull request's head and
answers with its exit code:

| Exit | What it means |
| --- | --- |
| 0 | A check ran on the head and passed. |
| 1 | A check ran on the head and did not pass. |
| 2 | No check ran on the head, or the head could not be read. A refusal, never a pass. |

Only a published check counts. The builder's own line in the pull request
body, `Builder check: PASS <head>`, is a claim about the check and not the
check, so it never makes a head pass. A repository that publishes no checks
(CI is agent checks only, as in mac-ops) therefore has no evidence on its
heads: its items stay open, and the receipt says why.

## The per-item budget

Every item has a soft and a hard budget of builder time, and at most two
fix tries after a failed check (spec section 10). The time limits stay
inside the ten-minute turn cap the coordinator's own turncap job
enforces, so the budget is smaller than the turn: the shift can stop an
item and write it up before the turn itself ends.

| Number | Where it comes from | What it does |
| --- | --- | --- |
| `soft_budget_minutes` (5) | The policy snapshot, or the turn cap's number when the snapshot names none. | Over it, the builder is asked to wrap up. The item keeps its state and the receipt says so. |
| `hard_budget_minutes` (8) | The policy snapshot, or the turn cap's number when the snapshot names none. | Over it, the item is stopped and written up: its receipt says `parked` and why. |
| `retry_cap` (2) | The policy snapshot. | Out of fix tries, the item is parked and the shift sends no further fix. |

A snapshot that names a budget above the ten-minute turn cap is refused:
the budget can never outlive the turn it lives in. A snapshot that names
no budget at all keeps working, because the shift falls back to the turn
cap's budget; the 24x7 shift must not stop at the next install.

The builder time is the sum of the minutes the builder thread's own runs
took. The idle time between two runs is not builder time, so a builder
that waited a day for its findings did not spend a day building. The
number is read from the thread, never claimed by a model.

The budget stops work, so it says nothing about work that is finished: a
merged item and an item that waits for Shyam's merge keep their state,
and the time they took stays in the receipt.

The fix tries come from the queue's own record: the queue writes one
entry per fix it sent, under the head it sent it for, so one entry is one
fix try. The shift keeps no count of its own.

The rule lives in one place in the module (`budget_verdict`), and the
receipt writer, the board and the budget command all read it.

```sh
overnight budget --fixture evidence/MO-217/fixture-over-hard-budget.json --dry-run
overnight budget --repo shyamsivakumar/mac-ops --number 217 --dry-run
```

The fixture is a JSON file that describes one item:

```json
{
  "key": "MO-999",
  "item": "MO-999 a fixture item over its hard budget",
  "repo": "shyamsivakumar/mac-ops",
  "number": 217,
  "builder_minutes": 9,
  "fix_tries": 0,
  "soft_budget_minutes": 5,
  "hard_budget_minutes": 8,
  "retry_cap": 2
}
```

`overnight receipt --fixture <file>` writes the receipt of that fixture
item through the real writer, so the budget can be shown on the real path:
an item over its hard budget is written up as `parked`, and the morning
report reads it like any other receipt.

## The stall rule (spec part T8b)

A tick that shows no new commit and no new receipt for three ticks means
the item is not moving. The shift reports the stall: a receipt for the
item and a line in the shift log. When the whole board shows no progress
for three ticks, the shift logs the stall, sweeps the board again and
alerts Shyam. The shift keeps running until every item is done or parked:
a stall is not the end of the shift, and a stalled item is not parked. The
shift keeps working it (the no-parking policy from Refs #376).

The rule lives in one place (`coordinator/overnight/stall.py`): `observe`
decides one item, `board` decides the board, and both are pure. The shift
writes the records.

| Thing | What it is |
| --- | --- |
| The marker of an item | The item's commit and the item's newest dispatch receipt, as one string. A new commit or a new receipt is progress, and nothing else is. |
| The idle count | How many ticks in a row the item's marker did not change. The first tick of an item counts as idle: there is nothing yet to compare it with. |
| The stall cap | Three idle ticks (`STALL_CAP`). The policy snapshot's `stall_cap` names the same number. |
| The stall state | `run/stall-state.json`, in the shift's own folder. It holds the marker, the idle count and the parked flag of every item the shift measured. |

An item is measured when the shift has something to measure: a commit or a
receipt. An item the shift never started has neither, so it is not a
stalled item, it is an item the shift still has to start. A draft pull
request is not work the shift does, so it is not measured either.

The board the shift holds is cached for a few passes, and a stale head is
not evidence that an item stopped moving. So a tick that could park an
item or stall the board reads the board again first, and the fresh head
decides.

The board moved when an item moved or when new work arrived on it. New
work counts whether the shift has measured the new item or not: a ticket
that appeared on the board is work, and a board that keeps receiving work
is not stuck. The board's first tick is its baseline: there is nothing yet
to compare it with, so it counts as an idle tick, the way the first tick
of an item does.

A stalled item is reported, not parked: the lane keeps working it, the
shift does not label it, does not re-cut it and does not stop its
builder. The shift writes the receipt of a stalled item (`State: stuck`,
`Stopped because: stall: ...`), so the morning report names it under
"Stuck" and Shyam sees it.

A board that stopped moving gets one alert, not one per tick: the alert
is written again after the board moves and stalls a second time. The flag
that says "the board was alerted" is set only after the alert was written,
so a board whose alert could not be written asks again on the next tick
instead of going quiet for good. The alert goes to the mac-ops owner board
(`factory-overnight-stall`), the same board the merge alert uses. The
watchdog stays on the decisions board. The board is swept again in the same tick, so the shift
keeps working on a fresh board.

The tracking is bounded: an item's idle count stops at the cap, and an
item that leaves the board is not tracked any more.

```sh
overnight stall --fixture evidence/MO-218/stall-fixture.json --root <folder>
overnight stall --root <folder>
```

The first command runs the real rule over the ticks of the fixture and
writes the records it produces: the receipt of the reported item, the lines
in the shift log and the alert. The second command reads the shift's own
stall state and says which items are idle and for how many ticks, and
which of them are `stalled` (never `parked`: the shift keeps working a
stalled item). It writes nothing.

The fixture is a JSON file that names its items and its ticks. A tick maps
every item to its marker.

```json
{
  "items": [
    {
      "key": "MO-218",
      "repo": "shyamsivakumar/mac-ops",
      "number": 218,
      "title": "Overnight T8b: Stall detection"
    }
  ],
  "ticks": [
    { "shyamsivakumar/mac-ops#218": "aaaa111|1" },
    { "shyamsivakumar/mac-ops#218": "aaaa111|1" },
    { "shyamsivakumar/mac-ops#218": "aaaa111|1" }
  ]
}
```

## The secret redaction

Every record the shift writes under `.overnight/` goes through one
redaction function, so no receipt, no shift log line and no morning
report holds a token, a key, a cookie or a `.env` value. The pattern
list lives in that one place (`SECRET_PATTERNS` in the module) and the
function (`redact`) is the only thing that applies it. Every write in the
module goes through `write_record` or `append_record`, which call it, so
no writer has to remember the rule.

The console is a writer too. Launchd writes everything the module prints
to the job's own log (`~/Library/Logs/coordinator/lanes.log`), and a
printed line can carry a secret: a gate thread's report, a command's own
output tail, a pull request title, a receipt body. So every line the
module prints goes through `emit`, which calls the same `redact`
function. A writer added later (the inbox of T10, the punch list of an
older spec revision) uses `write_record`, `append_record` or `emit`, and
the rule holds for it without the writer knowing the rule.

The patterns, in the order they are applied:

| Pattern | What it matches |
| --- | --- |
| `private key` | A PEM private key block, from `BEGIN` to `END`, and a block that was cut short (the check's own output often ends in the middle of the key). |
| `aws key`, `github token`, `gitlab token`, `anthropic key`, `openai key`, `slack token`, `google api key`, `huggingface token`, `npm token`, `stripe key` | The token shapes of the tools the shift's own builders use. |
| `jwt` | A JSON web token. |
| `authorization header`, `bearer token` | An `Authorization:` header and the token behind `Bearer`. |
| `cookie`, `session cookie` | A `Cookie:` or `Set-Cookie:` header, and a session cookie on its own when it sits in a cookie context and is long enough to be a token. |
| `url credentials` | The password in a URL with credentials in it. |
| `secret field` | A `api_key=`, `password:`, `client_secret:` field, in JSON, in YAML or in a command line, quoted or not. |
| `environment secret` | An environment variable whose name ends in `TOKEN`, `SECRET`, `KEY`, `PASSWORD`, `PASSWD`, `PASSPHRASE` or `CREDENTIALS`, anywhere in the line. |
| `.env value` | A `.env` line: an environment variable's name and its value, and nothing else on the line. |

The replacement keeps no part of the value and says what was redacted:
`[REDACTED:github token]`. A record that says what it hid is still a
record; a record that keeps the value is a leak. A pattern that matched
part of a line keeps the rest of the line: `GITHUB_TOKEN=[REDACTED:github
token]` still says which variable it was.

The redaction of a text is the same text: a value that is already
redacted is not redacted again. So a receipt that is written on two
cycles is the same receipt, and the receipt writer's own comparison (the
receipt on disk against the body it would write) still holds.

The patterns leave prose alone. `STATE=merged`, `session = 3 of 5` and
`Secret: unknown` are records, not secrets, and they stay readable.

The command shows the redaction on a fixture. It writes nothing.

```sh
overnight redact --file fixture.txt
overnight redact --text 'GITHUB_TOKEN=ghp_...'
```

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

`coordinator/launchd/dev.coordinator.lanes.plist` in the mac-ops
checkout is the job `dev.coordinator.lanes`, the only job that runs the
shift. The installer retires the old `dev.coordinator.overnight` job. The mac-ops installer
copies it into `~/Library/LaunchAgents` with the rest of the coordinator
jobs, so the job and the command always come from the same checkout.

The job fires on a fixed interval, every day. The shift runs 24x7, so
there is no night window, no 22:30 start and no 06:00 deadline: every
cycle is the same cycle.

| Every 5 minutes | What runs |
| --- | --- |
| Any time of day | One shift cycle. It reads the policy snapshot, runs the health checks, reads the whole board, works it and writes the receipt of every item whose state changed, plus the cycle's own health receipt. |
| 06:00 to 07:29 PT | The same cycle, and it writes the day's morning report. The report is written once a day: the first morning cycle writes it and a later cycle leaves it alone. |

The interval lives in the plist (`StartInterval`), not in the command, so
one place owns it: 300 seconds, so a stalled pull request waits at most
five minutes for its next action. The job has no `RunAtLoad`, so the
first cycle lands one interval after the job loads and not at every boot.

The job takes the shift's own lock, `~/.local/state/mac-ops/overnight-shift.lock`
(`OVERNIGHT_SHIFT_LOCK` moves it). A cycle that starts while another
cycle holds the lock does no work and says so in the log, so two cycles
never run at once, whatever starts them: the scheduled job, or a person
at a shell. A lock that cannot be opened refuses the cycle, because a
cycle that runs unlocked is a cycle that can overlap another one. A cycle
takes about a minute and a half on the current board, well inside the
five-minute interval.

The Mac must run on Pacific time for the shift log to say Pacific time.
If the Mac's clock is not on Pacific time, the job still fires, and it
says so in the log.

The job runs real cycles (spec part T14): a cycle reads the board under
the policy snapshot, works it with no item cap and writes a receipt for
every item whose state changed. It still starts no builder and runs no
merge and no push: the queue starts the work, under the rules that apply
today, and the shift records what it really saw. The policy snapshot (T4)
is read on every cycle, and a cycle that finds no snapshot refuses to
work.

Every cycle also runs the health checks below before it acts on the board,
and writes the cycle's own receipt, `receipts/cycle-<stamp>.md`. A dry run
(`shift --dry-run`) writes that receipt too and no ticket receipt.

## The health checks of a cycle

Every cycle starts with the health checks the tick used to run every tick
(`loop/tick.md` section 1b). The tick is retired for the 24x7 shift, so
the shift runs them instead. They read only; they change nothing.

| Check | What it reads | What a finding means |
| --- | --- | --- |
| The tools | `coordq status` and `overnight --help` under the interpreter launchd uses, plus the last 40 lines of `dispatch.log` and `gatekeep.log` | A tool breaks under the launchd interpreter, or the queue's log holds a traceback (2026-11-13: a duplicate parser argument stopped the dispatcher for 14 minutes). |
| The installed files | `install_coordinator.py status` in the mac-ops checkout | The installed coordinator differs from the merged main (2026-11-13: the installed coordq came from an unmerged branch). |
| The board's attempts | The `Starting ... attempt` comments of every board ticket, against the open pull requests | A ticket was started three or more times and has no pull request, so its spec is broken. |
| The board's blockers | The refusals the queue recorded, against the state of the issues they name | A text blocker refusal names an issue that is closed, so the blocker is false (2026-11-13: four FFBT tickets were held by a false text blocker). |

Each finding is one line of the cycle's receipt, one ALERT line in the
shift log and one line of the report's `## Health and drift` section. A
finding the shift may fix under its own rules (resend, park) it fixes;
anything else is an ALERT. The shift's board work is not built yet (T5),
so today every finding is an ALERT and the receipt names the action each
one would take.

The shift is never armed: `run/armed` does not gate it, and every cycle
reads the board. The morning report has a time even though the shift does
not: the first cycle of the morning writes the day's report, so Shyam
reads one report in the morning. `run/STOP` still stops the shift at the
next cycle, and the report still runs when it does: the report says the
shift ended with STOP.

## The attended first night

`overnight attend` is the rehearsal before the first unattended night, and
the command a person runs when they sit down to watch.

```sh
overnight attend --items 3 --minutes 60 --run-by Shyam --wait
```

- It reads the board (`ticket list --fresh --json`) and takes the first
  small items the board shows: on the todo stage, in an allowed
  repository, and of a type that is one small part (`chore` or
  `standard`). A ticket Shyam holds is not in the board list at all, so
  the night never takes one, and the Ascend keys are never taken.
- It arms the shift in the folder it is given: `run/armed`,
  `run/deadline` and `run/policy.json`. The policy records the allow
  list, the queue's slot cap (read only, never raised), the stall cap, the
  retry cap and the verify level. The rehearsal keeps its own window
  (`run/armed` and `run/deadline`) because it is a rehearsal with a human
  in it; the shift itself has neither and always runs.
- It observes each item for real, with read-only commands only: the open
  pull request for the ticket, the checks on it, the gate's verdict on it
  and the files it touches. It runs no merge, no push and no builder.
- It writes one receipt per item, the shift log and then the morning
  report, from the same records the report part reads.
- `--wait` holds the door until the window closes, and then the night
  ends at the deadline. Without it the night ends as soon as the items
  are observed, and the shift log says that the window is still open.
- `--run-by` records who ran the night. The records never claim that a
  person watched: the command cannot know that, so it says who ran it.

`--dry-run` reads the board and writes nothing. `--root` points the night
at another folder, which is how a rehearsal runs without touching the
live records. Without `--root` the night writes to a dated folder under
the runtime folder, so it never mixes with the live receipts.

Load it after the install:

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.coordinator.lanes.plist
launchctl print gui/$(id -u)/dev.coordinator.lanes
```

Its log is `~/Library/Logs/coordinator/lanes.log`.

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
| `run/` | The shift contract: the policy snapshot, and the STOP file that ends the shift. |
| `receipts/` | One receipt per item, plus the morning report. Receipts are the only proof a cycle writes. |
| `inbox/` | What the shift could not decide or could not fix: the parking lot and the snag log. |
| `staging/` | Scratch for work in flight (worktree path, branch, builder notes). It is scratch, not a queue: an empty shift leaves it empty. |

## Files

The names come from the overnight runner spec, section 6 (revision 2), as
revision 3 changes them.

| File | Who writes | What it holds |
| --- | --- | --- |
| `run/policy.json` | `overnight policy` (and the attended first night) | Snapshot: allow list, slot cap (read only), stall cap, retry cap, verify level. No item cap and no allowance stop. |
| `run/armed` | The attended first night only | Shift id and start time of the rehearsal. The shift is always armed (revision 3). |
| `run/deadline` | The attended first night only | UNIX epoch the rehearsal ends at. The shift has no deadline (revision 3). |
| `run/STOP` | Shyam (or `overnight.sh stop`) | Stop wins. The shift ends at the next cycle. |
| `run/stall-state.json` | A cycle | How long every item the shift measured has been idle, and which items are parked as a stall. It holds no list of work: the board is the list. |
| `run/mute-state.json` | A cycle | Which alarm keys are quiet and until when. It is the mute for the alarms the shift raises (Refs #496), and it lives here and not in the board file, because the coordinator rewrites the board file. The write merges, so a tick cannot take an acknowledgement that landed while it ran with it. |
| `receipts/<item>.md` | A cycle (`overnight receipt`) | State, PR link, checks run and result, Opus gate verdict, files changed, time used, why it stopped. |
| `inbox/parking-lot.md` | A cycle (`overnight park`) | Decisions the shift could not make. Each with a default and a recommendation. |
| `inbox/snag-log.md` | A cycle (`overnight park`) | Problems found (flaky test, conflict, dialog) and what the shift did. |
| `run/shift-log.md` | All steps | One line per event, with PT time. It also states how the night ended (`ended: deadline`, `ended: all done`, `ended: STOP` or `ended: stall`). |
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

## The parking lot and the snag log

The shift works the board on its own and cannot make every decision. What it
cannot decide is parked; what it found is logged.

| File | What it holds |
| --- | --- |
| `inbox/parking-lot.md` | The decisions that wait for Shyam now. One section per item, each with a `Default:` line (what happens when he says nothing) and a `Recommend:` line. The file is written whole, so a decision that is no longer waiting leaves it and the morning report never names a decision that is gone. |
| `inbox/snag-log.md` | The problems the shift found and what it did about them. One section per problem, and a problem the shift finds twice is written once. |

What gets parked:

- A **pending approval request** on a thread that holds the work. The request
  is parked with its exact text, quoted as the tool showed it, and it is
  never answered. The shift has no call that answers a request: it reads the
  thread and writes the record. The request that is parked is the last one
  the thread holds that is still open, so a question that was already
  answered is never parked as if it waited for an answer. The proof
  (`evidence/MO-220/prove-park.py`) runs the command with a T3 stub that
  fails on every call but a read, so an answer would fail loudly.
- An **open decision in the coordinator's decisions log**. The log is the
  coordinator's own parking lot, so the shift reads it, quotes the open
  line and parks the ticket with it.
- A ticket the filter **drops for a decision**: a ticket marked as needing
  Shyam, a ticket marked as needing a design, a ticket with an open item or
  a hold in the decisions log. A ticket dropped as Ascend work, or as being
  off the allow list, is not a decision and is never parked.

What gets logged:

- A **failing check** on a pull request: the check names and what the shift
  observed about it.
- A **pending request whose text could not be read**: the item is parked
  without the text and the request is still not answered.
- An **item the shift's own budget rule holds back**: over its hard
  builder-time budget, or out of fix tries. The entry records the
  observation (the builder's own time and the queue's own count of fix
  tries) and never states that the item was stopped or parked on the
  strength of that observation alone.
- A **thread that could not be read**: the parking lot is then not
  rewritten, because a decision that is still waiting must not leave the
  file because one read failed. A dry run refuses the same way: it prints
  an INCOMPLETE line, shows the failure, writes no file and exits
  non-zero.

Three rules keep the records honest:

- A snag entry that names an action quotes the shift's own receipt for the
  item. The receipt is looked up by the **ticket's** number: a pull request
  is looked up by the issue it is linked to, never by its own number, so an
  entry never quotes another ticket's state because two numbers collided.
  An item with no receipt says that the action has not been verified.

- A quoted request is fenced, and the morning report's parser reads the
  fences, so a request that holds a heading or a `Default:` line cannot
  change the decision it is quoted in.
- A decision keeps the time it was first parked, and a problem keeps its
  first entry, so the records hold the state and not the cycles.

## What the morning report reads

The report is rendered from the records in this folder and from nothing
else. It never invents a count and it never upgrades a claim into proof.

| Record | What the report takes from it |
| --- | --- |
| `receipts/<item>.md` | The state of one item, its check, its gate verdict, its merge time, its builder time and why it stopped. The merge time is the one the shift wrote after it checked GitHub, so the report does not call GitHub again. |
| `inbox/parking-lot.md` | The decisions the shift could not make, each with a default and a recommendation. |
| `run/shift-log.md` | How many items were in scope (`planned N items`), whether the full suite ran and with which exit code, whether the shift stalled, and how the night ended (`ended: deadline`, `ended: all done`, `ended: STOP` or `ended: stall`). |
| `run/policy.json` | The verify level and `allowance_used_percent`, the share of the plan allowance the night used. |
| `run/armed`, `run/deadline` | The window of the attended rehearsal, in PT. A shift that is always armed and has no deadline has no window, so the report writes the window as UNVERIFIED. |
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
| `Time used` | The builder time, as `N min`. It is the sum of the thread's own runs, so the idle time between two runs does not count. A night that ran no builder says `0 min`. |
| `Observed` | How long the shift spent looking at the item, in seconds. It is not builder time. |
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
  explain none of them, it says `UNVERIFIED`. The shift log may state
  how the night ended, and the report reads that statement only when the
  records support it: a claim is never a proof.
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

## Prompt changes wait for Shyam (Refs #543)

A prompt, skill or playbook change never auto-merges (Shyam, 2026-11-17).
The gate merged such a pull request anyway (mac-ops #542), so the paths are
now checked instead of remembered. One list lives in
`coordinator/bin/prompt_paths.py` and two places read it:

- `ticket gate` builds the brief with the no-merge sentence in place of the
  merge order. The brief says do not merge and close nothing, and names the
  change as prompt text.
- The lane driver checks the same list before it merges a passing pull
  request. On a prompt change it merges nothing and writes one item
  (`kind: action`, id `prompt-merge-<key>-<pr>`) asking Shyam to merge it. The
  item goes to `~/Code/coordinator/decisions.json`, except for mac-ops (key
  `MO`), which goes to the mac-ops owner board
  `~/Code/coordinator/mac-ops-owner.json` (`COORDINATOR_OWNER_BOARD` moves
  it). The item is keyed by
  id, so a second pass replaces it instead of adding a second one. A pass
  also takes the item down, but only once the pull request itself reports
  `MERGED` or `CLOSED`: the open list a pass holds stops at 200 requests, so
  an older open request can be missing from it without being settled, and a
  state that cannot be read keeps the card until the next pass.

A file list GitHub cannot give is not code: the read is retried, and a list
still unknown defers the gate or the merge instead of guessing. A brief
written without the list could order a merge of prompt text, so an unknown
list never reads as clear. A list shorter than the pull request's own
changed-file count is unknown too, because GitHub's files endpoint stops at
3,000 and the dropped entry can be the prompt file; when the caller holds no
count, the pull request itself is read for it. A list that can never be
completed falls back to the complete diff, comparing the merge base's tree
with the head's tree, so a 3,001-file pull request of ordinary code still
merges while one that hides a prompt file still holds. That read is paginated and slurped like the rest,
so the single pull request is the only row of a list and the count is read
from that row. A renamed file counts
under both names, so moving prompt text out of `prompts/` still holds the
pull request. The list covers
`AGENT-RULES.md`,
`answer_format.py`, `gate_bar.py`, `gate_findings.py`, `gate_policy.py`, `playbook.md`,
`code-reviewer.md`, any `SKILL.md`, and anything under a `skills/` or
`prompts/` directory.

The replay is the registered `gate-pipeline` eval
(`python3 coordinator/overnight/overnight selftest`): its `prompt-pass` case
requires one decisions item and no merge, provides or fast-forward, and the
negative control with the path list switched off must fail.

## Lane execution ownership (Refs #363)

`overnight shift` runs the imported lane driver under its existing lock,
after checking STOP and loading policy. The installer copies `lane_driver.py`
beside `overnight` and replaces `dev.coordinator.lanes` with a job invoking
`overnight shift` every 180 seconds. It is the only job that runs the shift. The lane module has no standalone entry point.

The prototype's repository list, action order, ledger, retry routing and
watchdog remain unchanged. State stays in `~/Code/coordinator/loop` and the
watchdog still updates `~/Code/coordinator/decisions.json`. The helper briefs
in that runtime directory remain prerequisites. The shift policy controls
whether execution can begin; execution refuses if any prototype repository
is excluded. Driver output uses the shift redaction function.

Run `python3 install_coordinator.py --help` for installation and status.
Install only after merge from clean main. Live installation and same-board
service output comparison were waived for this PR; the fast check validates
syntax and the existing installer checks, not live board parity.

### API budget and board snapshot

The lane ledger stores one board snapshot and its successful refresh time.
A pass reuses it for 900 elapsed seconds, regardless of which scheduled job
invoked the shift. Ticket selection, PR actions and orphan detection all
use that snapshot. A failed refresh never replaces the last complete snapshot.
The shift no longer runs separate order and receipt board reads after lane
execution; receipt refresh is available through `overnight receipt` explicitly.
The morning report therefore reads existing receipts, which may be older.

Before optional GitHub reads and ticket start checks, both REST and GraphQL
remaining quota must be at least 500. Unreadable quota stops optional work.
Every pass logs before/after quota usage, including budget stops. The delta
also includes concurrent account activity and may span a quota reset.
Existing three-dry-run limits and 30-minute refusal caching remain in force.
Live-service, device and owner testing were waived, not failed.

## Fixture evals

Run `python3 coordinator/overnight/overnight selftest` from the checkout.
The command prints one PASS/FAIL line per registered eval and exits nonzero
on any failure. Only `start-routing` is registered. Later loop tickets must
extend this registry; unimplemented evals are never reported as passing.
The fast check runs the same command.

The fixture uses six synthetic repositories and the production lane selector,
run-pass wiring, orphan path and ticket launch-payload builder. Subprocesses
are denied unless replaced with fixture responses. Removing NEVER_START is
a negative control that must make the eval fail. Configuration loading now
happens at lane main entry, so importing the lane module reads no live files.

The adapter excludes occupied SRW chain groups and relaunches dead orphan
receipts through ticket start. It does not install or cut over the loop.
The fixture also exercises type-to-alias resolution through cmd_start and
checks the dispatched refresh request (`startFromOrigin: true`). Missing or
malformed SRW thread lists refuse dispatch. Live smoke, hourly tick integration,
T3 internal Git refresh execution, issue label parsing and the other eleven
evals remain outside this proof.

Occupied SRW groups also filter orphan recovery, including dead-thread
relaunches and generic unstick batches. Snapshot issue reads include titles
for the same group classifier. A cached orphan without a title is skipped
when groups are occupied until a refreshed snapshot supplies its group.
The fixture exercises the full run-pass fallback with an occupied bot group:
bot and unknown-title orphans produce no actions or ledger changes, while a
census orphan relaunches through ticket start.

SRW uses one refreshed thread-list boundary after PR actions for both ready
starts and orphan recovery. The fixture starts with an idle busy result,
simulates a PR launch, then requires the occupancy refresh to happen after
that launch. Same-group recovery, invalid responses and full capacity all
produce zero additional actions and no recovery ledger writes.


### Gate pipeline fixture eval (Refs #375)

`python3 coordinator/overnight/overnight selftest` registers `gate-pipeline`
alongside `start-routing`. It calls the production `lane_driver.act_on_pr`
handler and gate verdict reader with fake GitHub snapshots, T3 responses and
command receipts. Subprocess creation and filesystem opens are forbidden.
No service is contacted and no thread is launched.

The cases cover an exact checked head, PASS, FAIL findings sent to a builder,
no verdict, a second no-verdict, quota evidence, manual Concerning merge and
excluded Ascend work. The action comparator rejects an extra forbidden action.
The merge command must include `--match-head-commit` with the full head.

Current evidence: all three registered evals pass. Gate launch and PASS
completion now use the production adapter. A no-verdict gate retries once;
only explicit Astra quota exhaustion permits Opus fallback after that retry.
A second infrastructure failure records needs-you without parking the PR.
Concerning remains manual merge and Ascend is excluded.

PASS completion uses an exact-head squash merge, then `ticket close` verifies
the PR is merged on that head and references the issue. Closure also requires
the gate's exact-head `PROVIDES: PASS`, `CHECK: PASS` and final `VERDICT: PASS`
lines. Missing evidence refuses closure. The gate brief requests Provides
verification and assigns merge ownership to the lane. The fixture exercises
the actual close handler with valid proof and refusals for unmerged or wrong
heads, wrong issue references, missing merge commits and failed proof lines.
Provides facts remain a reviewer attestation, not an independent machine proof.
The final local update reads git worktree list --porcelain -z, finds the
worktree holding refs/heads/main, verifies its branch, and runs git pull
--ff-only there. If main is not checked out, it fetches origin main:main
without changing the canonical checkout branch. Invalid listings or changed
branches refuse the update. Fixtures cover a canonical feature branch with
main elsewhere, an unchecked-out main, paths with spaces, and refusal cases.
Command failures now raise rather than being recorded as successful sends.
No runtime is installed and live checks remain waived.

### No parking fixture eval (Refs #376)

The `no-parking` eval calls production `act_on_pr` and `send` with injected
snapshots, FAIL histories, interrupted builder responses and command receipts.
It requires another fix after two prior fix heads, one continue send per head,
and a fresh fix and continue after the head changes. Exact actions and ledger
keys reject parking, PR closure, extra sends and missing sends. An extra park
action is a negative control that the comparator must reject. Subprocesses
remain denied by the suite and filesystem opens are denied by this fixture.

The production adapter removes the FAIL count parking boundary and replaces
stopped-builder parking with a continue send keyed by repository, PR and head.
The newer loop eval spec and coordinator notes override lane.md section 6.
Run `python3 coordinator/overnight/overnight selftest`. All three registered evals pass.
No runtime installation or live service proof is included. Dead thread rerouting,
send receipt failure handling remain outside this fixture's proof.

The no-parking fixture also covers completed and failed builder statuses. A
production-path negative control replaces send with a no-op and requires the
eval to fail, so missing fix dispatches cannot produce a passing result.


### Turncap eval (Refs #377)

`overnight turncap [--dry-run]` uses the owned `turn_cap.py` installed in
`~/.local/bin`. The launchd plist uses the same installed script. The old
`~/Code/coordinator/loop/turn_cap.py` remains untouched for rollback.

`overnight selftest` intercepts T3 calls, filesystem writes, clock and sleep.
It checks per-run clocks, heavy-wait pauses, warnings after 10 active minutes,
and interruption and parking after 20 active minutes. Attempts stay unchanged.
Its planted early-interrupt negative control must fail the same assertions.

### Turncap gate receipts (Refs #397)

These command outputs were captured from the implementation reviewed in PR #398.
No real install or launchctl mutation was performed.

Command: `timeout 300 heavy env PYTHONPATH="$PWD/coordinator/overnight" overnight selftest`

```text
PASS start-routing
PASS gate-pipeline
PASS no-parking
PASS turncap
```

Command: `timeout 300 python3 install_coordinator.py install --dry-run`

```json
{
  "action": "coordinator",
  "would_write": [
    "/Users/shyamsivakumar/.local/bin/turn_cap.py",
    "/Users/shyamsivakumar/Library/LaunchAgents/dev.coordinator.turncap.plist"
  ],
  "would_retire": [],
  "would_reload": [
    "dev.coordinator.turncap"
  ],
  "overnight_root": "/Users/shyamsivakumar/Code/coordinator/.overnight",
  "would_create": []
}
```

The installer's read-only `render_plists` preview decodes to:

```text
/Users/shyamsivakumar/Library/LaunchAgents/dev.coordinator.turncap.plist
['/usr/bin/python3', '/Users/shyamsivakumar/.local/bin/turn_cap.py']
```

The installed payload and plist argument reference the same script.
Device, handset and live-service testing were waived by Shyam, not failed.
Live installation and behavior are unverified; the coordinator owns installation.

### Active run interruption safety (Refs #397)

Turncap skips reads with no running run or no running start timestamp.
Completed runs and thread update timestamps cannot supply the cap clock.
Interrupt requests include the observed `runId`, so a replacement run is not
selected by a thread-only interrupt. The selftest requires that identity on
both threshold and heavy-wait interruption paths; timing assertions are unchanged.

Focused intercepted-call probes passed for empty and completed-only reads
(no interruption), and selection of the running identity beside completed history.
Device, handset and live-service testing remain waived, not failed.


### Eval 6: zero-merge (Refs #379)

`python3 coordinator/overnight/overnight selftest` now registers `zero-merge`.
The lane driver's normal command checks the monitored board after its pass.
With open PRs and no merge in the preceding 60 minutes, it writes one
`factory-zero-merge` action to the mac-ops owner board
`~/Code/coordinator/mac-ops-owner.json`, not decisions.json. The same board
takes `factory-overnight-stall` and the mac-ops `lane-gate-rounds-*` items.
`alarms.route_update` picks the board by id and removes any copy of that id
still on decisions.json. A merge anywhere in the monitored
repos at or after the cutoff clears the action. No open PRs also clears it.
The check uses the existing board snapshot and budgeted GitHub read adapter;
failed reads abort before changing the action. Dry runs skip the check.

Fixtures inject GitHub mergedAt responses, UTC time and decisions-file writes.
They check old merges, an empty history, the exact cutoff, a recent merge in
another repo, repeated raises, recovery, unrelated-item preservation and the
atomic replacement target. A disabled production handler must fail the fixture.
All six registered evals pass; evals 7 through 12 remain unimplemented.
The repository check is `python3 scripts/mac_ops_fast_check.py`.
Live execution and installation are not verified by these fixtures.

### Eval 7: board-integrity (Refs #380)

`overnight selftest` runs the same reporter as the read-only command
`overnight board-integrity < snapshot.json`. The command prints every defect
and exits 1 when any are found, or 0 for a clean board. Imports perform no I/O.

The snapshot has `tickets` (repo, number, stage) and a `repos` mapping. Each
repo has its configured `key`, `issues` (number, title, state, labels and
optional GitHub `blockedBy` nodes/totalCount), and `prs` (number, state, body).
Include open issues, open and merged PRs, and the prior started ticket states.
Missing blocker fields mean no blockers; provided blocker lists must be complete.
PR bodies use the coordinator's `Refs #n` convention for same-repo issues.
Keys must have the configured uppercase prefix and a positive integer suffix.
Backlog and hold stages identify parked issues under the eval contract.

Fixtures assert the exact seven diagnostic strings for absent and multiple
stages, malformed and duplicate keys, lost started state, a parked blocker
with an open PR, and an open issue referenced by a merged PR. A clean case
checks exit 0; disabling the reporter must fail the eval. All subprocesses
remain forbidden by the suite harness. No unimplemented eval is registered.

Left for later: live snapshot collection, pagination completeness, persisted
started-state history, cross-repository PR references, and periodic loop wiring.
The command reports defects and does not repair or mutate the board. Live
service checks are waived for this ticket; fixture evidence proves the supplied
snapshot boundary, not live GitHub state.

### Eval 8: api-budget (Refs #381)

The canonical lane driver caches a successful board snapshot for five passes.
The first pass collects it; passes 6 and 11 refresh it. The persisted pass
counter replaces the former 900-second cache so rapid passes cannot exceed
the budget. An older snapshot without a pass marker refreshes once.

`overnight selftest` exercises the actual snapshot, start, quota and main
handlers with canned subprocess responses, clock and file handles. It checks
exact read counts across eleven passes, at most three refused dry-runs per
repo, suppression at 1799 seconds and retry at 1800 seconds, both quota
resources below the floor, reads at the floor, and usage logging on normal
and quota-aborted passes. A one-pass refresh negative control must fail.
All eight registered evals pass; evals 9 through 12 are not registered.

Verification: `overnight selftest` and `python3 scripts/mac_ops_fast_check.py`.
No live service, installed loop or cutover is exercised. Left for later:
failed snapshot collection retries, quota endpoint failures, and end-to-end
live pass telemetry. The coordinator owns installation and the Opus gate.

### Lane item failures

The driver keeps subprocess commands strict and catches command failures and
timeouts at PR, ticket-start, orphan-recovery and main-refresh item boundaries.
A repository boundary also protects later lanes from a failed lane action.
Each caught failure emits one ITEM ERROR line with repository, item, command,
exit status and the first output line. The pass prints ITEM SUMMARY and raises
after processing the lanes when any item failed, so shift health stays failed.
The per-pass count is retained in the lane ledger. API budget exhaustion remains
a pass-wide stop, and it does not hide an item failure: a pass that is stopped
by the API budget after an item failed still prints ITEM SUMMARY and still
fails.

The driver's LANE_REPOS list excludes digitized/Concerning; both board reads
and main-refresh scheduling use that list, and the repository's entry is gone
from the per-repository pull-request order and checkout map. The manual-merge
branch in the pull-request handler stays, because the registered gate-pipeline
eval still exercises it. No installed lane configuration is changed until
installation.

#### Ticket #407 live dry pass

The gate at 94f6a66ce7655b7d2473c6aebd4350445f988645 found no code defect
and failed for missing proof: a real dry pass of the driver with one planted
failing item. The fix round's brief applies the full proof bar to this diff,
because the diff changes when a lane pass stops and raises failure, so the
waiver that an earlier commit recorded for that proof is withdrawn and the
pass was run.

The pass ran the driver from this branch against the live board with the
driver's own DRY flag set. The board snapshot, the `ticket list --json
--fresh` read, the GitHub pull-request and issue reads, the thread lists and
the per-repository `git rev-parse` checks were real reads of the live
services; only the mutating actions were skipped, which is what the flag
means. The lane ledger path pointed at a copy of the live ledger whose pass
counter was advanced, so the driver's own read path took fresh board reads
instead of the ledger's cached snapshot; the copy was never written back.
One real command was planted to fail: the mac-ops main-refresh `git rev-parse`
exited 2 with "planted failure". Every other `git` and `ticket` call reached
the real binary. The plant was a temporary PATH wrapper and it was removed
after the run.

The pass logged the planted failure once, processed the items and the lanes
after it, and raised at the end so shift health stays failed:

```text
ITEM ERROR repo=shyamsivakumar/mac-ops item=main-refresh command='git -C /Users/shyamsivakumar/Code/mac-ops rev-parse main origin/main' exit=2 output='planted failure: local main could not be read'
MO    busy (live: #408 fix 94f6a66c r1); PR actions still run
SRW   busy (live: SRW-1017 review #1167 df608018); PR actions still run
FFBT  busy (live: FFBT-48 · Connect auction target shared evidence to live pro); PR actions still run
CTL   nothing ready
ITEM SUMMARY failures=1
API USAGE used={'core': 12, 'graphql': 13} remaining={'core': 2435, 'graphql': 4501} floor=500
RuntimeError: lane pass completed with 1 item failures
```

The planted failure was logged once, the mac-ops, strategy-replay-workbench,
fantasy-football-toolkit and catalogue lanes all ran after it, and the pass
raised at the end so shift health stays failed.

An earlier run of this pass, whose driver differs only in when the summary
line prints, also caught a live failure the board produced on its own: the
ticket CLI refused `ticket start` for SRW#1084 with exit 2 and the message
"merged PR #1094 changed only docs; not treated as delivery". That refusal is
not the "refused: " form the driver already tolerates, so before this change
it would have ended the whole pass; here it was caught at the ticket-start
boundary, logged once, and the pass continued through the remaining lanes
before it raised.

The command log of that run is the whole set of commands the driver ran:

```text
GIT-CALL -C /Users/shyamsivakumar/Code/mac-ops rev-parse main origin/main
GIT-CALL -C /Users/shyamsivakumar/Code/strategy-replay-workbench rev-parse main origin/main
GIT-CALL -C /Users/shyamsivakumar/Code/fantasy-football-toolkit rev-parse main origin/main
GIT-CALL -C /Users/shyamsivakumar/Code/catalogue rev-parse main origin/main
TICKET-CALL list --json --fresh
```

No call touched digitized/Concerning or /Users/shyamsivakumar/Code/concerning.
The pass rewrote the coordinator's decisions.json the way every production
pass does through the watchdog; the watchdog reported no stale job, so the
file holds the same items. The lane ledger was not written, because the dry
flag skips it. The ticket-start call was a dry run of the ticket CLI and
started nothing. Installation and the live shift remain unverified.

#### Repeatable offline dry-pass proof

Run `python3 coordinator/overnight/proofs/item_failure.py`. The proof executes
the complete driver main in a child process with DRY enabled. It relocates
hardcoded filesystem paths into a temporary directory and supplies executable
gh, ticket and t3mcp fixtures through PATH. No driver function is mocked or
replaced. The ticket executable plants the reported gate-brief exit 2.

The one-failure case logs the failing PR once, processes its successor and
the remaining repositories, then exits nonzero with failures=1. The all-fail
case logs all five attempted PRs and exits nonzero with failures=5. The third
case stops the pass with the API budget right after an item failed, and the
pass still exits nonzero with the item failure. Every ITEM ERROR line is
checked for its repository, item, command, exit status and output text, not
only for its count. Command receipts assert that Concerning is never touched.
The dry ledger is not written; temporary commands and files are removed after
every pass.

This is offline process evidence: it repeats without the live board and
without any live service. The live dry pass above is a separate record, and
neither is a claim about the installed driver or about a live shift. Device
and handset testing remain waived, not failed.

### Eval 9: fast-forward drift

`overnight selftest` exercises `lane_driver.drift_ff` with injected Git,
queue and filesystem responses. It checks one queued chore per origin SHA,
a new chore for a new SHA, no action for equal refs, and a report without
queue or ledger changes when Git rejects ancestry. A missing-chore negative
control must fail. The adapter checks the observed immutable SHAs with
`git merge-base --is-ancestor` before queueing; Git errors other than the
non-ancestor exit remain item failures. The chore still owns the eventual
fast-forward and must handle refs changing after this check.

All nine registered evals and `python3 scripts/mac_ops_fast_check.py` pass.
This is offline decision-path evidence; installed and live behavior are
unverified. Evals 10–12 remain for their owning tickets.

## Script result fixtures and commands (Refs #383)

`overnight selftest` includes `script-results`. It checks missing results past
(deadline strictly less than now), pending results at the deadline, explicit
PASS/FAIL results, and one re-cut action per failed record. The negative
control removes reconciliation and must be rejected.

`overnight script-results --now <epoch>` reads a JSON array from stdin. Each
record has `repo`, `issue`, `deadline` (epoch seconds), `state`, and an optional
`result` (`PASS` or `FAIL`). It prints updated records and re-cut actions;
the coordinator must persist these records and consume those actions. It does
not launch threads or mutate tickets. This PR does not wire a live loop.

`overnight script-run --repo <repo> --issue <n> --sha <sha> --timeout <seconds>
--artifact <path> -- <command> [args...]` runs the supplied script, then posts
one RESULT comment. Nonzero exits, timeouts and launch errors post FAIL.
Comment failures propagate as errors rather than claiming delivery. Callers
must use scripts that do not post a second RESULT themselves, and must supply
the SHA and artifact identity. The wrapper does not verify artifact contents
or terminate detached descendants; it must not wrap scripts that daemonize.
Default selftest intercepts all subprocess calls and performs no live posting.


### Eval 11: consolidation-guard (Refs #384)

`overnight selftest` inspects the actual builder and gate brief generators
and captures the lane re-cut dispatch with a fake command runner. The re-cut
brief limits creation to two tickets and prohibits a third; a repeated dispatch
uses the ledger receipt. Removing the dispatch must fail the negative control.
This proves the dispatched instructions, not compliance by a live planner.
Ticket bodies and coordinator comments are trusted inputs; the fixture covers
the generated brief with a representative scoped body. No live thread is launched.

### Send integrity (Refs #385)

`overnight selftest` registers exactly 12 fixture evals, including send-integrity.
The lane reads thread status before queueing a send. Missing, archived, unknown,
or explicitly unsendable threads route to a fresh thread and print `SEND REROUTE`.
Continuation uses the same handler and keeps its existing cooldown and priority.
A failed command or empty receipt leaves sent bookkeeping unchanged. Failed
continuations do not fall through to the unrelated unstick launch.

The fixture covers allowed statuses, rejected statuses and flags, failed commands,
empty receipts, dry mode, continuation routing, and an unchecked-send mutation
that must fail. Fixtures replace T3, command execution, and file reads. They do
not prove delivery after coordq accepts a request: a thread can change status
between inspection and queue execution. Live-service checks and cutover are waived.


### Hourly fixture scheduling (Refs #386)

`coord-tick` runs the canonical `overnight selftest` under its tick lock before
checking model availability. Each completed attempt persists its injected clock
time in `~/.local/state/mac-ops/overnight-selftest.json`. Runs less than an hour
later skip the subprocess, including after a launcher restart. The subprocess
has a 120-second timeout and must return exactly the registered PASS lines the
adapter expects, the set in `EXPECTED`, with exit status zero. The adapter
runs the `overnight` executable beside it and keeps the checkout copy as its
one fallback; when neither is there it reports a missing executable rather
than a failing suite. Failure, timeout, or runner errors replace the
single `overnight-selftest` action in coordinator `decisions.json`; a later PASS
removes it and preserves other items.

The existing watchdog eval also exercises scheduling with a temporary filesystem,
a fake clock and an injected runner, including the executable that sits beside
the adapter, recovery and a negative control.
Run `overnight selftest` or `python3 scripts/mac_ops_fast_check.py` for evidence.
No installation or live tick was performed for this change. The launcher and
its sibling coordinator files must be installed together through the existing
installation process. Malformed state files and concurrent decisions writers
remain outside the scheduling fixture coverage.

### Read-only live smoke (Refs #388)

Run `git fetch origin` and then `python3 coordinator/overnight/overnight selftest --live`.
The adapter performs two consecutive passes. Each reads `origin/main`, GitHub's
mac-ops main SHA, and a bounded T3 thread list through the installed `t3mcp`.
Every successful pass prints its UTC timestamp and exact main SHA. A SHA mismatch,
authentication failure, unavailable service, timeout, or malformed response exits 1.
Keep both PASS lines as the pre-cutover receipt. The command does not fetch,
install, launch threads, send, merge, close, comment, label, or persist receipts.

Only the three exact command argument lists in `live_smoke.COMMANDS` are allowed.
Each subprocess has a 15-second timeout; the six reads take at most 90 seconds
apart from process cleanup. Service output and exception diagnostics are never
printed; failures use fixed messages. Existing CLI authentication is used without
opening credential or `.env` files in the adapter.

Default selftest remains the twelve fixture evals. The api-budget eval additionally
checks this adapter with fake subprocesses, rejected write commands, malformed and
failed service responses, timeout handling, two-pass output, and a disabled
allowlist negative control. These fixtures do not prove live authentication or
service availability. Live-service testing and the two live receipts were waived
for this ticket; they remain necessary evidence before a future loop cutover.
No loop installation or cutover is included.


## PR state classification (Refs #277)

`overnight board --json` classifies PRs by draft, conflict, missing ticket link,
failed or missing exact-head check, and gate state. It reports `states`,
`oldestByState`, and `noAction`. Builder lookup uses ticket receipts and then
thread titles. Missing builders produce `needs-you`.

Dispatch retains origin/main behavior. The latest ticket instruction limits
this delivery to classification. Additional dispatch, reminder and dedupe work,
state matrix proof, and live board counts remain unverified.
See `evidence/MO-254/status.md` for verification and limitations.

### The watchdog reads the job's real state (Refs #479)

The watchdog used to treat a log's mtime as proof of life. A job with nothing
to write writes nothing, so a quiet log raised a false alarm about a live job
and put a fake question on the board. The `WATCH` table now holds the launchd
label of each job beside its log and its silence limit, and the watchdog asks
launchd what the state of the job is.

The signal is `launchctl print gui/<uid>/<label>`. A job that launchd holds
and that ends clean is alive, whatever its log says, and the watchdog says so
in a `WATCH <job>: signal=launchd ...` line. A job that launchd no longer
holds is stopped and alarms. A job that is idle now and whose last exit code
is not zero, or that launchd killed with a signal, is failing and alarms. A
job that is running now is judged by the run in flight alone: what an
earlier run left behind says nothing about the run that is going on, so a
job that started a moment ago after a failure does not raise an alarm, and
only a run that overruns its limit is a problem and it is stuck. When
launchd cannot say how the job ended, the log age is the only evidence left
and the old silence rule applies, so a watchdog that cannot read launchd
does not silence a real alarm. That fallback covers a launchctl that cannot
run, a launchctl failure that is not a missing service, a job that never ran
and so reports no exit code, and a running job that nobody can time.

launchd prints its status in more than one shape, and the watchdog reads all
of them: `last exit code = 0`, a code with its name (`78: EX_CONFIG`), a
signal with its name (`Killed: 9`), and `(never exited)` for a job that never
ran. A status it cannot read stays unknown, and an unknown status falls back
to the log age rather than counting as health.

The plists under `coordinator/launchd/` stay the source of truth for which
jobs exist, and the tick, dispatch and refill thresholds and the
`dev.coordinator.*` schedules are unchanged.

The board still holds one `factory-watchdog` item: the pass removes the item
and writes it back when a job is not healthy. The title names the reason and
the job.

Run `python3 evidence/MO-1056/proof.py` for the proof. The first pass reads
the live launchd state of `dev.coordinator.gatekeep` with a stale gatekeep log
and writes no alarm. The second pass stubs the stopped job and alarms with
the job's name. The proof uses a copy of the decisions file, a copy of the
log and a stub for the stopped job: it never stops the live job, never writes
the live board file and never installs anything.

`overnight selftest` covers the same ground with a fake launchd and a fake
clock: a stale log with a live job raises nothing, a stopped job, a failing
job, a job killed by a signal in both launchd shapes and a job stuck past
its limit each raise one alarm that names the job, a launchd that cannot say
or cannot be read falls back to the log age, a job that is running now is
judged by its own run and ignores what an earlier run left behind, a job
that never ran is judged by how long it has been running, the silence limit
is a limit, and the item stays a single item over repeated passes.

`evidence/MO-1056/proof.py` runs three passes: the live launchd state with a
stale log, a stopped job, and real launchctl output that reports a job
killed by a signal, so the parser is exercised on the text launchd prints.

### An acknowledged alarm stays quiet for four hours (Refs #496)

The tick's alarms reached Shyam five times on one day for causes that were
already known and being fixed. Marking one item Done on the decisions board
does not stop the alarm: the next tick raises it again, the board holds the
item again, and the phone relay sends it again. Shyam's decision (2026-11-17)
is that an alarm that was acknowledged or routed stays quiet for four hours,
unless its cause changes.

The rule lives in one place (`coordinator/overnight/alarms.py`), beside the
two places that raise these alarms: the watchdog (`factory-watchdog`, in
`lane_driver.py`) and the stall rule (`factory-overnight-stall`, in
`stall.py`). There is no second alerting path and no new alarm.

| Thing | What it is |
| --- | --- |
| The key of an alarm | The alarm's id and its cause, as one string: `factory-watchdog\|gatekeep failing (last exit code 1)`. |
| The cause | What is wrong, without the parts that change on every tick. The minutes of a quiet log and the minutes of a stuck run are not part of the cause; the exit code and the signal are. The stall's cause names the stalled repos. The idle tick count is not part of a cause: the same stall reported on the fourth tick is the same stall as the one reported on the third. |
| The mute state | `run/mute-state.json`, in the shift's own folder, next to the stall state. It is not in the board file: the coordinator rewrites the board file, and a board file that is rewritten must not take the mute with it. |
| The mute | Four hours (`MUTE_SECONDS`) from the acknowledgement. |

One thing mutes a key: an explicit acknowledgement. It is a record with the
time it was given and the time the mute ends, and it is written when the
alarm was answered on the decisions board or when the coordinator recorded
it as routed. The coordinator panel writes it when Shyam answers, through
the `alarms ack <alarm-id> <cause>` command, and the command is there for
the coordinator and for a person. `alarms status` prints the alarm keys and
until when each one is quiet, and `alarms --help` prints the usage.

The acknowledgement names the cause the panel showed, so only that cause is
quiet: another cause of the same alarm was not answered and is not silenced.
The command is the installed one (`~/.local/bin/alarms.py`, installed with
the rest of the shift's commands), and it is a file with a shebang, so the
panel runs it as a command.

A state file that is not there is an empty state: the shift measures the
alarms again from that tick on. A state file that cannot be read, or that
holds damaged text, is not an empty state. Reading it as empty would let
the next alarm overwrite it with its own key, and the acknowledgements it
still holds would be lost, so the answered alarms would come back before
their four hours are over. So the read failure is raised, and the alarm is
published as unchecked without writing over the state that could not be
read.

The healthy branch cleans the board whether the mute state was written or
not: a state that could not be read or locked must not leave a stale alarm
on the board, so the board is cleaned under the board lock either way.

The state is written with a merge: a tick reads the state, the panel records
an acknowledgement and writes the file, and the tick writes its older
snapshot. The newer acknowledgement of a key wins, so the tick cannot take
it with it. The read, the merge and the replace happen under a lock file
beside the state, so the two writers cannot land in each other, and each
writer replaces the file from a temporary file of its own. A lock that cannot
be taken is not a lock: the write fails rather than going on unlocked.

The decision and the publication happen under that lock as well. A tick
takes the lock, reads the state, decides, writes the state, reads the board,
changes it and writes it back, all before it lets go: an answer that lands in
between cannot be missed, and the alarm on the board is exactly what the
decision said. The panel's answer waits for the lock, so it is either in the
state the tick read, or it comes after the tick published and applies from
the next tick. The board is read inside the lock too, so the watchdog and
the stall writer cannot read it stale and lose each other's item.

A quiet tick changes nothing, so it writes nothing: a write that fails on a
quiet tick cannot turn a muted alarm into a published one. A board that
cannot be written is said out loud, because the alarm is then nowhere.

The board has its own lock, in a file beside the board, and it is held
across the read, the change and the replace. It is not the mute lock: a
mute storage that cannot be locked must not leave the board unprotected,
or the watchdog and the stall writer read the same board and one alarm
disappears. Each publisher also replaces the board from a temporary file
of its own. A board lock that cannot be taken does not stop the
publication: the write falls back to a compare-and-swap, which re-reads
the board and replaces it only when nobody else wrote in between, and the
board is read back so a write another publisher replaced is not counted as
delivered. So an unacknowledged alarm is still delivered when the lock file
cannot be opened, and two publishers still cannot erase one another's
alarm. A publication that cannot be made safe after a few tries says so.

An alarm on the board always has a key. The key is written before the alarm
is published, so the answer Shyam gives it has something to acknowledge. A
key that cannot be written is a fault the shift says out loud, and the
alarm is published anyway: a storage failure must not hide a real failure
from Shyam.

The panel's answer is bound to the cause it showed when he chose it: the
choice and the free-text reply alike take the cause when the answer
starts, not when it is sent. An answer that was never bound to a cause is
dropped rather than sent for the alarm that is there now, and so is an
answer whose alarm was replaced in between. A reply the popup restores
keeps the cause it belongs to, and text saved without a cause is not
restored at all: it cannot be bound to the alarm on the board now.

The rules that bind an answer live in `coordinator/mods/coordinator/answers.js`,
a module with no imports, so the panel uses it and a probe can run it.
`tests/test_alarm_panel.py` runs that module for real: a legacy draft
reopened against a replaced alarm sends nothing and acknowledges nothing,
a bound draft for another cause is dropped, and a bound draft for the alarm
on the board is sent and acknowledged. When the alarm is replaced between the answer
and the send, the answer is dropped and Shyam is told, because sending it
would answer the alarm that is there now, and he never answered that one.

The mute state lives under the root the run chose. A shift run and a
fixture run with `--root` each write their own state under their own root,
so a fixture never writes a synthetic alarm key into the live state and
never reads a live acknowledgement.

The command exits 0 when the acknowledgement was written, 1 when there is
no raised key for that cause, 2 when the usage is wrong, and 3 when the
state could not be locked or written. The panel warns on every exit but 0,
because an acknowledgement that was not written means the alarm can raise
again on the next tick, and an alarm on the board always has a key, so a
missing key is a fault and not a quiet success.

The record is the whole rule. A board item that went missing is not an
acknowledgement: the board has more than one writer and one of them can lose
the item for a tick, so an alarm that nobody answered is never silenced. It
is raised again on the next tick.

The shift asks again on every tick of a stall that continues. The rule
stops asking once the alert was delivered, but the shift does not: the
writer knows whether the alarm is due, it is quiet while the mute runs,
and it comes back when the four hours are over and the board still has not
moved.

A muted alarm writes no board item and raises no alert for that key, and the
shift logs one line per tick so the log says what it did not raise. A
different cause is a different key and alarms at once: the tick job that
fails with a new exit code, or the board that stalls on other repos, is a new
alarm and is not silenced. An alarm that is not true any more drops its
"raised" mark, so the same cause can alarm again the next time it is true,
but an acknowledgement that is still running keeps the key quiet: one healthy
tick does not take the mute with it. After the four hours are over the alarm
comes back, if it is still true.

The other board items are untouched: the merge alert (`factory-zero-merge`),
the hourly fixture selftest (`overnight-selftest`) and every item a person
put on the board keep their own rule and are never muted by this one.

Run `python3 evidence/MO-496/proof.py` for the proof. It replays both
alarms on a copy of the board file with a fixture clock. The stall is
replayed on the real path: the proof loads the overnight runner and drives
`stall_records`, so the shift's own decision to ask again on a stall that
continues is part of the proof and not skipped. The first tick raises the
alarm, the alarm's item goes missing and nobody answered, so the alarm is
raised again, the answer records the acknowledgement, the next tick is
quiet and logs one line, a changed cause alarms at once, the same cause
alarms again after four hours, and the mute survives a tick where the job
was healthy. The
`alarm-mute` eval in `overnight selftest` covers the same ground with the
fake clock, and the changed expectations in the `watchdog` eval are the
alarm's new `cause` field and the mute state the pass writes beside the
board.
