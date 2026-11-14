# MO-214 · Overnight T6: Evidence rule for done items

Ticket: https://github.com/shyamsivakumar/mac-ops/issues/182
Spec: overnight runner spec part T6 (spec issue #172, copy in
`~/Code/coordinator/specs/overnight-runner-spec.md`).

## What was built

One rule in the one module, `coordinator/overnight/overnight`, and the
commands that use it:

```
overnight close --repo shyamsivakumar/mac-ops --number 182 [--dry-run]
overnight check-head --repo shyamsivakumar/mac-ops --number 182
```

The rule: an item counts as done, and the coordinator closes its issue,
only when the receipt records a command, its exit code and a gate PASS on
the pull request. A model claim alone never counts.

The rule lives in one function, `evidence_holds(fields, checks)`, and three
readers use it:

| Reader | What it does with the rule |
| --- | --- |
| The receipt writer (`item_facts`) | A pull request that merged is `done` only when the receipt holds the evidence. Otherwise the receipt says `stuck` and names the missing record ("a check has no exit code, so it did not run", "the gate did not pass"). |
| The morning report (`classify`) | The report keeps the rule it already held. Its check now calls the same function, so the report and the receipt cannot drift apart. |
| `overnight close` | The close step. It reads the receipt of the ticket and closes the issue only when the receipt holds the evidence. |

## The decisions

1. **The rule is one function, read by three things.** The report
   already held the evidence rule: `classify` turned a `done` or `ready`
   receipt into `stuck` when a check had no exit code or the gate was not
   `PASS`. T6 needed the same rule in the receipt writer and in the close
   step, so the rule moved into `evidence_holds`, and `classify` and the
   report's "did not run" list both call it (`unrun_checks` takes the
   checks, not a receipt). The report's sentences are unchanged.
2. **A merged pull request is not automatically done.** Before this part
   the receipt writer set `done` when GitHub said the pull request merged.
   The merge is a fact, but the spec wants the command, the exit code and
   the gate PASS as well, so the receipt now checks them. A merge without
   them is `stuck`, and the receipt names the missing record.
3. **The receipt records a command that really ran.** A check counts as
   run only with its exit code, so the writer records the command it ran.
   A repository that publishes checks is read with `gh pr checks`. A
   repository that publishes none answers `gh pr checks` with exit 1 and
   "no checks reported", which is the absence of a check and not a
   failing one; recording that as a run would mark every mac-ops item
   stuck, and the reason would be false. So for those repositories the
   writer runs the new `overnight check-head`, which asks the head the
   question the gate asks (the agent check on the head, or the builder's
   `Builder check: PASS <head>` line in the pull request body) and has an
   exit code of its own. The receipt records that command and its exit.
   `check-head` exits 2 when the head cannot be read, which is a refusal,
   never a pass.
4. **The receipt's `Ticket` line names the issue, never the pull
   request.** The board numbers issues and GitHub numbers pull requests in
   different counters, and a `done` item is always a pull request item, so
   the old line (`Ticket: KEY (#<pull request>)`) would have pointed the
   close step at a pull request number. `issue_number(item)` returns
   `item["ticket"]` (the issue) and falls back to `item["number"]` for a
   ticket that has no pull request yet.
5. **The close step is a command, not a prompt.** "The coordinator closes
   its issue" is a rule about what may happen, so it is enforced where the
   close happens: `overnight close` reads the receipt, applies
   `evidence_holds`, and refuses with a non-zero exit when there is no
   receipt, or the receipt holds no check, a check with no exit code, a
   check that failed, a gate that did not pass, or a state that is not
   `done`. The issue stays open and the refusal names the missing record.
6. **The close finds the receipt and addresses the issue in it.** The
   receipt is found by the fields it holds (the repository and the issue
   number in its `Ticket` line), so the receipts folder stays the only
   record of what the shift did. There is no `--receipt` switch: a caller
   could otherwise hand the close a receipt for one ticket and a number
   for another, and the close would land on the wrong issue. The number
   the close runs is the one it found the receipt by, so the two cannot
   disagree.
