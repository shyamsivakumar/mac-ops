# MO-226 decisions

Run id: `ticket:shyamsivakumar/mac-ops#196:a1`. Refs #196.

## What landed

- `coordinator/bin/ticket`: the launch brief that `ticket start` assembles now
  carries the coordinator decision comments and the concrete run id.
- `evidence/MO-226/decisions.md`: this file.

Nothing else changed. No refusal rule changed, no label or blocker behaviour
changed, no existing test was edited or weakened, and no other repository was
modified. No new test file was added: the standing rule forbids one, so the
proof is the real `ticket start --dry-run --print-brief` output on
strategy-replay-workbench#977, pasted below.

## The failure this fixes

On 2026-11-13 about 25 SRW builders stopped with no change. Their stated
reasons were all missing from the brief they were given:

- "missing coordinator Opus PASS" — the PASS was recorded in an issue comment,
  and the brief carried only the issue body.
- "confirm the run ID" — the brief never filled in the run id.
- "proof edit not authorized" — the authorization was in a comment.

The comment channel was the coordinator's decision channel, and the brief
assembly dropped it. Stale stop conditions written in the body therefore won
over the newer decision.

## Decisions

### 1. The decision comments are appended to the brief, not merged into the body

- **When**: revision 1.
- **The decision**: Every issue comment whose body starts with "Coordinator",
  and every comment that quotes Shyam, is appended verbatim under a new
  `## Coordinator decisions (override the body)` heading at the end of the
  brief. The body itself is left untouched.
- **The gap**: A brief that rewrites the body would make the coordinator's
  own record unreadable: the body is the ticket, and the decisions are
  amendments to it.
- **The reach**: The heading says the section overrides the body, so a builder
  that reads only the tail still gets the current decision. The body stays
  byte-identical to what the issue says.
- **Verdict**: sound.
- **Confidence**: high.

### 2. A comment counts as a decision when it starts with "Coordinator" or quotes Shyam

- **When**: revision 2, after the in-session review round.
- **The decision**: The rule is a body-prefix match on "Coordinator"
  (case-insensitive) plus an attribution test for a Shyam quote: the name
  Shyam has to sit next to a quoted span (double quotes, single quotes or a
  markdown block quote) and something has to attribute the quote to it (a
  speech verb or a colon). The machine ledger lines
  (`<!-- coordinator-ticket ... -->`) are stripped from the appended text.
- **The gap**: Revision 1 tested only "mentions Shyam and contains a quoted
  span". That missed `Shyam said:` followed by a block quote and
  `Shyam's words: 'go ahead'`, and it swept in unrelated comments such as
  `Shyam, the builder reported "approval missing"`. The review round found
  both. Revision 2 requires the attribution, so the unrelated comment is
  dropped and the quoted forms are caught.
- **The reach**: A coordinator comment that does not start with "Coordinator"
  but carries a Shyam quote is still carried, which is the case the ticket
  names ("plus any comment quoting Shyam").
- **Verdict**: sound.
- **Confidence**: medium-high. The attribution test is a heuristic, but it
  errs toward including a decision rather than dropping one.

### 3. The run id is filled in where the body asks for it, and added when it does not

- **When**: revision 2, after the in-session review round.
- **The decision**: The brief replaces a run id token with the concrete request
  id that `ticket start` is about to use
  (`ticket:<repo>#<github issue number>:a<attempt>`, attempt taken from the
  recorded intents) only when the body introduces it as the run instruction,
  that is when a "run id" cue sits right before it with nothing but
  punctuation between. When the body names no run id, the brief header gains a
  `Run id: ...` line.
- **The gap**: The coordinator drafts the Finish section by hand and often
  writes the ticket key instead of the issue number, so SRW-1101 (issue 977)
  carried `ticket:...#1101:a1` while the real run id was
  `ticket:...#977:a1`. Revision 1 replaced every run id token in the body,
  which the review round caught: a historical or prerequisite reference such
  as "Previous prerequisite run was ticket:...#196:a2" was rewritten to the
  current run. Revision 2 fills only the run instruction.
- **The reach**: The run instruction in the Finish section now names one
  concrete run id, so a builder can confirm it without asking, and every other
  run id in the body stays as the coordinator wrote it. The attempt number is
  the same one the CLI posts in the intent comment and sends as
  `clientRequestId`.
- **Verdict**: sound.
- **Confidence**: high.

### 4. `--print-brief` is display-only and never starts a ticket

- **When**: revision 1.
- **The decision**: `ticket start <ref> --print-brief` prints the brief that a
  start would send and stops. It posts no comment, starts no thread, changes
  no label and touches the queue. With `--dry-run --print-brief` it prints the
  dry-run report and then the brief.
- **The gap**: There was no way to see the brief without starting a ticket,
  and a ticket that was already started has had its stage label removed, so
  `ticket start --dry-run` refuses it.
