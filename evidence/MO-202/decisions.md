# MO-202 decisions

Run id: `ticket:shyamsivakumar/mac-ops#167:a3` (run a3 continues runs a1 and
a2's work). Refs #167.

Revision 2 (2026-11-13): the first version of the evidence file went up as
PR #194 and was merged before the in-session Opus 5.5 review came back. The
review found ten wrong or unsupported claims. They are fixed in this
revision, and the follow-up PR carries them. The list is under "Corrections
after the review" in the evidence file.

Revision 3 (2026-11-13, run a2): the revision 2 corrections sat on a branch
whose base was the pre-merge parent, so `main` moved under it and the pull
request came back as conflicting. Run a2 re-applies the same corrected
content onto `main` as it stands, re-checks the references against a fresh
read-only clone, and runs one more reviewer round. No new research, no new
claims, no code.

Revision 4 (2026-11-13, run a3): the Moonmux half of the evidence is
unchanged and re-verified (`moonframehq/moonmux` `main` is still
`ef34516`). The **our side** half was wrong and is now corrected. Revision
3's caveat said the live `herdr-projects` tree has "no agent-status
detection at all". It does have detection, in TypeScript, in
`server/core/source.ts:228-241` and `server/core/agents.ts:243-247`. The
evidence file now carries a signal-by-signal comparison against the live
tree (`a862ac9`) with `blob/<sha>` links, and the recommendations are
re-targeted at the code that actually runs. Two of revision 3's six
recommendations changed as a result: the on-screen suppression is already
done in the live tree, and the alert-discipline recommendation narrowed to
the one case the live tree still misses.

## What landed

- `evidence/MO-202/moonmux-needs-you.md`: how Moonmux detects that an agent
  needs the user, compared signal by signal with herdr-projects and the
  mac-ops coordinator panel.
  - 15 signals, each with how it is detected, the Moonmux file and line at
    the pinned commit `ef34516`, the upstream commit that introduced it,
    what herdr-projects has today, and a copy-or-skip with a reason.
  - Revision 4 adds the same 15 signals against the live `herdr-projects`
    tree (`a862ac9`, TypeScript), each with a `blob/<sha>` link.
  - The licenses are named: Moonmux is MIT (Fabien Penso, 2026), herdr-core
    is Apache-2.0, herdr-projects at `a862ac9` is MIT (Elias Stravik, 2026).
  - Six recommendations, ordered by value, each aimed at a named file and
    line in the live tree.
  - After the run-a3 reviewer round: two rows that described `reconcile()`
    wrongly were corrected, the "agents started outside the app" idea came
    back as recommendation 1, recommendation 1 was reworded, and four loose
    descriptions were tightened.
- `evidence/MO-202/decisions.md`: this file.

Nothing else changed. No code was copied from Moonmux, Moonmux was not
installed, and no repository other than this one was modified.

## Decisions

### 1. The Moonmux clone lives in `$TMPDIR` and was read only

- **When**: revision 1.
- **The decision**: Shallow clone of `moonframehq/moonmux` into `$TMPDIR`,
  read from there, deleted with the temp directory.
- **The gap**: The brief allows a clone into `$TMPDIR` but forbids an
  install.
- **The reach**: A reader can reproduce the file and line numbers from the
  pinned commit without Moonmux on the machine.
- **Verdict**: sound.
- **Confidence**: high.

### 2. The comparison is against herdr-core's own status report, not against
Moonmux's scraper

- **When**: revision 1.
- **The decision**: The signal table says what herdr-projects has, not what
  Moonmux has. Where the two reach the same state by different means
  (OSC 7501 report versus screen phrase), the row says so and the copy
  verdict is skip.
- **The gap**: A literal line-by-line diff of two code bases would have
  compared Moonmux's tmux scraper with our herdr-core path and made our side
  look empty.
- **The reach**: The table answers the ticket's question (what to copy) on
  the merits: only the alert discipline and the seen-and-dismissed state are
  worth anything, and both are presentation, not detection.
- **Verdict**: sound.
- **Confidence**: high.

### 3. herdr-projects is credited with the one screen read it does

- **When**: revision 1.
- **The decision**: Row 9a records that herdr-projects reads a pane's screen
  for trust dialogs (`src/trust_screen.rs`) and treats a trust screen as
  blocked for the brief (`src/ticker.rs:644-646`). The earlier draft said
  flatly that herdr-projects never reads a screen, which was wrong.
- **The gap**: The claim came from the needs-you path only; the trust path
  was found afterwards by grepping for screen reads in `src/`.
- **The reach**: The row keeps the comparison honest: we have one narrow
  screen read, for safety, and Moonmux has a general one, for detection.
- **Verdict**: sound.
- **Confidence**: high.

### 4. Recommendation 6 says skip the scraper, and says why at the level of
the mechanism

- **When**: revision 1.
- **The decision**: The evidence names the reason a scraper exists at all:
  a tmux pane has no OSC 7501 report to read, and the fix for tmux panes is
  to pass OSC through tmux, not to copy a phrase list.
- **The gap**: "Do not copy" is only useful with the alternative.
- **The reach**: If a tmux pane ever has to be on the board, this file says
  which way to go.
- **Verdict**: sound, with the caveat that the tmux OSC pass-through claim
  was not tested here (no tmux pane was set up, per the no-install rule).
- **Confidence**: medium on the tmux claim, high on the rest.

### 5. No code from Moonmux, so the MIT notice travels nowhere

- **When**: revision 1.
- **The decision**: Copying is legal with the notice kept, but nothing here
  is worth the notice, so the file copies no code.
- **The gap**: The brief asked for the license to be checked and named.
- **The reach**: A later ticket that does copy a phrase list must carry the
  MIT notice and Fabien Penso's copyright.
- **Verdict**: sound.
- **Confidence**: high.

## Decisions (revision 4)

### 6. The comparison is redone against the live tree, and the old table is
kept

- **When**: revision 4.
- **The decision**: The file keeps the fifteen-signal table read at the
  released Rust line `4e4548c`, and adds the same fifteen signals read at
  the live tree `a862ac9`, with a verdict column for each.
- **The gap**: Revision 3 said the live tree has no detection at all, so
  its recommendations pointed at the Rust line only. That is wrong, and a
  reader following them would have changed the wrong code.
- **The reach**: A reader now sees which of Moonmux's ideas the live tree
  already has (the in-app on-screen suppression, the helper rule, the alert
  jump) and which it still lacks (`error` as a need, a "seen" memory,
  time-in-state per agent, and the agents the user started by hand).
- **Verdict**: sound.
- **Confidence**: high.

### 7. The wrong caveat is corrected in place, not deleted

- **When**: revision 4.
- **The decision**: The revision 3 caveat paragraph is kept and marked
  corrected, with the correction spelled out in the same place.
- **The gap**: Deleting it would hide the fact that the file was wrong for
  a whole revision.
- **The reach**: The corrections list at the end of the evidence file names
  each wrong claim and its fix, so a reader can audit the change.
- **Verdict**: sound.
- **Confidence**: high.

## Proof

0. **The live tree, read in place.** `herdr-projects` `origin/main` was
   fetched and read at `a862ac947306621bac9e8130db8b3cd6ffead6fe`:
   `server/core/source.ts`, `server/core/agents.ts`, `server/core/tasks.ts`,
   `server/core/automations.ts`, `server/core/news.ts`, `server/app.ts`,
   `server/push.ts`, `shared/alerts.ts`, `shared/attention.ts`,
   `shared/types.ts`, `src/attention.ts`, `LICENSE`. Every line number the
   new table cites was printed and checked against the file at that
   commit; one was wrong on the first pass (`source.ts:222` is a closing
   brace, the reconcile call is `:223`) and was corrected before the
   commit.
1. **Moonmux did not move.** `git ls-remote origin refs/heads/main` on
   `moonframehq/moonmux` returned `ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f`,
   the same commit the revision 1 and 2 tables were read at, so the
   Moonmux half of the file needed no change.
1. **The clone and the pins.** `git clone --depth 50
   https://github.com/moonframehq/moonmux.git` into `$TMPDIR`; `git rev-parse
   HEAD` gave `ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f`, and every file and
   line in the table was read at that commit. `herdr-core` was cloned the
   same way (`d9e68262268b25a33bfe79cabb41fe60baf5db07`), and herdr-projects
   was read in place at `4e4548c3c43888e6be1c96906215998f07dc63f0`.
2. **The upstream commits.** `git log --oneline -S` on the Moonmux clone
   found the commit that carried each signal: `4d06ea0` (the tmux
   detector, `src/core/tmux/agents.rs`), `8fcf76a` (status grouping,
   `app/mods/sidebar/main.luau`), `dc3b848` (alerts,
   `app/mods/alerts/main.luau`), `a571cc5` (the first commit: the herdr
   listing, the `ours` label, `shown_status`), `e8c3f90` (the screen-hash
   "still printing" fix), `bfd23a6` (phrase sorting). For four rows the
   `-S` hit was a later refactor, so the first commit that carried the
   signal was found by reading that commit's diff; the reviewer caught all
   four, and the rows now name the first commit.
3. **The licences.** `LICENSE` in the Moonmux clone is the MIT text with
   "Copyright (c) 2026 Fabien Penso"; `NOTICE` credits herdr-app (Apache-2.0)
   for the Pi icon; the herdr-core `LICENSE` is Apache-2.0.
4. **Our side.** Every herdr-projects path and line in the table was opened
   and read at the pinned commit, and the trust-screen path was found by
   grepping `src/` for screen reads, not from memory.
5. **Checks.** `python3 scripts/mac_ops_fast_check.py` passed; the result
   and the head sha are in the PR body.

## The reviewer round

One in-session reviewer round (Claude Opus 5.5, delegated through the task
router, read-only) read the merged diff against the ticket and returned
`VERDICT: FAIL` with seventeen findings. What was done with them:

1. **Wrong claim, fixed.** The first version said herdr-projects alerts on
   agent state rather than on transitions. It does not: the ticker only
   records a transition when the group changed and there was a previous
   group (`src/ticker.rs:682-686`), and the alert fires once on the move
   into `WaitingOnYou` (`src/steps.rs:198-225`). Recommendation 1 was
   rewritten as the real gap, and the group-versus-status point moved to
   recommendation 2.
2. **Wrong commits, fixed.** Rows 5, 7, 11 and 14 named the wrong upstream
   commit. They now name `e8c3f90`, `a571cc5`, `dc3b848` and `a571cc5` /
   `4d06ea0`, and the evidence file says how each was found.
3. **Wrong claims about our side, fixed.** `error` is not treated as
   needs-you by herdr-projects (row 15), `state_secs` comes from our own
   `thread.last_state_change` and not from herdr-core's `state_change_seq`
   (row 13), and herdr-projects does adopt panes it did not start
   (`Kind::Adopted`, row 14).
4. **Unsupported, softened.** The tmux OSC pass-through claim in
   recommendation 6 is no longer stated as fact; it is stated as something
   to prove before anyone relies on it.
5. **Acceptance gap, fixed.** The evidence file now carries real
   `blob/<sha>` links for every file and line, as the acceptance asks.
6. **Missing context, added.** herdr-projects `origin/main` is 585 commits
   past the pinned release and has been rewritten as a TypeScript app with no
   Rust sources; the recommendations now say which tree they apply to.
7. **Nits, fixed.** The `ctrl-c to interrupt` phrase, the `entry()` line
   range, the trust-screen line range, the tmux "every server" wording, and
   the statement that the turn is counted by herdr-core rather than carried
   in the OSC 7501 report.
8. **Not changed.** The reviewer's note that the PR was already merged when
   the review ran is true: PR #194 was merged by the coordinator before the
   review came back. The corrections ride in a follow-up PR rather than a
   force push to a merged branch.

Nothing in the review was left unaddressed, and no existing test or check
was touched.

### The run-a3 reviewer round

One in-session reviewer round (Claude Opus 5.5, read-only) read the
revision 4 diff against the ticket and returned `VERDICT: FAIL` with eight
findings. All eight are fixed in the evidence file, under "The run-a3
reviewer round" there.

1. **Row 14 was wrong, and it hid a recommendation.** The live tree does
   not see every agent herdr-core reports: `reconcile()` walks the app's
   own records and `terminal()` matches only terminals carrying this
   launch's labels (`server/core/agents.ts:63-69`, `:56-62`). The row now
   says "No", and Moonmux's "sees agents started outside the app" is
   recommendation 1.
2. **Row 1 described the same code wrongly.** Agents come from the app's
   own launch records, not from herdr-core.
3. **Recommendation 1 overstated its effect.** A crashed process is already
   a need (dead pid at `source.ts:235`, finished terminal at
   `tasks.ts:121`); the gap is an agent that is alive and reports
   `state=error`. Reworded.
4. **Row 9 called a filter an order.** `waiting()` filters by status; it
   orders nothing. The row now says so.
5. **Row 12's shape was off.** `go` is `{ place, task }`; `focus` is added
   later.
6. **A hook event was missing.** `agents.ts:243` also sets `idle` on
   `SessionStart`.
7. **Rows 7 and 11 overstated `keptTags`.** The in-app rule is per chat
   (`plugins/alerts/client.tsx:45`), the push skip is per device
   (`server/app.ts:109-110`). Both rows now say "Partly".
8. **A stale cross-reference** in the revision 2 corrections list, which
   still pointed at the old recommendation numbers.

The reviewer confirmed the rest by reading the code at the pinned commits:
the Moonmux pin is still upstream `main`, the cited herdr-projects line
numbers are right, the `error` gap is real, the licences are as named, the
diff touches only the two evidence files, nothing was installed or copied,
and the acceptance criteria are met.

## Known limits

- The herdr-projects rows describe the released Rust line (0.2.34,
  `4e4548c`); revision 4 adds the live tree (`a862ac9`) beside them.
  Neither tree is a run of the product: both were read as source.
- The live tree's trust-screen equivalent was not looked for, the order the
  live sidebar draws needs-you rows in was not read, and the mac-ops
  cockpit panel was not checked for whether it already reads the live
  tree's `need` status. Recommendation 5 says to check before changing
  anything.
- Moonmux was not run and not installed, per the brief, so the table
  describes the source, not an observed run.
- The Moonframe upstream (the framework Moonmux draws with) was not read
  beyond the mods in the Moonmux repo.
- The `agents()` list that the mac-ops cockpit imports lives in herdr-app,
  outside this repo, so that row is described from its call site
  (`coordinator/mods/cockpit/main.js:707`).

## Rollback

Revert the evidence commit.
