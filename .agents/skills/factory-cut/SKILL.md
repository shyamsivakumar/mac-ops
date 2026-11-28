---
name: factory-cut
description: Cut a spec, a plan or an oversized pull request into a chain of tickets that each fit the 150-line, 3-file cap, and open them through `ticket open`. The only cut procedure for this factory.
---

# Factory cut

Use this for any spec, plan or oversized pull request that has to become tickets, and for the re-cut brief the lane sends. It replaces `prd-dag`, `to-spec` and `to-tickets` here: no Fusion waves, no tracker publishing of your own, no "fits one context window" sizing. `ticket open` is the only way a ticket is filed, and it refuses a body that breaks the rules below.

## Steps

1. Read the source. For a pull request: `gh pr view <n> -R <repo> --json files,headRefOid` and `gh pr diff <n> -R <repo>`. Name the pull request and head in every ticket's Context.
2. Count code lines and code files the way `ticket open` and the gate do (the size rule below). Do this per file, from additions plus deletions.
3. Cut along seams so each ticket is at most 150 code lines in at most 3 code files. Aim for 120 so a review fix still fits.
   - One behavior per ticket. Order them so the pure helper or owner comes first and the wiring comes last.
   - A file over 150 lines splits by function group inside the same file, one group per ticket.
   - Proof scripts, fixtures and evidence ride with the ticket that needs them. They do not count: the cap is runtime code lines only, and the builder pastes `Runtime code lines: <n>` and `Proof lines: <n>` in the PR body.
   - Never use `type:large` to get past the cap.
4. Give each behavior ticket one proof command that is red on `origin/main` for the reason the ticket fixes (the proof section below).
5. Write one body file per ticket from the template, in dependency order.
6. Chain with Blocked by: each ticket names the real issue number of the ticket it needs, not a title or a plan key.
7. Dry-run every body, then open them in order.
8. For a re-cut, comment once on the pull request, "Superseded by #<a>, #<b>, ...", and leave it open.

## Size rule

`ticket open` refuses a body when `Scope and non-goals` lists more than 3 code files under `In:`, or when its `Size:` line says more than 150 code lines. These do not count: `evidence/`, `docs/`, any `*.md`, `fixtures/` paths, files with `proof` in the name, and `evals/harbor/tasks/`. Write the `In:` entries as backticked paths at the start of a line (for example ``- `path`: what changes``) and end the section with `Size: about <n> code lines, <k> code files.`

## Template

Every body has these 12 headings, each with real content (`Nothing.` is real content for Blocked by):

```
## Goal and why
## Context
## Scope and non-goals
## Design fit
## Blocked by
## Acceptance and proof
## CI
## Must not cause
## Data/secrets and stop conditions
## Rollback
## Gate
## Finish
```

- Context: the source (spec, or the original pull request and head), the files and functions involved.
- Scope and non-goals: `In:` list, `Size:` line, `Out:` line.
- Design fit: `Requires:` the base commit and merged blockers; `Provides:` what a later ticket can rely on.
- CI: no GitHub Actions or Woodpecker, ever; the repo's local check run through `heavy`.
- Gate: reviewer, head, and that the verdict line ends the review.
- Finish: the PR, the head, the check line, and closing the ticket when the PR merges.
- Copy the wording of a recent ticket for CI, Must not cause, Data/secrets, Rollback, Gate and Finish: `gh issue view 810 -R shyamsivakumar/mac-ops`.

## Proof

Inside `Acceptance and proof`, a behavior ticket carries these two lines:

```
Proof command: <one command, runs from a clean checkout in under 120 seconds>
Expected red signature: <regex that matches the output on origin/main>
```

- Where `proofOnOpen` is on for the repo, `ticket open` runs the proof on `origin/main` and refuses unless it is red and the output matches the signature. It refuses a proof that passes ("nothing to build") and a body with no signature line. See `docs/ticket-open-proof.md`.
- A chained ticket is opened while its blockers are unmerged, so main still lacks the blocker's code. Write a signature that matches main as it is now (for example `undefined|is not a function`), not main after the blockers land.
- A ticket's proof must pass on (main plus that ticket's blockers plus that ticket), never only on the finished upstream PR. If a proof needs something a later ticket adds (an export, a helper, a fixture), move that part into this ticket or prove through what is already reachable.
- To check it, build the chain on a scratch branch one ticket at a time from the source's base commit. At each step run that ticket's proof: red on the step before, green on the step after. Never push the scratch branch.
- A docs or config ticket says `Proof command: none (prose)` and states the prose acceptance.
- Each acceptance case names a fixture (a path in the repo) or carries a waiver line `Waiver: <case> — <reason>`. The gate accepts a named waiver as meeting that case, may reject a reason that does not hold, and still demands a case that names neither. Use a waiver for a case the repository cannot prove, such as a legacy or partial persisted row with no fixture on main.
- Also add `Builder check: PASS <full sha>` as the last acceptance line.

## Blocked by

- List `#<number>` of each blocker, one per line, with what must be true ("merged").
- Open tickets in dependency order and read the number from the `url` that `ticket open` prints; paste it into the next body. A chain is linear unless two tickets touch different files and need nothing from each other.
- Tickets that edit the same file chain, even when the functions differ, so their diffs never conflict.

## Open

```
ticket open --repo <owner/name> --title "<title>" --body-file <file> --label stage:<stage>,type:<type>,priority:<n> --dry-run
```

Run the same command without `--dry-run` to open. The tool mints the key: never type one, never run `gh issue create`, never edit an issue by hand to add the template. When the source PR's ticket title carries `Parity <Pxx>`, each piece's `--title` is `Parity <Pxx>.<k> · <title>`, numbered from 1; `ticket open` refuses a malformed Parity label and adds the key. If `ticket open` refuses, fix the body or title and retry; a dry run writes nothing.

## Worked example

Oversized pull request: SRW #1579, 798 code lines in 4 code files. The cut has 8 tickets in a linear chain: the 591-line `order_identity.cjs` by function group, then the executor wiring, then the bots.

| Ticket | Code files | Code lines | Blocked by |
| --- | --- | --- | --- |
| 1 constants, identity keys, position helpers, their exports | order_identity.cjs | about 110 | nothing |
| 2 capacity, invariants, `readSellReservation` | order_identity.cjs | about 73 | 1 |
| 3 book plumbing: store, epoch, fenced commit | order_identity.cjs | about 126 | 2 |
| 4 `proveHoldings`, `allocateRow`, `reserve`, `markUnknown` | order_identity.cjs | about 104 | 3 |
| 5 `recordExecution`, `observeOrder`, `reconcile`, `release` | order_identity.cjs | about 117 | 4 |
| 6 `capacity`, `reservationFor`, `snapshot`, `close` | order_identity.cjs | about 61 | 5 |
| 7 executor wiring | thala_v2_executor.js | about 137 | 6 |
| 8 bot 2 and ledger hooks, proof script, fixtures | trade_machine.js, alpaca_paper_execution.js | about 70 | 7 |

Each helper is exported by the ticket that adds it, so every proof passes at its own step (`evidence/MO-766/runs.md`). The bodies are in `evidence/MO-766/srw1579-cut/`; `evidence/MO-766/example-ticket.md` is ticket 1.
