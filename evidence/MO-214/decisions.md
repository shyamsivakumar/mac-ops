# MO-214 · Overnight T6: Evidence rule for done items

Ticket: https://github.com/shyamsivakumar/mac-ops/issues/182
Spec: overnight runner spec part T6 (spec issue #172, copy in
`~/Code/coordinator/specs/overnight-runner-spec.md`).

## What was built

One rule in the one module, `coordinator/overnight/overnight`, and one
command that uses it:

```
overnight close --repo shyamsivakumar/mac-ops --number 182
overnight close --repo shyamsivakumar/mac-ops --number 182 --dry-run
```

The rule: an item counts as done, and the coordinator closes its issue,
only when the receipt records a command, its exit code and a gate PASS on
the pull request. A model claim alone never counts.

The rule lives in one function, `evidence_holds(fields, checks)`, and three
readers use it:

| Reader | What it does with the rule |
| --- | --- |
| The receipt writer (`item_facts`) | A pull request that merged is `done` only when the receipt holds the evidence. Otherwise the receipt says `stuck` and names the missing record ("a check has no exit code, so it did not run", "the gate did not pass"). |
| The morning report (`classify`) | The report keeps the rule it already held. The check that classified a receipt was rewritten to call the same function, so the report and the receipt cannot drift apart. |
| `overnight close` | The close step. It reads the receipt of the ticket and closes the issue only when the receipt holds the evidence. |

## The decisions

1. **The rule is one function, read by three things.** The report
   already held the evidence rule: `classify` turned a `done` or `ready`
   receipt into `stuck` when a check had no exit code or the gate was not
   `PASS`. T6 needed the same rule in the receipt writer and in the close
   step. Writing it a third time would let the three drift, so the rule
   moved into `evidence_holds` and `classify` now calls it. The report's
   own messages are unchanged, because the new function returns the same
   reasons.
2. **A merged pull request is not automatically done.** Before this
   part, the receipt writer set `done` when GitHub said the pull request
   merged. The merge is a fact, but the spec's rule asks for the command,
   the exit code and the gate PASS as well, so the receipt now checks
   them. A merge without the evidence is `stuck`, and the receipt says
   which record is missing. The report already read such a receipt as
   stuck, so this change makes the receipt honest rather than changing
   what the report counts.
3. **The close step is a command, not a prompt.** "The coordinator closes
   its issue" is a rule about what may happen, so it is enforced where
   the close happens: `overnight close` reads the receipt, applies
   `evidence_holds`, and refuses with a non-zero exit when the receipt
   holds no check, a check with no exit code, a check that failed, a gate
   that did not pass, or a state that is not `done`. The issue stays open
   and the refusal names the record that is missing. A prompt line would
   have been a claim, and the spec says a claim never counts.
4. **The close step finds the receipt by what the receipt holds.** The
   receipts are named after the board key, so the ticket is found by the
   fields inside the receipt: the repository and the issue number in its
   `Ticket` line. The folder of receipts stays the only record of what
   the shift did, and the shift keeps no second list.
5. **The close step writes nothing else.** It runs one command, the
   `gh issue close`, and nothing else. It does not merge, does not push,
   does not write to the queue's config and does not touch the Ascend
   rules. `--dry-run` says what the close would run and closes nothing.
6. **The gate's own close path is left alone.** The gate brief in
   `coordinator/bin/coordq` and `coordinator/bin/ticket` tells the
   interactive gate to close the ticket after its own merge. That is
   today's coordinator path, not the shift's, and changing it would change
   today's close behavior for every ticket, which this ticket forbids
   ("no change to merge, push, slot cap or Ascend rules"). The shift's
   closer is the command above, and it is the shift that has receipts.

## The proof

The proof is the real command, run twice on two receipts of a fixture
folder. No new unit test files were written, per the ticket.

Run 1, the receipt that holds the evidence (command, exit code, gate
PASS):

