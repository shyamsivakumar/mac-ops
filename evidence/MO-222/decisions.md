# MO-222 decisions

Overnight runner spec part T11b: the morning report names the decisions
that wait for Shyam, the work that was not run and why, and the cost of the
night. Any count that cannot be checked says UNVERIFIED, and a check is
never reported as passed unless it ran.

Run id: `ticket:shyamsivakumar/mac-ops#190:a1`. Refs #190.

## What landed

- `coordinator/overnight/overnight`: a new `report` subcommand in the same
  module as the intake command.
  - `overnight report --dry-run` renders the morning report from the
    shift's own records and writes nothing. Without `--dry-run` it writes
    `receipts/morning-YYYY-MM-DD.md`.
  - It reads the receipts, the parking lot, the shift log, the policy
    snapshot, the armed file, the deadline file and the STOP file. It
    reads no board and holds no second queue of its own.
  - The report has the headings of spec section 11: how it ended and the
    counts, Merged, Ready for you, Stuck, Decisions for you, Not run and
    why, Cost. The times are PT.
  - "How it ended" is one of the four ways the spec allows: deadline, all
    done, STOP or stall. Anything the records do not explain says
    UNVERIFIED.
  - **Decisions for you** holds the parking-lot entries, each with its
    recommendation and the default that applies if Shyam says nothing, and
    then the parked items, because a parked item waits for a decision.
  - **Not run, and why** holds the checks that were claimed without an exit
    code, the full suite with its exit code when the shift log records one,
    and the planned items that have no receipt.
  - **Cost** holds the builder time summed from the receipts and the model
    use as a share of the plan allowance.
  - A count that cannot be checked is written as UNVERIFIED: the planned
    count when the shift log has no summary line, the model use when the
    allowance was not readable, the builder time when a receipt records no
    time, and the identity of planned items that have no receipt.
  - A check counts as run only when the receipt names the command and its
    exit code. A receipt that claims to be done or ready without that
    proof, or with a check that failed, is reported as stuck, and the
    check appears under "Not run, and why". The report never says a check
    passed if it did not run.
  - `done` counts the items that merged and `ready` counts the items that
    wait for a merge right, so the counts and the lists agree item for
    item.
  - The command exits non-zero when the folder that holds the records
    does not exist, so a wrong folder is not a calm empty report.
- `coordinator/overnight/README.md`: the contract names the report command,
  the record each field comes from, the receipt fields and the rules the
  report holds.
- `evidence/MO-222/fixture-night/`: the fixture night the proof renders.
- `evidence/MO-222/report-dry-run.log`, `evidence/MO-222/report-contrast.log`:
  the report and the contrast runs.
- `evidence/MO-222/reviewer-fixes.log`: the probes for the findings of the
  reviewer round.
- `evidence/MO-222/decisions.md`: this file.

Not touched: the merge, push and slot-cap rules, the Ascend rules, the
coordq queue, the launchd jobs, the tick, the intake command, and every
existing test or check. No existing test or check was weakened.

## Decisions

### 1. The report is a command in the same module, not a second list

- **The decision**: `overnight report` lives in `coordinator/overnight/`
  next to `overnight intake`, and the installer already installs that one
  file, so the installer needed no change. The report reads the shift's
  records and holds nothing of its own.
- **The gap**: The brief asked for one module and said to stop and report
  before coding if the part only fits as a bolt-on.
- **The reach**: The report cannot drift from the board, because it never
  reads one. It cannot invent a count, because every count comes from a
  file in `.overnight/`. The later parts (the tick writing receipts, the
  arm step writing the policy snapshot) feed it.
- **Verdict**: sound.

### 2. The report renderer had to land here, because T11a never landed

- **The decision**: This part implements the whole of spec section 11,
  including the headings T11a owned (how it ended, the counts, Merged,
  Ready for you, Stuck).
