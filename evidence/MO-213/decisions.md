# MO-213 · Overnight T5b: Receipt per item state change

Ticket: https://github.com/shyamsivakumar/mac-ops/issues/181
Spec: overnight runner spec part T5b (spec issue #172, copy in
`~/Code/coordinator/specs/overnight-runner-spec.md`).

## What was built

One command in the one module, `coordinator/overnight/overnight`:

```
overnight receipt --repo <repo> --number <n>    # one item
overnight receipt --items 3                     # the first N of the shift's order
overnight receipt --items 3 --dry-run           # print it, write nothing
```

It reads the board with the same helpers the rest of the module uses
(`read_board`, `read_bodies`, `filter_issues`, `collect_items`), so the
receipts are about the items of the shift's own order and the shift keeps
no second queue. It writes `receipts/<item>.md` and one line per receipt in
`run/shift-log.md`.

A cycle writes the receipts. A real `overnight shift` cycle reads the
board under the policy snapshot, writes the receipt of every item it sees
and writes one line per receipt to the shift log. It still starts no
builder and works no board item: that part of the spec (T5) is not built,
so the cycle says so instead of pretending it works.

## The decisions

1. **The command writes the receipt, not the model.** The ticket says the
   receipt is "built from threads and PRs, never from model claims". A
   prompt line that asks the model to write the receipt would put a model
   claim in every field. So the command reads the evidence itself: `gh pr
   checks` with its exit code, `gh pr view` for the files and the merge
   time, the gate thread for the verdict and the builder thread for the
   time. No agent writes a receipt by hand.
2. **The fields are the report's fields.** The morning report already
   parses `- Key: value` lines (`parse_receipt`) and requires a check with
   a command and an exit code plus a gate `PASS` before an item counts as
   done or ready (`classify`). The receipt writes exactly those fields, so
   the report reads the new receipts with no change to the report. A
   receipt with a check that did not run leaves the item stuck, which is
   the rule the report already held.
3. **The state is derived, not chosen.** `done` when GitHub says the pull
   request merged, `ready` when the gate passed and the shift has no merge
   right, `stuck` for everything else. A failing check leaves the item
   stuck whatever the gate says. The state is never `ready` without a
   passing check and a gate `PASS`, so the report's own rule and the
   receipt agree.
4. **The gate verdict has two sources and one answer.** The gate thread of
   that head (the queue's own dispatch receipt `gate:<repo>#<pr>:<head>`)
   is read first, because a gate for an older head is not a verdict for
   this one. When there is no gate thread the pull request's own review
   and comments are read. When neither can be read the receipt says
   `UNKNOWN`, and `UNKNOWN` is never a pass.
5. **The builder time is measured.** The minutes between the builder
   thread's own `createdAt` and `updatedAt`. The receipt names the thread
   it measured, so the number is never anonymous. A night that ran no
   builder says `0 min`.
6. **The receipt is rewritten on a state change, not on every cycle.** The
   rendered receipt is compared with the file, without the `- Observed:`
   line (it changes every cycle by its own nature). The same receipt is
   left alone; a changed state or a changed piece of evidence is written.
   The shift log names the change: `state ready -> stuck`.
7. **The receipt is written to a scratch name and moved into place**, so a
   run that dies mid-write never leaves a half receipt for the morning
   report to read.
8. **One receipt per item, named after the item.** The board key when the
   item has one (`MO-213.md`), the repository and the number when it does
   not. A pull request that belongs to a ticket is part of that ticket's
   record, so it does not get a receipt of its own. A ticket with two open
   pull requests has one receipt: the one written last is the one on
   disk, and the shift log names every write, so nothing is silent.
9. **No new rules.** Nothing here touches merge, push, the queue's slot
   cap or the Ascend rules. Every command the receipt runs is read only:
   `gh pr checks`, `gh pr view`, `t3mcp call t3_thread_read`. No secret is
   read or written, and the receipt holds no token, key or `.env` value.

## What the gate found, and what was done

The first gate returned FAIL on the branch `bb05ce0`.

- **Major, the branch conflicted with `main`.** Main had moved: the
  overnight runner now runs 24x7 and the pi tick is retired (mac-ops
  #246). The branch merges `origin/main` now, so the push is a plain
  fast-forward of the merge commit and no force push is needed. The only
  conflict was the receipt row of the README's file table: main renamed
  the writer from "Tick" to "A cycle", so the row reads "A cycle
  (`overnight receipt`)".
- **The pi tick is retired, so the tick prompt is the wrong place.** The
  first branch asked the pi tick's prompt to write the receipt. That
  launcher no longer runs. The receipts are written by the shift's cycle
  instead, and the change to `coordinator/pi/bin/coord-tick` is gone.
- **Minor, the previous state was read after the write.** It always held
  the new state, so the shift log never showed a change. It is read
  before the write now.
- **Minor, `--number` without `--repo` was ignored** and the command then
  wrote the receipt of every item. It refuses with a clear line now.
- **Minor, the pull request body claimed a gate FAIL that the evidence did
  not show.** The evidence file now holds that run: the receipt for
  `strategy-replay-workbench#987` carries `Gate: FAIL`, read from the
  gate's own thread.

## What is not in this change

- The shift still starts no builder and works no board item (spec part T5
  is not built). A cycle writes the receipts and says so.
- The launchd job still runs the shift in dry-run mode, so it writes no
  receipt until the shift's board work lands. That is main's rule, not
  this ticket's.
- No unit test file was added (the ticket asks for proof by running the
  real command).

## The proof

The real command, on the live board, in a scratch folder (the task
TMPDIR, so the live records were never touched):

```
$ overnight receipt --items 3 --root $TMPDIR/mo213-proof3
Overnight receipts - 3 item(s)
  FFBT-24 | stuck | gate UNKNOWN | wrote
  FFBT-35 | stuck | gate UNKNOWN | wrote
  FFBT-34 | stuck | gate UNKNOWN | wrote
```

The second run over the same items wrote nothing (`unchanged`), because
the state and the evidence did not change. A receipt whose state was
changed by hand showed the change in the output and in the shift log
(`state ready -> stuck`). A pull request the gate had looked at
(`strategy-replay-workbench#987`) got the gate's own `FAIL` verdict and the
builder's own time. The full run is in `receipts-run.txt`.
