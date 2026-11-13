# MO-202 decisions

Run id: `ticket:shyamsivakumar/mac-ops#167:a2` (run a2 continues run a1's
work). Refs #167.

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

## What landed

- `evidence/MO-202/moonmux-needs-you.md`: how Moonmux detects that an agent
  needs the user, compared signal by signal with herdr-projects and the
  mac-ops coordinator panel.
  - 15 signals, each with how it is detected, the Moonmux file and line at
    the pinned commit `ef34516`, the upstream commit that introduced it,
    what herdr-projects has today, and a copy-or-skip with a reason.
  - The licenses are named: Moonmux is MIT (Fabien Penso, 2026), herdr-core
    is Apache-2.0.
  - Six recommendations, ordered by value.
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
  the merits. On the presentation side, only the alert discipline and the
  seen-and-dismissed state are worth anything. There is also one
  detection-side gap on our side: an agent reporting `error` is not treated
  as needs-you (row 15, recommendation 1).
- **Verdict**: sound.
- **Confidence**: high.

### 3. herdr-projects is credited with the screen reads it does

- **When**: revision 1, corrected in revision 3.
- **The decision**: Row 9a records that herdr-projects reads a pane's screen
  for trust dialogs (`src/trust_screen.rs`) and treats a trust screen as
  blocked for the brief (`src/ticker.rs:644-646`). The earlier draft said
  flatly that herdr-projects never reads a screen, which was wrong. Revision
  1 also implied the trust read was the only screen read; revision 3 drops
  that claim and names the other two places the screen is read for
  non-needs-you facts (`src/brief.rs:119-174` for the input box, the
  delivery marker and the settle key; `src/steps.rs:353-368` for an empty
  input box before a nudge).
- **The gap**: The claim came from the needs-you path only; the trust path
  was found afterwards by grepping for screen reads in `src/`, and the other
  two reads were found by the second reviewer round.
- **The reach**: The row keeps the comparison honest: we read the screen for
  safety and for delivery facts, and only the trust read changes the
  needs-you state; Moonmux has a general screen read, for detection.
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

## Proof

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

## The second reviewer round

One more in-session reviewer round (Codex `gpt-6.1-sol`, delegated, read
only) read this diff against the ticket and returned `VERDICT: FAIL` with
seven findings. All seven were checked against the pinned trees and fixed:

1. **The summaries hid the one detection gap.** The short answer said we
   were only missing presentation ideas, which contradicted row 15 and
   recommendation 1. Both summaries now say that an agent reporting `error`
   is not treated as needs-you.
2. **"A screen is read for one case only" was false.** The trust read is the
   only screen read that changes a needs-you state, but it is not the only
   screen read: `src/brief.rs:119-174` and `src/steps.rs:353-368` read the
   same screen for other facts. Row 9a is now titled "A screen is read for
   trust dialogs" and names the other reads.
3. **Row 9 claimed one shared order; there are two.** The overview iterates
   `Group::DISPLAY_ORDER` (`src/overview.rs:146`), the sidebar metadata
   publishes `Group::rank()` (`src/sidebar.rs:90`, enumerated at
   `src/thread.rs:472-480`). The values agree, but they are two lists. The
   row now says so, and the recommendation is to fold them into one.
4. **Row 11 cited the wrong lines and described `elsewhere` wrongly.** The
   visibility suppression is at `app/mods/alerts/main.luau:96-99`, not
   `84-92`, and `elsewhere` covers agents with no app-owned pane (an agent
   the app did not start), not agents in another space. Both fixed.
5. **Row 12 over-claimed our side.** We print the pane and the cockpit
   cycles to a blocked agent, but our notification carries no id and no
   agent target (`src/notify.rs:43-51`), so a click does not land on the
   agent. The row now says "Partly".
6. **Recommendation 3 was presented as Moonmux's behaviour.** Moonmux
   demotes a seen `done`, not a seen `blocked`. The recommendation and row 7
   now say that extending it to `blocked` is our extrapolation.
7. **Recommendation 1 overstated the gap.** An agent reporting `error` is
   never made needs-you by that fact, but it does not simply sit in `Idle`:
   `group()` can put it in `Resolved`, `Landing`, `ReadyForReview` or
   `Working` on other facts. The recommendation and row 15 now state the
   condition.

Nothing in the review was left unaddressed, and no existing test or check
was touched.

## Known limits

- The herdr-projects rows describe the released Rust line (0.2.34,
  `4e4548c`). `origin/main` has moved on and is now a TypeScript app.
- Moonmux was not run and not installed, per the brief, so the table
  describes the source, not an observed run.
- The Moonframe upstream (the framework Moonmux draws with) was not read
  beyond the mods in the Moonmux repo.
- The `agents()` list that the mac-ops cockpit imports lives in herdr-app,
  outside this repo, so that row is described from its call site
  (`coordinator/mods/cockpit/main.js:707`).

## Rollback

Revert the evidence commit.
