# MO-210 · Overnight T3c: Intake orders the board

Run id: `ticket:shyamsivakumar/mac-ops#178:a1`
Part: T3c of the overnight runner spec (spec issue #172, revision 2).
Refs #178.

## What this part adds

One command in the same module, `coordinator/overnight/` in mac-ops,
installed by the existing installer (`install_coordinator.py`).

| Command | What it does |
| --- | --- |
| `overnight order --dry-run` | Orders the whole board, prints the full ordered list, and writes one summary line to `run/shift-log.md`. |

The intake command from T3a and the filter from T3b are unchanged in
what they do. The filter's rules moved into one shared function so the
order uses exactly the same drops, and the filter's own output is
unchanged.

There is no list file. The board is the list.

## The order, and where each rule comes from

| Group | Rule | Source |
| --- | --- | --- |
| Failing pull requests | `gh pr checks` on each open pull request. A check in a failed bucket or a failed state makes the pull request a failing one. A pull request with no checks at all is not a failure. | Spec section 7, step 3(a). |
| Pull requests with a gate PASS | The coordinator's dispatch receipts (`gate:<repo>#<pr>:<head>`) name the gate thread for a pull request head. The gate's own last message in the thread's latest run must end with `VERDICT: PASS` and carry `CHECK: PASS <head>`. | Spec section 7, step 3(b). |
| Ready tickets already split into 5-minute parts | The ticket's own text says it is a bounded slice: a light build slice, a light chore, or a part that says how many minutes it takes. | Spec section 7, step 3(c). |
| Ready tickets not yet split | Every other ready ticket. The shift splits it first, then adds the parts. | Spec section 7, step 3(d). |

Decisions worth naming:

- **A gate for an older head is not a verdict for the current head.**
  The receipt key carries the full head sha, so the order only reads the
  gate of the head the pull request has now. A pull request whose head
  moved is not called gate PASS.
- **The gate verdict is read from the gate, not guessed.** The last
  message of the thread's latest run must end with `VERDICT: PASS` and
  carry the line `CHECK: PASS <head>`. The queue dispatches a gate for
  the same head under the same request id, so one thread can hold two
  runs: only the latest run speaks. A thread that cannot be read, a
  latest run with no message, and a message that ends with anything
  else, are all no verdict, so the pull request falls into the in-flight
  list with the reason.
- **A mark is the marked form.** The board says "light build slice" and
  "light chore" for a slice it has already cut, and says "budget 3 to 5
  minutes" or "one 5-minute part" in the body. A ticket that says none of
  these is not split yet, so it is listed for splitting.
- **Ready means the board's stage is `todo`.** A ticket in another stage
  is not work for the night. It is listed as "not ready", not dropped.
- **A blocker is met when its issue is closed.** The open issue list of
  the repository says which issues are still open, and the closed issue
  list says which are done, so a blocker whose ticket has left the board
  is met rather than unknown. A blocker that cannot be checked counts as
  unmet, so the shift does not treat work as free it cannot prove.
- **A blocked item is not left out.** It stays in its group, is marked
  with the blocker that holds it, and is ordered after the items that
  are ready. The order never drops work; it says why work waits.
- **Inside a group the board decides.** Priority label first, then the
  items whose blockers are met, then the repository and the issue
  number, so the same board always gives the same list.

## The summary line

One line, written to `run/shift-log.md`:

```
planned 103 items | shyamsivakumar/catalouge 9 (failing 0, gate-pass 0, split 0, unsplit 9); ...
```

It carries the planned count and the counts per repository and per
state. The morning report already reads `planned N items` from the
shift log, so this line is the report's planned count and needs no
second source.

The line is a record, not work, so the command writes it in dry-run
mode too. It is the only file the command writes.

## Proof

The command is the real one. Nothing was mocked.

### 1. The real board, today

```sh
python3 coordinator/overnight/overnight order --dry-run
```

```
Overnight order - dry run (read only)
Board: 120 tickets
Allowed repositories: 15
Decisions log: /Users/shyamsivakumar/Code/coordinator/loop/decisions.md
Dropped by the filter: 13
Planned items: 103

Failing pull requests (4)
  1. shyamsivakumar/fantasy-football-toolkit#423 FFBT-24 ... - failing check: Vercel (FAILURE)
  2. shyamsivakumar/fantasy-football-toolkit#425 FFBT-35 ... - failing check: Vercel (FAILURE)
  3. shyamsivakumar/fantasy-football-toolkit#412 - ci: replace Woodpecker verification with local check - failing check: Vercel (FAILURE)
  4. shyamsivakumar/strategy-replay-workbench#993 - docs: define safe pooled test premium exclusion - failing check: srw/agent-check (FAILURE)

Pull requests with a gate PASS (1)
  5. shyamsivakumar/mac-ops#240 MO-224 MO-224 · Overnight T13: Attended first night (Refs #192) - gate PASS

Ready tickets already split into 5-minute parts (19)
  6. shyamsivakumar/strategy-replay-workbench#891 SRW-1054 ... - already a 5-minute part
  ...

Ready tickets not yet split (79)
  ...

Not work items: a pull request is open (27)
  ...

Not ready: the board stage is not todo (1)
  ...

Summary line written to /Users/shyamsivakumar/Code/coordinator/.overnight/run/shift-log.md
  planned 103 items | shyamsivakumar/catalouge 9 (failing 0, gate-pass 0, split 0, unsplit 9); shyamsivakumar/fantasy-football-toolkit 25 (failing 3, gate-pass 0, split 0, unsplit 22); shyamsivakumar/mac-ops 12 (failing 0, gate-pass 1, split 11, unsplit 0); shyamsivakumar/strategy-replay-workbench 57 (failing 1, gate-pass 0, split 8, unsplit 48)
No list file is written: the board is the list, and this run wrote one line of the shift log and nothing else.
```

### 2. The gate PASS is the gate's own verdict

The order called mac-ops #240 gate PASS. That verdict was read from the
gate thread the coordinator's dispatch receipts name, and the gate's own
last two lines are:

```
CHECK: PASS 631b09b15fe5c0c62410c4309c5e100daa8ebe39
VERDICT: PASS
```

The head in the receipt, the `CHECK:` line and the pull request's current
head are the same sha, so the verdict is for the head that is open now.

### 3. The filter still behaves

```sh
python3 coordinator/overnight/overnight filter --dry-run
```

```
Kept: 107
Dropped: 13
Ascend items kept: 0
```

The filter's rules moved into a shared function so the order drops
exactly what the filter drops. Its own output is unchanged.

### 4. No list file

The only file the run wrote was one line in `run/shift-log.md`. There is
no `punch-list.md` and no `next.md`, and the runtime folder holds no new
file.

### 5. The checks

```sh
python3 scripts/mac_ops_fast_check.py
~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py
```

Both pass. The result is in the pull request body.

## What did not change

- No merge, no push rule, no slot cap, no Ascend rule.
- No secret was read or written.
- The intake and filter commands keep their behaviour; the filter's
  rules are now one shared function, which both use.
- `install_coordinator.py` needed no change: the module is one file and
  the installer already installs it.

## The reviewer round

The in-session reviewer read the merged change and found real defects.
Each one is fixed in this follow-up, on top of the parts that landed
after the merge.

| Finding | Fix |
| --- | --- |
| The `Blocked by` section was never read: the pattern matched nothing, so the blocked-by steering was inert. | The section is read the way the coordinator's own reader reads it: a heading of any level or a `Blocked by:` line, with `<details>` skipped. 35 items on today's board now carry their blocker. |
| A blocker whose ticket had left the board was reported as unmet. | The closed issues of each repository are read, so a closed blocker is met and an unreadable one says "could not be read". |
| The gate verdict was taken from the last verdict-bearing message, so an earlier run's PASS survived a later run. | Only the latest run of the thread speaks, and a PASS has to carry `CHECK: PASS <head>`. A verdict for another head is no verdict. |
| The README and this file claimed the shift does not start work whose order it cannot prove, and that the tiebreak is the board's own order. | Both texts now say what the code does: a blocked item stays in its group and is marked, and the tiebreak is the repository and the issue number. |
| `gh pr checks` was described as exiting non-zero for a failed check; it exits 0 with `--json`. | The docstring says what gh does, and a read that fails for any other reason is a refusal for that one pull request, not a failure and not the end of the run. |
| A timeout in the checks aborted the whole order. | One unreadable pull request is now one unreadable pull request; the rest of the list and the summary line are still written. |
| `CANCELLED` counted as a failing check. | A cancelled check is inconclusive, so it is not a failure. |
| The summary line wrote a count that could not be checked as a zero. | The line counts every state (failing, gate PASS, split, unsplit, in flight, not ready) and writes `UNVERIFIED` for the counts the shift could not check. |
| A draft pull request was ordered as work, and a standalone pull request carried its own number as a ticket number. | A draft is in flight with the reason "draft pull request", and a pull request that names no ticket carries no ticket number. |

## Open points

- The gate thread is found through the coordinator's dispatch receipts.
  A gate that never got a receipt (a manual gate) is not called gate
  PASS, so the pull request falls into the in-flight list with the
  reason. That is the fail-closed direction.
- The split mark reads the ticket's own text. A ticket that says nothing
  about its size is listed for splitting. Shyam can move a ticket
  between the two groups by saying so in the ticket, which is the same
  steering the board's labels give.