```
$ python3 coordinator/overnight/overnight close --repo shyamsivakumar/mac-ops --number 182 --root "$FIX" --dry-run
overnight: MO-214.md holds the evidence:
  state: done
  check: `python3 scripts/mac_ops_fast_check.py` exit 0
  gate: PASS
overnight: the close would run:
  gh issue close 182 -R shyamsivakumar/mac-ops --comment Done. The receipt records the check command, its exit code and the gate PASS on https://github.com/shyamsivakumar/mac-ops/pull/999.
exit=0
```

Run 2, the receipt with a claim and no exit code:

```
$ python3 coordinator/overnight/overnight close --repo shyamsivakumar/mac-ops --number 183 --root "$FIX" --dry-run
overnight: REFUSED: MO-215.md does not hold the evidence: a check has no exit code, so it did not run (`python3 scripts/mac_ops_fast_check.py`)
overnight: the issue stays open.
exit=1
```

The real board was read as well, with the real command
(`overnight receipt --items 1 --dry-run`): the receipt of a live pull
request carried its command, its exit code, its failing check and the
gate verdict, and it stayed `stuck` because a check is failing.

## Checks

- `python3 scripts/mac_ops_fast_check.py` → passed.
- `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` → passed
  (the full local check per `README.md`, "Check a task").

## The review round

The gate read the merged head and failed it. The fixes below are the
review's findings, applied on top of `origin/main` (which already holds
the first version of this part, plus the redaction and the shift's work
parts).

1. **The proof was circular.** The check a receipt recorded could pass on
   the builder's own line in the pull request body, `Builder check: PASS
   <head>`. That line is a claim about the check, not the check, and the
   spec says a claim never counts. The receipt now records
   `overnight check-head --repo <repo> --number <n>`, and that command
   reads only the checks that ran on the head: exit 0 when a check ran and
   passed, exit 1 when a check ran and did not pass, exit 2 when no check
   ran on the head or the head could not be read. A repository that
   publishes no checks (CI is agent checks only, as in mac-ops) therefore
   has no evidence on its heads: its items stay open and the receipt says
   why. That is the honest answer, not a rule that blocks everything: the
   shift has no check of its own to show, so it shows nothing.
2. **The close could land on a pull request.** The receipt's `Ticket`
   line held `item["number"]`, which for a pull request item is the pull
   request number, and the fallback in the issue lookup returned the same
   number when a pull request had no linked ticket. The receipt now holds
   the issue number (`issue_number()`), a pull request with no linked
   ticket holds no issue number at all, and the close addresses the number
   it found the receipt by.
3. **The close could be pointed at the wrong issue.** The `--receipt`
   switch let a caller hand the close one ticket's receipt and another
   ticket's number. The switch is gone: the close finds the receipt by
   the repository and the issue number in it, and closes that number.
4. **Two copies of the "check did not run" test.** `unrun_checks()` takes
   the checks now, and `evidence_holds()` and the report both call it.
5. **A comment explained a constant.** The constant's purpose moved into
   the module's own description, and the comment is gone.
6. **The checks were read twice.** The receipt writer runs one command,
   `overnight check-head`, and that command reads the head's checks once.

The gate also found the branch sat on the wrong base, so `origin/main` is
merged in and the diff against it is this part's change alone.

### The proof after the fixes

The receipt is written by the module's own writer for a real pull
request, and the close runs on it:

```
$ python3 coordinator/overnight/overnight check-head --repo shyamsivakumar/strategy-replay-workbench --number 1044
overnight: shyamsivakumar/strategy-replay-workbench#1044 carries a check that ran and passed
exit=0

$ python3 coordinator/overnight/overnight check-head --repo shyamsivakumar/mac-ops --number 260
overnight: REFUSED: no check ran on the head of shyamsivakumar/mac-ops#260, so the check is unknown
exit=2
```

The second run is the honest answer for a repository that publishes no
checks: the head carries no check that ran, so a receipt for it cannot
hold the evidence and the close refuses.
