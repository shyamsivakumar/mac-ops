# MO-224 decisions

Overnight runner spec part T13: the attended first night. The night leaves
three receipts and one morning report, and no rule is broken.

Run id: `ticket:shyamsivakumar/mac-ops#192:a1`. Refs #192.

## What this ticket does and does not claim

The attended hour with Shyam **has not happened yet**. This ticket builds
the command that runs it (`overnight attend`), rehearses it end to end on
the real board, and proves the shape of the night: three receipts, one
morning report, an end the report can check, and no rule broken. The
human hour is still to be run by Shyam with `--run-by Shyam --wait`, and
it needs the builder path (T5, `#180` and `#181`) before the night does
work rather than observation. The records of the rehearsal say who ran
them ("the agent (rehearsal)"), because the command cannot know that a
person watched and the records must not claim it.

## What landed

- `coordinator/overnight/overnight`: a new `attend` subcommand in the same
  module as `intake`, `report` and `shift`.
  - It reads the board (`ticket list --fresh --json`) and takes the first
    small items the board shows: on the todo stage, in an allowed
    repository, and of a type that is one small part (`chore` or
    `standard`). A ticket Shyam holds is not in the board list at all (the
    ticket CLI keeps it out), so the night needs no second hold rule, and
    the Ascend keys are never taken.
  - It arms the shift in the folder it is given: `run/armed`,
    `run/deadline` and `run/policy.json`. The policy records the allow
    list, the queue's slot cap (read only, never raised) and the verify
    level.
  - It observes each item with read-only commands only: the open pull
    request for the ticket, the checks on it, the files it touches and the
    gate's verdict on it (a comment or a review). It runs no merge, no
    push and no builder.
  - It writes one receipt per item, the shift log, and then the morning
    report through the same report code the report part uses.
  - `--wait` holds the door until the window closes, and then the night
    ends at the deadline. Without it the night ends when the items are
    observed and says so.
  - `--dry-run` reads the board and writes nothing. Without `--root` the
    night writes to a dated folder under the runtime folder, so a
    rehearsal never mixes with the live receipts.
- `coordinator/overnight/overnight`: the report part reads the shift log's
  own statement of how the night ended, but only when the records support
  it. "all done" still needs every receipt to be done or parked,
  "deadline" still needs the clock to be past the deadline, "STOP" still
  needs the STOP file and "stall" still needs the stall in the log. A
  claim the records do not support is never repeated.
- `coordinator/overnight/README.md`: the contract names the new command,
  what it reads, what it writes, that it runs read-only commands only, and
  the two receipt fields the night writes (`Time used` and `Observed`).
- `evidence/MO-224/`: the proof runs. `attended-run.log`,
  `shift-log.md`, `policy.json`, `armed`, the three receipts
  (`MO-231.md`, `MO-234.md`, `MO-237.md`), the morning report
  (`morning-2026-11-13.md`) and `rule-check.log`.

Not touched: the merge, push and slot-cap rules, the Ascend rules, the
coordq queue, the tick job, the existing coordinator jobs, and every
existing test or check. No existing test or check was weakened, and no
new test file was added: the ticket says to prove by running the real
command.

## Decisions

### 1. The attended night observes, it does not build

- **The decision**: the command reads the board and observes each item
  with read-only commands. It starts no builder, merges nothing and pushes
  nothing.
- **The gap**: T13 asks for a night that does checked work. The builder
  path is T5 and is not built, and this ticket may not widen the rules
  that decide when a builder may start.
- **The reach**: the rehearsal proves the parts that exist, on real data:
  real board tickets, a real pull request, real checks, the real gate
  verdict, a real report. Nothing in the night pretends to have run.
