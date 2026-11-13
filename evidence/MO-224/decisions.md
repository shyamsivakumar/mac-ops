# MO-224 decisions

Overnight runner spec part T13: the attended first night. Shyam watches one
hour with three small items. The night leaves three receipts and one morning
report, and no rule is broken.

Run id: `ticket:shyamsivakumar/mac-ops#192:a1`. Refs #192.

## What landed

- `coordinator/overnight/overnight`: a new `attend` subcommand in the same
  module as `intake`, `report` and `shift`.
  - It reads the board (`ticket list --fresh --json`) and takes the first
    small items the board shows: on the todo stage, in an allowed
    repository, of a type that is one small part, with nothing on them that
    waits for Shyam. The Ascend keys (`AUH`, `MCP`, `OPS`, `DBT`, `OMN`)
    are never taken, and the allow list already leaves those repositories
    out.
  - It arms the shift in the folder it is given: `run/armed`,
    `run/deadline` and `run/policy.json`. The policy records the allow
    list, the queue's slot cap (read only, never raised) and the verify
    level.
  - It observes each item with read-only commands only: the open pull
    request for the ticket, the checks on it (`gh pr checks`), the files it
    touches and the gate's verdict on it. It runs no merge, no push and no
    builder.
  - It writes one receipt per item, the shift log, and then the morning
    report through the same report code the report part uses.
  - The night holds the door until its window closes and then ends at the
    deadline. The shift log says so and the report repeats it.
  - `--dry-run` reads the board and writes nothing. `--root` points the
    night at another folder, so a rehearsal never touches the live
    records.
- `coordinator/overnight/README.md`: the contract names the new command,
  what it reads, what it writes and that it runs read-only commands only.
  The shift log row now says the log also states how the night ended.
- `evidence/MO-224/`: the proof runs. `attended-run.log`,
  `shift-log.md`, `policy.json`, `armed`, the three receipts
  (`MO-231.md`, `MO-234.md`, `MO-237.md`), the morning report
  (`morning-2026-11-13.md`) and `rule-check.log`.

Not touched: the merge, push and slot-cap rules, the Ascend rules, the
coordq queue, the tick job, the existing coordinator jobs, and every
existing test or check. No existing test or check was weakened, and no new
test file was added: the ticket says to prove by running the real command.

## The honest boundary of this part

T13 says "Shyam watches 1 hour with 3 small items". The parts that exist
today are intake (T3a), the morning report (T11) and the launchd job
(T12). The part that starts a builder for a board item is T5, and it is
still open (`#180`, `#181`). The attended night therefore observes and
records what the board really shows, and every receipt says what stopped
it. When T5 lands, the same command takes the item's builder path instead
of the observation path; the receipts, the shift log and the report do not
change shape.

The rehearsal ran the night for one minute rather than one hour, because
the part under test is the shape of the night (arm, three receipts, one
report, an end the report can check), not the length of the window. The
window is `--minutes`, and the proof run used `--minutes 1`.

## Decisions

### 1. The attended night observes, it does not build

- **The decision**: the command reads the board and observes each item
  with read-only commands. It starts no builder, merges nothing and pushes
  nothing.
- **The gap**: T13 asks for a night that does checked work. The builder
  path is T5 and is not built, and this ticket may not widen the rules that
  decide when a builder may start.
- **The reach**: the rehearsal proves the parts that exist, and it proves
  them on real data: real board tickets, a real pull request, real checks,
  the real gate verdict, a real report. Nothing in the night pretends to
  have run.
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

### 3. The night ends at the deadline, and the report reads that from the log

- **The decision**: the shift log states how the night ended
  (`ended: deadline`, `ended: all done`, `ended: STOP` or `ended: stall`),
  and the report reads that statement before it guesses.
- **The gap**: the report part (T11) read the shift log for the planned
  count, the full suite and a stall, but it had no way to read the shift's
  own statement of its end, so an attended night ended at its deadline
  would have said `UNVERIFIED`.
- **The reach**: the change is additive. A log without the statement
  behaves exactly as before, the `STOP` file still wins over everything,
  and the four words are the four the spec allows. No receipt, no count
  and no check changed.
- **Verdict**: sound.

### 4. One folder, one command, the existing installer

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
   --attended-by Shyam` printed the board (119 tickets), the three planned
   items and wrote nothing.
2. **The night runs and writes three receipts and one report.**
   `python3 coordinator/overnight/overnight attend --items 3 --minutes 1
   --attended-by Shyam --root ~/Code/coordinator/.overnight/attended-2026-11-13`
   wrote `run/armed`, `run/deadline`, `run/policy.json`,
   `run/shift-log.md`, three receipts and
   `receipts/morning-2026-11-13.md`, and exited 0
   (`evidence/MO-224/attended-run.log`,
   `evidence/MO-224/shift-log.md`, the receipts and
   `evidence/MO-224/morning-2026-11-13.md`).
3. **The report is rendered from the records.**
   The report says "How it ended: deadline. Items: 3 planned, 0 done,
   0 ready, 3 stuck, 0 parked", lists each stuck item with what stopped it
   and the next step, and writes "Full suite: UNVERIFIED (the shift log
   records no full suite run)" because no full suite ran
   (`evidence/MO-224/morning-2026-11-13.md`).
4. **No rule was broken.** The shift log holds only the read-only
   commands the night ran, the module holds no `gh pr merge`, no
   `git push` and no force push, and the shell history was last written
   before the window opened, so it holds no command from the night
   (`evidence/MO-224/rule-check.log`). The policy snapshot records the
   queue's slot cap as 6, read only, and the night never wrote it.
5. **No secret was written.** The receipts, the shift log, the policy and
   the report hold no token, key, cookie or `.env` value.
6. **Checks.** `python3 scripts/mac_ops_fast_check.py` and the full local
   check through `heavy` are recorded in the pull request body.

## The reviewer round

One in-session reviewer round read `git diff origin/main...HEAD` against
this ticket. Its findings and the probes for them are in
`evidence/MO-224/reviewer-fixes.log`.
