# MO-766 runs

All runs use a temp `COORDQ_DIR`, `COORD_JOURNAL_DIR` and `HOME`. Nothing was opened for real: every `ticket open` below has `--dry-run`, and SRW #1579 was only read with `gh pr view` and `gh pr diff`.

## Ticket proof command

Before, in a clean checkout of `origin/main` (`51a34824`):

```
FileNotFoundError: [Errno 2] No such file or directory: 'evidence/MO-766/example-ticket.md'
exit 1
```

After, on the branch (the ticket's command, repo mac-ops):

```
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1190", "title": "MO-1190 · zz", "labels": ["stage:hold", "priority:3", "type:standard"], "dryRun": true}
exit 0
```

`grep -c 'ticket open' .agents/skills/factory-cut/SKILL.md` prints 8.

## Worked example: SRW #1579 cut by the procedure

SRW #1579 (P50, head `cd544b89`, read-only) changes 10 files. Counted the way `ticket open` counts, it has 798 code lines in 4 code files: `thala_executor/order_identity.cjs` +591, `thala_v2_executor.js` +137, `bot2/trade_machine.js` +46, `alpaca_paper_execution.js` +24. The proof script `scripts/srw1458_sell_reservation_proof.cjs` (+857), `fixtures/srw1458/*` and `evidence/SRW-1458/*` do not count.

Following the procedure, the file of 591 lines is cut by function group (the cut points are the function boundaries in the diff), then the executor wiring, then the bots. Eight tickets, a linear chain, each at most 137 code lines and 2 code files. The bodies are in `evidence/MO-766/srw1579-cut/`.

| Ticket | Code lines | Code files | Blocked by |
| --- | --- | --- | --- |
| 01 identity and position helpers, their exports | 110 | 1 | nothing |
| 02 capacity, invariants, read | 73 | 1 | 01 |
| 03 book plumbing | 126 | 1 | 02 |
| 04 prove, allocate, reserve, markUnknown | 104 | 1 | 03 |
| 05 recordExecution, observeOrder, reconcile, release | 117 | 1 | 04 |
| 06 book reads and close | 61 | 1 | 05 |
| 07 executor wiring | 137 | 1 | 06 |
| 08 bots, ledger hooks, proof script, fixtures | 70 | 2 | 07 |

The sizes are the added lines in the matching diff ranges of `gh pr diff 1579`, with the 11 export lines split across tickets 01 (9 names), 02 (1) and 03 (1), so each helper is exported by the ticket that adds it. The proofs are checked in the next section, one ticket at a time.

## Each proof passes at its own step

Gate finding: ticket 1's proof imported four helpers while the exports sat in ticket 6, so a builder following ticket 1 got `undefined`. Fixed by moving each export into the ticket that adds the helper (01 exports its 9 names, 02 `readSellReservation`, 03 `createSellReservationBook`) and by the new rule in `.agents/skills/factory-cut/SKILL.md`.

Check: a read-only clone of SRW in the scratchpad (push URL disabled, nothing pushed), scratch branch `scratch-cut` from SRW #1579's base `02d5a019`. Tickets 01 to 06 are the line ranges of `thala_executor/order_identity.cjs` at head `cd544b89` plus the export lines above, tickets 07 and 08 are the `git diff 02d5a019 cd544b89` of their files. Each proof is the `Proof command:` line of the ticket body, run at the step before the ticket (must be red) and at the step after it (must be green). The same checkout then differs from `cd544b89` only by `evidence/SRW-1458/*`.

| Ticket | Before the ticket (HEAD) | After the ticket (HEAD) |
| --- | --- | --- |
| 01 | `undefined,undefined,undefined,undefined` (`02d5a019`) | `function,function,function,function` (`d9092752`) |
| 02 | `undefined` (`d9092752`) | `function` (`1bec1db3`) |
| 03 | `TypeError: m.createSellReservationBook is not a function` (`1bec1db3`) | `string,string,string,string,number` (`03234630`) |
| 04 | `undefined,undefined,undefined,undefined` (`03234630`) | `function,function,function,function` (`36960f42`) |
| 05 | `undefined,undefined,undefined,undefined` (`36960f42`) | `function,function,function,function` (`151db2ef`) |
| 06 | `undefined,undefined,undefined,undefined` (`151db2ef`) | `function,function,function,function` (`7edda047`) |
| 07 | `0` (`7edda047`) | `3` (`07e4e37e`) |
| 08 | `Error: Cannot find module '.../scripts/srw1458_sell_reservation_proof.cjs'` (`07e4e37e`) | `PASS: 7 cases, input f520349d381f, expected dd8e10b1fe65` (`801e793c`) |

Every proof passes at its own step, and ticket 01's proof fails before ticket 01's change.

Dry run of each body, repo `shyamsivakumar/strategy-replay-workbench`, labels `stage:hold,priority:3,type:standard`:

```
exit 0 01-identity-and-position-helpers.md   {"key": "SRW-1407", ..., "dryRun": true}
exit 0 02-capacity-invariants-read.md        {"key": "SRW-1407", ..., "dryRun": true}
exit 0 03-book-plumbing.md                   {"key": "SRW-1407", ..., "dryRun": true}
exit 0 04-book-prove-allocate-reserve.md     {"key": "SRW-1407", ..., "dryRun": true}
exit 0 05-book-record-observe-reconcile.md   {"key": "SRW-1407", ..., "dryRun": true}
exit 0 06-book-reads-and-exports.md          {"key": "SRW-1407", ..., "dryRun": true}
exit 0 07-executor-wiring.md                 {"key": "SRW-1407", ..., "dryRun": true}
exit 0 08-bots-ledger-and-proof.md           {"key": "SRW-1407", ..., "dryRun": true}
```

The key is the same on every line because nothing was created; a real run mints 1407, 1408 and so on in order.

Controls, same command:

```
ticket 08 with "Size: about 798 code lines, 4 code files."   refused: Size names 798 code lines, the cap is 150   (exit 2)
ticket 08 with 4 code files under In:                        refused: Scope In names 4 code files, the cap is 3   (exit 2)
ticket 01 with its Proof command lines removed               refused: a behavior ticket needs a `Proof command:` block ...   (exit 2)
```

## Not covered

`proofOnOpen` (the red run on main and the `Expected red signature` match) is not on `origin/main` yet: it is in PR #820's branch. SRW has no `proofOnOpen`, so these dry runs do not run the proofs through `ticket open`. The signature lines follow `docs/ticket-open-proof.md` on that branch.