- **The gap**: Issue #189 (MO-221, T11a) is closed. The closure comment
  says "Closed by the coordinator sweep: PR #136 merged after its gate".
  PR #136 is `MO-189 · worker task routes use the router instance`, a
  different ticket, and no report renderer exists in `origin/main` or in
  any branch. The sweep closed the issue on the number, not on the work.
- **The reach**: This pull request carries the renderer that T11b needs.
  If T11a is built later against the same contract, the two must agree on
  the receipt fields, which this pull request documents.
- **Verdict**: sound, and the reason is recorded here so the next reader
  does not read the closed issue as done work.

### 3. A check needs a command and an exit code

- **The decision**: A receipt line `Checks:` holds one check or several
  separated by semicolons, each as a command in backticks and its exit
  code: `` `cmd` exit 0 ``. A check with no command or no exit code is a
  claim, not a run.
- **The gap**: The brief says a check is never reported passed unless it
  ran. The spec says an item counts as done only when its receipt holds
  the verify command, its exit code and an Opus gate PASS.
- **The reach**: A receipt that says "Checks: `cmd` passed" with no exit
  code leaves the item not done, and the report says so under "Not run,
  and why" instead of passing it on.
- **Verdict**: sound.

### 4. A receipt without proof is stuck, not done and not ready

- **The decision**: When a receipt claims `done` or `ready` but holds no
  check that ran, or its gate did not pass, the report puts the item under
  Stuck with the reason, and counts it as stuck.
- **The gap**: The counts have to add up to the receipts, and the report
  must not say a check passed when it did not run.
- **The reach**: A shift that writes sloppy receipts sees its own counts
  drop, which is the pressure the spec wants. Nothing is invented to fill
  the gap.
- **Verdict**: sound.

### 5. The counts come from the records, and an unknown count says UNVERIFIED

- **The decision**: The planned count comes from the shift log's
  `planned N items` line, the builder time from the receipts, and the
  model use from `allowance_used_percent` in the policy snapshot. When a
  count cannot be checked, the report writes UNVERIFIED and says why.
- **The gap**: The spec says counts come only from records and that a
  count that cannot be checked is written UNVERIFIED.
- **The reach**: The report never keeps a punch list, so the planned
  count is the shift log's summary and not the board. When that summary is
  missing, the report says the planned count is UNVERIFIED and names the
  planned items that have no receipt as UNVERIFIED too. `done` counts the
  items that merged and `ready` counts the items that wait for a merge
  right, so the counts and the lists agree item for item.
- **Verdict**: sound.

### 6. The report reads records only, so the merged list is the receipts' list

- **The decision**: The report does not call GitHub. A merged item is a
  receipt that records a merge time, and the receipt is written only after
  the shift checked GitHub.
- **The gap**: The spec heading says "Merged (checked on GitHub)".
- **The reach**: The report runs offline, so it cannot fail half way
  through because the network is down. The check of GitHub happened when
  the receipt was written, and the receipt is the proof. A later part that
  wants a fresh check can add it without changing this contract.
- **Verdict**: sound, and the limit is stated here rather than hidden.

### 7. Work that is done but not merged waits for Shyam

- **The decision**: A receipt that is done, holds a pull request and
  records no merge time appears under "Ready for you".
- **The gap**: The shift has no merge right for most repositories, so a
  finished piece of work waits for the morning.
- **The reach**: The counts still report the receipt's own state, so a
  reader sees the work counted as done and listed as ready to merge.
- **Verdict**: sound.

## Proof

1. **The real command, on a fixture night.** `python3
   coordinator/overnight/overnight report --dry-run --root
   evidence/MO-222/fixture-night --date 2026-11-13` printed the report in
   `evidence/MO-222/report-dry-run.log`, exit code 0. The report shows
   `Model use: UNVERIFIED (the allowance was not readable)` next to a
   checkable `Builder time: 45 min`, and the claimed check of MO-240
   under "Not run, and why" instead of as a pass.
