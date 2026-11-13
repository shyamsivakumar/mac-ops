# MO-202: how Moonmux detects that an agent needs you

Run id: `ticket:shyamsivakumar/mac-ops#167:a1`. Refs #167.

Research only. Nothing was installed, nothing was copied out of Moonmux, no
code in any repo changed.

## Sources, pinned

| What | Repo | Commit | Date | License |
| --- | --- | --- | --- | --- |
| Moonmux (the app under study) | `moonframehq/moonmux` | `ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f` | 2026-11-11 | MIT, Copyright (c) 2026 Fabien Penso (`LICENSE`, `NOTICE`) |
| herdr-core (the backend Moonmux runs on for us) | `herdrdev/herdr-core` | `d9e68262268b25a33bfe79cabb41fe60baf5db07` | 2026-11-13 | Apache-2.0 (`LICENSE`) |
| herdr-projects (our side) | `shyamsivakumar/herdr-projects` | `4e4548c3c43888e6be1c96906215998f07dc63f0` | 2026-09-28 | see its own `LICENSE` |
| mac-ops (the coordinator panel) | `shyamsivakumar/mac-ops` | `93a1467360f27d8d9d7b6e105432a419142c46fa` | 2026-11-12 | repo licence |

Links are `blob/<sha>/<path>` on GitHub.

The Moonmux checkout was a read-only shallow clone in `$TMPDIR`; nothing was
installed and no Moonmux file was copied into any of our repos.

## The short answer

Moonmux does two different things, and only one of them is detection.

1. On **herdr-core** panes it does not detect anything. It reads the status
   herdr-core already reports per terminal (`src/core/herdr.rs:434-455`) and
   draws it.
2. On **tmux** panes it has its own detector: it scrapes the bottom of the
   agent's screen for phrases the agent prints (`src/core/tmux/agents.rs`), and
   runs a small state machine over what it sees.

In our stack the equivalent of (1) is already in place and better than
Moonmux's: herdr-core records the agent's own **OSC 7501** status report
(`crates/herdr-core/src/status.rs:14-60`), which carries a state
(`idle`/`working`/`done`/`blocked`/`error`), a kind (`permission`/`question`/
`auth`), a progress percentage, and a turn counter. Moonmux's tmux detector
is a fallback for a backend that has no such report.

herdr-projects does not screen-scrape for needs-you. It reads herdr-core's
`agent_status` plus the progress reports its own threads file, and it groups
the result into `WaitingOnYou` (`src/thread.rs:565-600`). It does read one
screen, narrowly: a trust dialog ("trust this folder?", "Hooks need review")
must never be answered by a typed brief, so that screen is checked right
before a prompt is sent (`src/trust_screen.rs:41-49`, `src/brief.rs:115`), and
a trust screen on a pane counts as `blocked` for the brief (`src/ticker.rs:640-646`).

So: our needs-you detection is already at least as good as Moonmux's for
herdr-core panes, and it is missing the *presentation* ideas (see the
recommendations), not the detection ideas.

## Signals

`Moonmux` column is `path:line` at `ef34516`.

