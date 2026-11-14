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

The tick prompt in `coordinator/pi/bin/coord-tick` now tells the tick to
run `overnight receipt --repo <repo> --number <n>` for the item it acted
on. The command does the writing, so the model never writes a receipt.

## The decisions

1. **The command writes the receipt, not the model.** The ticket says the
   receipt is "built from threads and PRs, never from model claims". A
   prompt line that asks the model to write the receipt would put a model
   claim in every field. So the command reads the evidence itself: `gh pr
   checks` with its exit code, `gh pr view` for the files and the merge
   time, the gate thread for the verdict and the builder thread for the
   time. The model only names the item.
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
   The shift log names the change: `state stuck -> ready`.
7. **One receipt per item, named after the item.** The board key when the
   item has one (`MO-213.md`), the repository and the number when it does
   not. A pull request that belongs to a ticket is part of that ticket's
   record, so it does not get a receipt of its own.
8. **No new rules.** Nothing here touches merge, push, the queue's slot
   cap or the Ascend rules. Every command the receipt runs is read only:
   `gh pr checks`, `gh pr view`, `t3mcp call t3_thread_read`. No secret is
   read or written, and the receipt holds no token, key or `.env` value.

## What is not in this change

- `loop/tick.md` in the coordinator runtime folder (`~/Code/coordinator`)
  is not changed here: it is another repository, so it needs its own
  change. The tick prompt that mac-ops installs already tells the tick to
  write the receipt through the command, so the shift writes receipts
  without it.
- The shift's own cycle (`overnight shift`) still writes no receipt. The
  shift is a dry run until the tick part lands, and the tick writes the
  receipt of the item it acted on.
- No unit test file was added (the ticket asks for proof by running the
  real command).

## The proof

The real command, on the live board, in a scratch folder:

```
$ overnight receipt --items 3 --root $TMPDIR/mo213
Overnight receipts - 3 item(s)
  FFBT-24 | stuck | gate UNKNOWN | wrote
  FFBT-35 | stuck | gate UNKNOWN | wrote
  FFBT-34 | stuck | gate UNKNOWN | wrote
```

The three receipts and their fields are in `receipts/`. The second run
over the same items wrote nothing, because the state and the evidence did
not change. A third run against a pull request the gate has looked at
(`strategy-replay-workbench#987`) wrote the gate's own verdict:

```
  SRW-1077 | stuck | gate FAIL | wrote
```

with `- Checks: `gh pr checks 987 -R shyamsivakumar/strategy-replay-workbench` exit 0`,
`- Gate: FAIL`, `- Files: 3` and the builder's own time. The raw output is
in `receipts-run.txt`.