7. **The gate's own close path is unchanged, and the close has no caller
   yet.** Today's coordinator close is the gate brief in
   `coordinator/bin/coordq` and `coordinator/bin/ticket`: after its own
   merge it runs `gh issue close`. That is the attended path, it is not
   the shift's, and this part does not touch it. `overnight close` is the
   shift's closer, it is proven below, and nothing calls it yet: wiring it
   into the shift's cycle is a later part. The behavior change this ticket
   states therefore holds today for the shift's own command and not yet
   for the gate's path.
8. **The close writes nothing else.** It runs one `gh issue close` and
   nothing else. It does not merge, does not push, does not write to the
   queue's config and does not touch the Ascend rules. `--dry-run` says
   what the close would run and closes nothing.

## The proof

The proof is the real command, on a receipt the module's own writer
produced. No new unit test files, per the ticket.

The receipt was written by `overnight` itself (`item_facts` +
`receipt_body` + `write_receipt`) for the merged mac-ops pull request #260,
whose ticket is issue #181:

```
$ python3 coordinator/overnight/overnight receipt ... # the writer, in process
# MO-213
- Item: Overnight T5b: Receipt per item state change
- Repo: shyamsivakumar/mac-ops
- Ticket: MO-213 (#181)
- State: done
- PR: https://github.com/shyamsivakumar/mac-ops/pull/260
- Checks: `.../coordinator/overnight/overnight check-head --repo shyamsivakumar/mac-ops --number 260` exit 0
- Gate: PASS
- Files: 4
- Time used: 50 min
- Stopped because: the pull request merged on GitHub
```

Run 1, the receipt that holds the evidence (a command, its exit code and a
gate PASS):

```
$ python3 coordinator/overnight/overnight close --repo shyamsivakumar/mac-ops --number 181 --root "$FIX" --dry-run
overnight: MO-213.md holds the evidence:
  state: done
  check: `.../coordinator/overnight/overnight check-head --repo shyamsivakumar/mac-ops --number 260` exit 0
  gate: PASS
overnight: the close would run:
  gh issue close 181 -R shyamsivakumar/mac-ops --comment Done. The receipt records the check command, its exit code and the gate PASS on https://github.com/shyamsivakumar/mac-ops/pull/260.
exit=0
```

Run 2, the same receipt with the exit code removed — a claim, not a run:

```
$ sed -i.bak 's/ exit 0$/ /' "$FIX/receipts/MO-213.md"
$ python3 coordinator/overnight/overnight close --repo shyamsivakumar/mac-ops --number 181 --root "$FIX" --dry-run
overnight: REFUSED: MO-213.md does not hold the evidence: a check has no exit code, so it did not run (`.../coordinator/overnight/overnight check-head --repo shyamsivakumar/mac-ops --number 260`)
overnight: the issue stays open.
exit=1
```

Run 3, no receipt for the issue at all:

```
$ python3 coordinator/overnight/overnight close --repo shyamsivakumar/mac-ops --number 1 --root "$FIX" --dry-run
overnight: REFUSED: no receipt for shyamsivakumar/mac-ops#1, so there is no evidence to close on
exit=1
```

The check the receipt records, run on its own against two real heads:

```
$ python3 coordinator/overnight/overnight check-head --repo shyamsivakumar/mac-ops --number 260
overnight: shyamsivakumar/mac-ops#260 carries a passing check
exit=0
```

The live board was read with the real command as well
(`overnight receipt --items 1 --dry-run`): a live pull request carried its
command, its exit code, its failing check and the gate verdict, and stayed
`stuck` because a check is failing.

`overnight check-head` runs the installed command (`OVERNIGHT_BIN`,
default `overnight`), so a receipt names the command that really ran. The
installer copies the module to `~/.local/bin`, so the installed command and
this checkout are the same file; during review the installed copy is the
previous release, which is why the runs above point the variable at the
checkout.

## Checks

- `python3 scripts/mac_ops_fast_check.py` → passed.
- `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` → passed
  (the full local check per `README.md`, "Check a task").