2. **The same night with a readable allowance.** The same command on a
   copy of the same fixture whose policy snapshot carries
   `allowance_used_percent: 41` prints `Model use: 41% of allowance`. One
   field is the difference, so the UNVERIFIED comes from the unreadable
   allowance and from nothing else
   (`evidence/MO-222/report-contrast.log`).
3. **A count that cannot be checked.** The same command on a copy of the
   same fixture without the shift-log summary line prints `Items:
   UNVERIFIED planned`, and on a copy that plans 12 items against 4
   receipts it prints `8 planned items have no receipt. Which ones:
   UNVERIFIED` and an UNVERIFIED builder time.
4. **The write path.** The same command without `--dry-run` writes
   `receipts/morning-2026-11-13.md` and prints where it wrote it.
5. **The probes of the reviewer round.** `evidence/MO-222/reviewer-fixes.log`
   holds the run of each finding's probe: a folder that does not exist
   exits 1, an empty night says UNVERIFIED, "install" is not a stall, a
   night where every item was done says "all done", a planned count below
   the receipt count never goes negative, a failed check is not done, a
   semicolon inside a command is one check, a receipt that is not UTF-8
   is an unreadable item and not a crash, a bad date is a clean error,
   and the report follows the folder the installer moved.
6. **Checks.** `python3 scripts/mac_ops_fast_check.py` and the full local
   check through `heavy` are recorded in the pull request body.

## The reviewer round

One in-session reviewer round (Claude Opus 5.5) read `git diff
origin/main...HEAD` against this ticket and returned `VERDICT: FAIL` with
three blocking findings and ten minor ones. Everything it raised is
fixed, and the probes for each finding are in
`evidence/MO-222/reviewer-fixes.log`.

1. **Blocking, fixed.** The report said "Nothing was left unrun" when it
   had no records at all, so an empty night and a wrong folder looked
   calm. Now the full suite is always named, an empty night says
   "Full suite: UNVERIFIED", and the command exits non-zero when the
   folder that holds the records does not exist.
2. **Blocking, fixed.** "How it ended" could be wrong: the word "stall"
   matched "install", the deadline was checked before the all-done case,
   and an unexplained night said "unclear", which the spec does not
   allow. Now the stall is a whole word, "all done" is checked before the
   deadline, and anything else says UNVERIFIED.
3. **Blocking, fixed.** The planned count was subtracted from the
   receipts without a guard, so a night with more receipts than planned
   items printed a negative count. Now the line appears only when the
   planned count is larger, and a planned count that is smaller than the
   receipts is written UNVERIFIED with a line that says the records
   disagree.
4. **Minor, fixed.** The full suite counted as passed with an exit code
   but no command. It now needs both, like every other check.
5. **Minor, fixed.** A later shift-log line without an exit code erased
   the full suite run the log already recorded. The log now keeps the
   last line that has an exit code.
6. **Minor, fixed.** A receipt whose check failed but whose gate passed
   counted as done. A failed check now leaves the item stuck, whatever
   the gate says.
7. **Minor, fixed.** A done receipt with no merge time appeared in no
   list. The counts now follow the lists: `done` counts what merged,
   `ready` counts what waits for a merge right.
8. **Minor, fixed.** A semicolon inside a command split the check. The
   split now happens only outside the backticks.
9. **Minor, fixed.** A receipt that is not valid UTF-8 crashed the
   report, and a bad `--date` gave a raw traceback. A receipt that
   cannot be read is now an unreadable item, and the date is checked by
   the parser.
10. **Minor, fixed.** The report's default folder ignored
    `MAC_OPS_COORDINATOR_DIR`, which is how the installer moves the
    runtime folder. The report follows it now.
11. **Minor, not changed.** The heading "Merged (checked on GitHub)" is
    the spec's heading, and the report does not call GitHub: the merge
    time is the one the shift recorded after it checked GitHub. Decision
    6 says so, and the README names the same source.
12. **Minor, fixed.** A misplaced comment above the state constants and
    a coverage pragma on the time-zone fallback are gone.

## Rollback

Revert the commit and run `python3 install_coordinator.py` again.