- **The reach**: The brief can be inspected for any ticket, started or not.
- **Verdict**: sound.
- **Confidence**: high.

### 5. The start refusal rules are untouched

- **When**: revision 1.
- **The decision**: The validation order in `cmd_start` is unchanged:
  `validate_start` still raises before the ledger is read, and a refusal still
  exits 2 with the same message. `--print-brief` is the only new path, and it
  starts nothing.
- **The gap**: A display path that runs the same validation and then reports
  "a start right now would be refused: ..." is more honest than a display
  path that skips validation.
- **The reach**: A ticket without a stage label is still refused with
  `refused: needs exactly one stage label, found 0` and exit code 2 on the
  plain `ticket start --dry-run` path.
- **Verdict**: sound.
- **Confidence**: high.

### 6. No new test file; the proof is the real brief

- **When**: revision 2, on the coordinator's instruction.
- **The decision**: The branch adds no test file. The standing rule forbids
  one, and the proof is the real `ticket start --dry-run --print-brief` output
  on strategy-replay-workbench#977 plus the repository's own checks
  (`python3 scripts/mac_ops_fast_check.py` and the full suite through
  `heavy`). No existing test was edited or weakened.
- **The gap**: The change ships without an automated regression test for the
  filter and the run id fill, so the review round's findings are locked in by
  the decisions ledger and the pasted output rather than by a test.
- **The reach**: The behaviour is still exercised end to end on a live ticket,
  and the full existing suite still passes unchanged.
- **Verdict**: sound, with the known gap that the filter rules are not
  covered by an automated test.
- **Confidence**: high on the behaviour, medium on the regression safety.

## Proof

`ticket start shyamsivakumar/strategy-replay-workbench#977 --dry-run --print-brief`
against the real CLI prints the 2026-11-12 coordinator decision comment and a
concrete run id. Head and tail of the output:

```
Ticket: https://github.com/shyamsivakumar/strategy-replay-workbench/issues/977
Reviewer for the gate: opus
...
## Finish
Run id `ticket:shyamsivakumar/strategy-replay-workbench#977:a3`; reuse any open PR for that branch and never open a second one. Write `evidence/SRW-1101/decisions.md` in the audit-decisions format before reporting done (an empty ledger on non-trivial work is a red flag, not a pass), then one in-session review round, then open the PR ready for review with `Refs #955` and the head SHA. No merge, no deploy, no Railway change.


## Coordinator decisions (override the body)

### 2026-11-13 · shyamsivakumar

Coordinator decision (Shyam 2026-11-12: "go on lane 3", "lane 4 as well", "you dont need me for anything"): registry-aware validation in bot2/lane_control_schema.js is in scope for this ticket, so enabled Lane 3/4 configs validate when their rule kind is registered. Lane 1/2 validation output stays identical. Network is allowed for git fetch/push, gh and the check's dependency install.

Source: https://github.com/shyamsivakumar/strategy-replay-workbench/issues/977#issuecomment-6845590447

note: a start right now would be refused: needs exactly one stage label, found 0
```

The run id in the body was `ticket:shyamsivakumar/strategy-replay-workbench#1101:a1`
before this change; the brief now carries `#977:a3`, the attempt the CLI would
use next. The refusal note is expected: SRW-1101 was already started twice and
`ticket start` removes the stage label after a start.

The same command on a ticket whose body has no run id, mac-ops#196, prints the
run id in the header:

```
Ticket: https://github.com/shyamsivakumar/mac-ops/issues/196
Reviewer for the gate: opus
Run id: `ticket:shyamsivakumar/mac-ops#196:a2`
```

## The in-session review round

One reviewer round ran on revision 1 (gpt-6.1-sol, read-only). It returned
FAIL with two major findings and two minor ones:

1. Major: the Shyam quote filter missed `Shyam said:` with a markdown block
   quote and `Shyam's words: 'go ahead'`, and swept in
   `Shyam, the builder reported "approval missing"`. Fixed in revision 2 by
   requiring the name to sit next to the quote and an attribution to tie the
   quote to it.
2. Major: the run id substitution rewrote every run id in the body, including
   a historical prerequisite reference. Fixed in revision 2: only the run
   instruction is filled.
3. Minor: the payload assertion could pass on the separately printed brief
   instead of the queued message, and the stub `gh` accepted mutations
   silently. Both assertions were in the test file that the standing rule
   removed, so nothing was left behind.
4. Minor: a comment with no author crashes the pre-existing `ledger_of`. Not
   introduced here and out of scope; `coordinator_decisions` handles a missing
   author.

## Rollback

Revert the single commit and reinstall the CLI from the reverted main. No
stored state changes: the run id and the decision section are computed at
start time and travel only in the queued payload.