| # | Signal | How Moonmux detects it | Moonmux | Upstream commit | herdr-projects | Copy / skip |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **The agent exists** | Read the pane's process tree with `ps -A -o pid=,ppid=,args=` and take the nearest descendant whose program or script name is a known agent (`node .../codex.js` counts as `codex`) | `src/core/tmux/agents.rs:106` (`agent_under`), `:130` (`agent_in`), `:34` (`MAX_DESCENDANTS` = 256) | `4d06ea0` (2026-11-01, "run terminals on tmux as well as herdr-core") | **Yes, differently.** `herdr agent list` returns one row per agent herdr-core knows (`src/herdr.rs:309`, field `agent_status` at `:212`). No process walking needed | **Skip.** herdr-core already owns agent discovery. Copying a `ps` walk into herdr-projects would duplicate it and lose `state_change_seq` |
| 2 | **Needs you (blocked)** | Scrape the last 15 non-empty lines of the pane's screen, lowercased, for phrases the agent prints when it waits on a human: `(y/n)`, `[y/n]`, `(yes/no)`, `do you want to`, `would you like to`, `allow once`, `allow always`, `don't ask again`, `press enter to continue` | `src/core/tmux/agents.rs:49` (`BLOCKED`), `:162` (`read_screen`), `:32` (`FOOT_LINES` = 15) | `4d06ea0` | **Yes, by a better route.** The agent's own OSC 7501 report says `state=blocked`, `kind=permission|question|auth` (`herdr-core` `crates/herdr-core/src/status.rs:14-30`); herdr-projects consumes it as `agent_status` and debounces it 30 s (`src/thread.rs:590`, `BLOCKED_DEBOUNCE_SECS` at `:15`) | **Skip.** herdr-core's signal is the agent telling us, not us guessing from prose. The phrase list would also fire on our own output (a README that says "do you want to") |
| 3 | **Working** | Scrape for phrases printed while an agent works: `esc to interrupt`, `ctrl+c to interrupt`, `esc to cancel`, `esc to stop`, `esc interrupt` | `src/core/tmux/agents.rs:37` (`WORKING`), `:162` | `4d06ea0`, phrases sorted in `bfd23a6` (2026-11-01) | **Yes.** Same OSC 7501 route; `working` is a state herdr-core reports, and herdr-projects' `Live::self_working` adds the report-file signal (`src/thread.rs:551`) | **Skip.** Same reason as #2 |
| 4 | **Only the foot of the screen counts** | Read the last 15 non-empty lines, so a hint printed 20 lines up is ignored | `src/core/tmux/agents.rs:32`, `:167` | `4d06ea0` | **Not needed.** There is no screen to read | **Skip.** Only meaningful for a scraper |
| 5 | **Still printing** | Hash the pane's screen every tick; if it has not changed for 2 s the pane is not printing, so a working agent between two hints is still working, and one that stopped is done | `src/core/tmux/agents.rs:21` (`RECENT_MS` = 2000), `:223` (`Track::observe`) | `4d06ea0`; fixed in `e8c3f90` (2026-11-01, "a tmux agent shows Done when it stops, even beside a busy pane") | **No equivalent, and none wanted.** herdr-core's turn counter and `done` state do this job without screen diffing | **Skip.** A cheap screen hash is the wrong tool when the agent reports its own state |
| 6 | **Idle / Working / Blocked / Done** | A four-state machine over the scrapes, with `since` (ms) and a `turn` counter that goes up on each `done` | `src/core/tmux/agents.rs:185` (`Status`), `:238` (`Track::next`) | `4d06ea0` | **Yes, and richer.** herdr-core's states are `idle`, `working`, `done`, `blocked`, `error` with `progress` (`herdr-core` `crates/herdr-core/src/status.rs:14-30`), plus a turn counter (`status.rs:74-80`). herdr-projects groups into six groups (`src/thread.rs:460-530`) | **Skip.** Our state set is a superset; Moonmux has no `error` state, and it folds `error` into "needs you" only for helper agents (`app/mods/sidebar/main.luau:76-83`) |
| 7 | **Done collapses to Idle once you looked at it** | The sidebar remembers the last turn it showed per terminal; a `done` whose turn was already seen (or whose pane is visible) is drawn as idle, so the user is not nagged about work they have seen | `app/mods/sidebar/main.luau:63-72` (`shown_status`) | `8fcf76a` (2026-11-01, "group agents by status, with their helpers and time in state"), kept through `0dba8c3` | **No.** herdr-projects has an analogous idea only for reports: `thread.acked_report_hash` vs `thread.report_hash` decides whether a new report is unread (`src/thread.rs:601-604`, `src/steps.rs:199-260`) | **Worth copying the idea (not the code).** A `blocked` we already looked at should stop shouting. This is presentation, not detection, so it fits our layering |
| 8 | **A helper's result belongs to its parent** | A child agent's `done` shows as idle; a child's `error` shows as needs-you; the parent's own `done` is the news | `app/mods/sidebar/main.luau:76-83` (`helper_status`) | `8fcf76a` | **No.** herdr-projects has no parent/child agent model in the overview; a delegated thread is its own board row | **Skip for now.** We would need a parent link in our thread model first; the herdr-core `parent` field exists (`herdr-core` `crates/herdr-core/src/terminals.rs`), so it is possible later |
| 9 | **One urgency order, one place** | Four sections, most urgent first: `blocked`, `working`, `done`, `idle`, with a loudness scale (`blocked` 4 > `working` 3 > `done` 2 > `idle` 1) that also picks the loudest agent for the status bar | `app/mods/sidebar/main.luau:39-42`, `:336`, `:506-508` | `8fcf76a` | **Yes, in our own words.** `Group::DISPLAY_ORDER` puts `WaitingOnYou` first, then `ReadyForReview`, `Landing`, `Working`, `Idle`, `Resolved` (`src/thread.rs:520-527`); the sidebar and the text overview both use it (`src/sidebar.rs:25-38`, `src/overview.rs:143-170`) | **Skip.** We already have one order, shared by the CLI and the ticker, which is the better shape |
| 9a | **A screen is read for one case only** | not in Moonmux: Moonmux has no trust-dialog concept | (Moonmux has nothing to compare) | (n/a) | **Yes, narrowly.** `trust_screen::detect` matches harness trust-dialog phrases on the pane's screen before a prompt is typed (`src/trust_screen.rs:41-49`, `src/brief.rs:115`); a trust screen makes the pane `blocked` for the brief (`src/ticker.rs:644-646`) | **Keep ours.** It is a safety check, not a needs-you signal, and Moonmux has no equivalent |
| 10 | **A sound and a notification, on a change only** | Watch the agent list; alert when an agent turns `blocked` or `done`, but only on a status change it saw happen: never for what the first look after a launch finds, never for a terminal it had not seen before, once per change | `app/mods/alerts/main.luau:62-110` (`look`), `:30` (`TITLES`) | `dc3b848` (2026-11-01, "a sound and a notification when an agent needs you or finishes unseen") | **Partly.** herdr-projects notifies per event with a sound (`src/notify.rs:43-51`, `Sound::Request` / `Sound::Done`), but the alert is driven by the ticker, not by a diff of agent status | **Copy the idea.** "Alert on a transition you witnessed, never on the first look" is the difference between a useful signal and noise. Our ticker should diff agent status the same way |
| 11 | **No alert for what is already on screen** | An alert is skipped when the window is active and the agent's pane is visible (or a peek shows it); an agent in another space, tab or session is "elsewhere" and can be included by a setting | `app/mods/alerts/main.luau:84-92`, setting `moonmux/alerts` `elsewhere` at `:158` | `dc3b848`; the elsewhere switch in `50f21c0` (2026-11-01) | **No.** herdr-projects notifies regardless of where the pane is (`src/notify.rs:43-51`) | **Copy the idea.** It is the cheapest way to cut alert fatigue: do not sound for a pane the user is already looking at |
| 12 | **Click the alert, land on the agent** | The notification's id encodes the terminal address, so a click focuses the pane, or opens a peek when the pane is off screen | `app/mods/alerts/main.luau:36-46`, `:111-124`; peek path `app/mods/sidebar/main.luau:447-449` | `dc3b848`, fixed for tmux in `7c3940b` (2026-11-01) | **Yes.** herdr-projects' overview prints `needs you in pane <id>` and the mac-ops cockpit overlay jumps to a blocked agent (`coordinator/mods/cockpit/main.js:707-712`) | **Skip.** We already have the jump; the id-encoding trick only matters for a notification we own |
| 13 | **Time in the current state** | `status_ms` per terminal: when the status last changed, so the sidebar can show "3 min" and sort by it | `src/core/tmux/mod.rs:362`; herdr path `src/core/herdr.rs:158-180` (`status_ms`) | `4d06ea0` | **Yes.** `Live::state_secs` comes from herdr-core's `state_change_seq` and `last_state_change` (`src/thread.rs:534-538`, `src/ticker.rs:646`) | **Skip.** Already ours |
| 14 | **Agents started outside the app are seen too** | On herdr-core, every terminal in the session is listed, not only the ones the app started; a label marks which are ours (`ours`). On tmux, every pane of the tmux server is scanned, and `ours` means "this server" | `src/core/herdr.rs:396-403`, `:450`; `src/core/tmux/mod.rs:173` | `50f21c0` (2026-11-01, "choose whether new panes run on herdr-core or tmux") | **Partly.** The mac-ops cockpit sees every agent in the herdr session (`coordinator/mods/cockpit/main.js:707`, via the herdr-app `agents()` list). herdr-projects itself only tracks the threads it launched (`src/ticker.rs`, `agent_list` filtered by thread id) | **Copy the idea for herdr-projects.** A needs-you overview that ignores an agent the user started by hand will miss the one that actually matters |
| 15 | **A failed agent is a need** | An agent that errored counts as needing you | `app/mods/sidebar/main.luau:78` (helper `error` becomes `blocked`) | `8fcf76a` | **Yes.** herdr-core reports `error` as its own state, and herdr-projects maps a failed thread to `WaitingOnYou` (`src/thread.rs:576-583`, `src/steps.rs:252-255`) | **Skip.** Ours is better: `error` is a state, not a demotion of a helper |

## What we would gain, honestly

Two things only.

- **The alert discipline** (#10, #11): alert on a witnessed transition, never
  on a first look, never for a pane already on screen. This is a change in
  our ticker, not in our detection.
- **The seen-and-dismissed state** (#7): a `blocked` the user has already
  looked at should stop being the loudest thing in the overview.

Everything else Moonmux does in this area is either a screen scraper we
should not copy (we have the agent's own report), or a presentation choice
we already made, in our own words.

## Recommendations, ordered by value

1. **Alert on transitions, not on state.** Diff `agent_status` per terminal
   in the ticker, and send a `Sound::Request` notification only when a
   terminal moves into `blocked` (or into `error`) after the last look, never
   on the first look after a launch and never twice for the same change.
   Source: Moonmux `app/mods/alerts/main.luau:62-110` (`dc3b848`). Cost: one
   map in the ticker; it removes the "same alert every tick" class of noise.
2. **Add a "seen" memory for needs-you.** Remember the turn or
   `state_change_seq` of each terminal the user has already looked at, and
   draw a `blocked` the user has seen as a quieter "waiting" row instead of
   the top needs-you entry. Source: Moonmux `app/mods/sidebar/main.luau:63-72`
   (`8fcf76a`). This is the one place where Moonmux is ahead of us, because
   herdr-core gives us `state_change_seq` to key the memory on.
3. **Do not sound for a pane the user is already looking at.** Suppress the
   request sound when the pane holding the blocked agent is the focused pane
   of the active workspace. Source: Moonmux `app/mods/alerts/main.luau:84-92`
   (`dc3b848`). Cheap, and it makes the remaining alerts trustworthy.
4. **Show the time in state next to a needs-you row.** `status_ms` (or
   `state_change_seq` and the tick clock) gives "waiting 4 min", which tells
   the user whether to look now or later. Source: Moonmux
   `src/core/tmux/mod.rs:362`, `src/core/herdr.rs:158-180`. We already keep
   `state_secs` (`src/thread.rs:537`), so this is a display change only.
5. **Widen the needs-you overview to agents we did not start.** The mac-ops
   cockpit already sees every agent in the herdr session
   (`coordinator/mods/cockpit/main.js:707`); herdr-projects' own overview does
   not. Source: Moonmux `src/core/herdr.rs:396-403` (`50f21c0`). Decide which
   of the two is the surface Shyam actually reads before doing anything.
6. **Skip the tmux screen scraper entirely.** It exists because tmux panes
   have no OSC 7501 report to read. If we ever need tmux panes in the board,
   the right fix is to read the OSC 7501 report through tmux (`tmux` passes
   OSC through with `set -g allow-passthrough on`), not to copy a phrase
   list. No code to copy: Moonmux is MIT (Fabien Penso, 2026) and copying it
   would require keeping the notice, but there is nothing here worth the
   notice.

## License

Moonmux is MIT (Copyright (c) 2026 Fabien Penso). `NOTICE` also credits
`herdr-app` (Apache-2.0) for the Pi icon. herdr-core is Apache-2.0. So
copying is legally allowed with the notice kept, and nothing here needs it:
this ticket copies no code, and the recommendation is not to.

## Method and limits

- Read: Moonmux `src/core/tmux/agents.rs`, `src/core/tmux/mod.rs`,
  `src/core/herdr.rs`, `app/mods/sidebar/main.luau`, `app/mods/alerts/main.luau`,
  `LICENSE`, `NOTICE`; herdr-core `crates/herdr-core/src/status.rs`,
  `crates/herdr-core/src/notes.rs`, `LICENSE`; herdr-projects `src/thread.rs`,
  `src/progress.rs`, `src/herdr.rs`, `src/overview.rs`, `src/sidebar.rs`,
  `src/notify.rs`, `src/ticker.rs`, `src/steps.rs`; mac-ops
  `coordinator/mods/cockpit/main.js`.
- Upstream commits were found with `git log -S` on the Moonmux clone
  (shallow, depth 50) and read with `git log --format`.
- Not checked: Moonmux's Moonframe upstream (the app framework it draws
  with) beyond the mods in this repo; the herdr-app `agents()` helper that
  the mac-ops cockpit imports (it lives outside this repo, so the cockpit's
  agent list is described from its call site only).
- Not run: Moonmux itself. No install, per the brief.