- **Verdict**: sound, and the limit is named in the receipt of every item
  ("the tick part (T5) starts the builder for this item; the attended
  night only observes").

### 2. Every receipt says what the shift really saw

- **The decision**: a receipt holds the command it ran and its exit code,
  the gate's verdict as it stands (`PASS`, `FAIL` or `UNKNOWN`), the file
  count of the pull request, the state and why it stopped there.
- **The gap**: a model claim is not proof, and "the checks failed" is a
  different claim from "the pull request has no checks yet".
- **The reach**: `gh pr checks` exits 1 both when a check fails and when
  the pull request has no checks, so the night reads the output and says
  which one it was. A gate verdict that cannot be read is `UNKNOWN`, and
  the report's own rule turns an `UNKNOWN` gate into a stuck item.
- **Verdict**: sound. The proof run shows one item with a pull request and
  no checks yet, and two items with no pull request at all.

### 3. No builder ran, so the builder time is zero

- **The decision**: the receipt records `Time used: 0 min` and puts the
  time the shift spent looking in a separate field, `Observed`.
- **The gap**: the report's cost line reads the receipt's `Time used` as
  the builder time. Rounding an observation up to a minute and calling it
  builder time would be a claim the night cannot support.
- **The reach**: the cost line of the proof report reads "Builder time:
  0 min", which is true, and the seconds the shift spent looking are in
  the receipts.
- **Verdict**: sound.

### 4. The night ends at the deadline, and the report checks that claim

- **The decision**: the shift log states how the night ended
  (`ended: deadline`, `ended: all done`, `ended: STOP` or
  `ended: stall`), and the report reads that statement only when the
  records support it.
- **The gap**: the report part (T11) had no way to read the shift's own
  statement of its end. Letting the log's claim win on its own would let
  a shift log write "all done" over a stuck receipt, which is exactly
  the "never upgrades a claim into proof" rule the report keeps.
- **The reach**: the change is additive and checked. A log without the
  statement behaves exactly as before, the `STOP` file still wins over
  everything, and every one of the four words still needs its proof.
- **Verdict**: sound.

### 5. One folder, one command, the existing installer

- **The decision**: the command lives in the existing
  `coordinator/overnight/` module, so the existing installer installs it
  with the rest of the module and the installed copy and the checkout can
  never disagree.
- **The gap**: a second script would need a second installer rule and a
  second thing to keep in step.
- **The reach**: the module stays one module, the board stays the only
  list, and the shift keeps no queue of its own.
- **Verdict**: sound.

## Proof

1. **The command reads the board and picks three small items.**
   `python3 coordinator/overnight/overnight attend --dry-run --items 3
   --run-by "the agent (rehearsal)"` printed the board (118 tickets), the
   three planned items and wrote nothing.
2. **The night runs and writes three receipts and one report.**
   `python3 coordinator/overnight/overnight attend --items 3 --minutes 1
   --wait --run-by "the agent (rehearsal)" --root
   ~/Code/coordinator/.overnight/attended-2026-11-13` wrote
   `run/armed`, `run/deadline`, `run/policy.json`, `run/shift-log.md`,
   three receipts and `receipts/morning-2026-11-13.md`, and exited 0
   (`evidence/MO-224/attended-run.log`,
   `evidence/MO-224/shift-log.md`, the receipts and
   `evidence/MO-224/morning-2026-11-13.md`).
3. **The report is rendered from the records.**
   The report says "How it ended: deadline. Items: 3 planned, 0 done,
   0 ready, 3 stuck, 0 parked", lists each stuck item with what stopped it
   and the next step, says "Builder time: 0 min" and writes "Full suite:
   UNVERIFIED (the shift log records no full suite run)" because no full
   suite ran (`evidence/MO-224/morning-2026-11-13.md`).
4. **No rule was broken.** The shift log holds only the read-only
   commands the night ran, and the module holds no `gh pr merge`, no
   `git push` and no force push. The policy snapshot records the queue's
   slot cap as 6, read only, and the night never wrote that file. The
   shell history cannot prove this: a command an agent runs is not an
   interactive shell command and never reaches the history, so the check
   says that rather than claiming a proof it does not have
   (`evidence/MO-224/rule-check.log`).
5. **No secret was written.** The receipts, the shift log, the policy and
   the report hold no token, key, cookie or `.env` value.
6. **Checks.** `python3 scripts/mac_ops_fast_check.py` and the full local
   check through `heavy` are recorded in the pull request body.

## The reviewer round

One in-session reviewer round read `git diff origin/main...HEAD` against
this ticket and returned `VERDICT: FAIL`. Its findings and the probes
for them are in `evidence/MO-224/reviewer-fixes.log`. The findings that
changed the code:

- The night slept at most ten minutes and then logged `ended: deadline`.
  Now the wait is the whole window (`--wait`), it is never cut short, and
  the end of the night is read from the records.
- The report took the shift log's word for how the night ended. Now the
  log's statement is checked against the receipts, the clock, the STOP
  file and the stall, and a claim the records do not support is never
  repeated.
- The receipts claimed builder minutes that no builder used. Now the
  builder time is zero and the observation time is its own field.
- The records claimed a person watched. Now the records say who ran the
  night, and this ticket says plainly that the attended hour has not
  happened yet.
- The rule check used the age of the shell history as proof. Now it says
  that the history cannot prove it and names the proof that does.
- The selection had a second hold rule that searched titles for the word
  "hold", which would have skipped items whose titles hold another word
  and never saw a held ticket the board list keeps out. Now the night
  takes what the board shows, and the board list is the only hold rule.
- The night wrote into the live receipts folder when it was run without
  `--root`. Now it writes to a dated folder under the runtime folder
  unless it is told where to write.
