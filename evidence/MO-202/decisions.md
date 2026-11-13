# MO-202 decisions

Run id: `ticket:shyamsivakumar/mac-ops#167:a1`. Refs #167.

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

## Proof

1. **The clone and the pins.** `git clone --depth 50
   https://github.com/moonframehq/moonmux.git` into `$TMPDIR`; `git rev-parse
   HEAD` gave `ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f`, and every file and
   line in the table was read at that commit. `herdr-core` was cloned the
   same way (`d9e68262268b25a33bfe79cabb41fe60baf5db07`), and herdr-projects
   was read in place at `4e4548c3c43888e6be1c96906215998f07dc63f0`.
2. **The upstream commits.** `git log --oneline -S` on the Moonmux clone
   found the commit that introduced each signal: `4d06ea0` (the tmux
   detector, `src/core/tmux/agents.rs`), `8fcf76a` (status grouping,
   `app/mods/sidebar/main.luau`), `dc3b848` (alerts,
   `app/mods/alerts/main.luau`), `50f21c0` (the elsewhere setting),
   `e8c3f90` (the Done fix), `bfd23a6` (phrase sorting).
3. **The licences.** `LICENSE` in the Moonmux clone is the MIT text with
   "Copyright (c) 2026 Fabien Penso"; `NOTICE` credits herdr-app (Apache-2.0)
   for the Pi icon; the herdr-core `LICENSE` is Apache-2.0.
4. **Our side.** Every herdr-projects path and line in the table was opened
   and read at the pinned commit, and the trust-screen path was found by
   grepping `src/` for screen reads, not from memory.
5. **Checks.** `python3 scripts/mac_ops_fast_check.py` passed; the result
   and the head sha are in the PR body.

## Known limits

- Moonmux was not run and not installed, per the brief, so the table
  describes the source, not an observed run.
- The Moonframe upstream (the framework Moonmux draws with) was not read
  beyond the mods in the Moonmux repo.
- The `agents()` list that the mac-ops cockpit imports lives in herdr-app,
  outside this repo, so that row is described from its call site
  (`coordinator/mods/cockpit/main.js:707`).

## Rollback

Revert the evidence commit.
