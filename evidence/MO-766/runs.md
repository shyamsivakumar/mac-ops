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
| 01 identity and position helpers | 101 | 1 | nothing |
| 02 capacity, invariants, read | 72 | 1 | 01 |
| 03 book plumbing | 125 | 1 | 02 |
| 04 prove, allocate, reserve, markUnknown | 104 | 1 | 03 |
| 05 recordExecution, observeOrder, reconcile, release | 117 | 1 | 04 |
| 06 reads and exports | 72 | 1 | 05 |
| 07 executor wiring | 137 | 1 | 06 |
| 08 bots, ledger hooks, proof script, fixtures | 70 | 2 | 07 |

The sizes are the added lines in the matching diff ranges of `gh pr diff 1579`, with the 11 export lines in ticket 06. The proof commands of tickets 01 to 06 were run against `order_identity.cjs` at the PR head and print `function,...` (ticket 03 prints `string,string,string,string,number`); on a file without those exports they print `undefined`.

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
