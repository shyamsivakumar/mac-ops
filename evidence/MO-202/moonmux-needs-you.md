# MO-202: how Moonmux detects that an agent needs you

Run id: `ticket:shyamsivakumar/mac-ops#167:a2` (run a2 carries run a1's work
forward). Refs #167.

Research only. Nothing was installed, nothing was copied out of Moonmux, no
code in any repo changed.

Revision 2 (2026-11-13): corrected after the in-session Opus 5.5 review of
the merged PR #194. What changed is listed under "Corrections after the
review" at the end.

Revision 3 (2026-11-13, run a2): no research change. The revision 2
corrections had to be carried onto a branch that was still based on the
pre-merge parent, so that branch went stale against `main`. This revision
is the same content, re-based onto `main` as it stands, with every Moonmux
line reference and every pinned-commit claim re-checked against a fresh
clone at `ef34516` and against the pinned herdr-projects tree
(`4e4548c`). The references and the conclusions are unchanged.

## Sources, pinned

| What | Repo | Commit | Date | License |
| --- | --- | --- | --- | --- |
| Moonmux (the app under study) | `moonframehq/moonmux` | `ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f` | 2026-11-11 | MIT, Copyright (c) 2026 Fabien Penso (`LICENSE`, `NOTICE`) |
| herdr-core (the backend Moonmux runs on for us) | `herdrdev/herdr-core` | `d9e68262268b25a33bfe79cabb41fe60baf5db07` | 2026-11-13 | Apache-2.0 (`LICENSE`) |
| herdr-projects (our side, released Rust line) | `shyamsivakumar/herdr-projects` | `4e4548c3c43888e6be1c96906215998f07dc63f0` (0.2.34) | 2026-09-28 | see its own `LICENSE` |
| mac-ops (the coordinator panel) | `shyamsivakumar/mac-ops` | `93a1467360f27d8d9d7b6e105432a419142c46fa` | 2026-11-12 | repo licence |

Every link below is a `blob/<sha>/<path>#L<line>` link at the pinned commit,
so the line numbers can be checked without a clone.

The Moonmux checkout was a read-only shallow clone in `$TMPDIR`; nothing was
installed and no Moonmux file was copied into any of our repos.

**A caveat that matters for the recommendations.** `herdr-projects`
`origin/main` (`a862ac9`) is 585 commits ahead of the pinned release and has
been rewritten: there is no `src/thread.rs`, `src/ticker.rs` or any other
Rust file there any more, and the app is now TypeScript. Its needs-you model
on `main` is a task status (`need`) plus unanswered chat requests
(`src/attention.ts`), with no agent-status detection at all. The rows below
describe the released Rust line (0.2.34), which is the code that talks to
herdr-core agents; the recommendations are about ideas, so they carry over,
but the file and line pointers do not.

## The short answer

Moonmux does two different things, and only one of them is detection.

1. On **herdr-core** panes it does not detect anything. It reads the status
   herdr-core already reports per terminal (`entry()` in
   [src/core/herdr.rs:432-453](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/herdr.rs#L432-L453))
   and draws it.
2. On **tmux** panes it has its own detector: it scrapes the bottom of the
   agent's screen for phrases the agent prints
   ([src/core/tmux/agents.rs](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs)),
   and runs a small state machine over what it sees.

In our stack the equivalent of (1) is already in place and better than
Moonmux's: herdr-core records the agent's own **OSC 7501** status report
([crates/herdr-core/src/status.rs:14-30](https://github.com/herdrdev/herdr-core/blob/d9e68262268b25a33bfe79cabb41fe60baf5db07/crates/herdr-core/src/status.rs#L14-L30)),
which carries a state (`idle`/`working`/`done`/`blocked`/`error`), a kind
(`permission`/`question`/`auth`) and a progress percentage. herdr-core counts
the turns itself
([status.rs:74-80](https://github.com/herdrdev/herdr-core/blob/d9e68262268b25a33bfe79cabb41fe60baf5db07/crates/herdr-core/src/status.rs#L74-L80));
the turn is not carried in the report. Moonmux's tmux detector is a fallback
for a backend that has no such report.

herdr-projects does not screen-scrape for needs-you. It reads herdr-core's
`agent_status` plus the progress reports its own threads file, and it groups
the result into `WaitingOnYou`
([src/thread.rs:565-600](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L565-L600)).
It does read one screen, narrowly: a trust dialog ("trust this folder?",
"Hooks need review") must never be answered by a typed brief, so that screen
is checked right before a prompt is sent
([src/trust_screen.rs:36-42](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/trust_screen.rs#L36-L42),
phrases at [src/trust_screen.rs:12-30](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/trust_screen.rs#L12-L30),
used at [src/brief.rs:115](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/brief.rs#L115)),
and a trust screen on a pane counts as `blocked` for the brief
([src/ticker.rs:640-646](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/ticker.rs#L640-L646)).

So: our needs-you detection is already at least as good as Moonmux's for
herdr-core panes, and it is missing the *presentation* ideas (see the
recommendations), not the detection ideas.

## Signals

The `Moonmux` column links the file and line at `ef34516`.

| # | Signal | How Moonmux detects it | Moonmux | Upstream commit | herdr-projects | Copy / skip |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **The agent exists** | Read the pane's process tree with `ps -A -o pid=,ppid=,args=` and take the nearest descendant whose program or script name is a known agent (`node .../codex.js` counts as `codex`) | [agents.rs:106](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L106) (`agent_under`), [:130](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L130) (`agent_in`), [:34](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L34) (`MAX_DESCENDANTS` = 256) | `4d06ea0` (2026-11-01, "run terminals on tmux as well as herdr-core") | **Yes, differently.** `herdr agent list` returns one row per agent herdr-core knows ([src/herdr.rs:309](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/herdr.rs#L309), field `agent_status` at [:212](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/herdr.rs#L212)). No process walking needed | **Skip.** herdr-core already owns agent discovery. Copying a `ps` walk into herdr-projects would duplicate it and lose `state_change_seq` |
| 2 | **Needs you (blocked)** | Scrape the last 15 non-empty lines of the pane's screen, lowercased, for phrases the agent prints when it waits on a human: `(y/n)`, `[y/n]`, `(yes/no)`, `do you want to`, `would you like to`, `allow once`, `allow always`, `don't ask again`, `press enter to continue` | [agents.rs:49](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L49) (`BLOCKED`), [:162](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L162) (`read_screen`), [:32](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L32) (`FOOT_LINES` = 15) | `4d06ea0` | **Yes, by a better route.** The agent's own OSC 7501 report says `state=blocked`, `kind=permission|question|auth` ([herdr-core status.rs:14-30](https://github.com/herdrdev/herdr-core/blob/d9e68262268b25a33bfe79cabb41fe60baf5db07/crates/herdr-core/src/status.rs#L14-L30)); herdr-projects consumes it as `agent_status` and debounces it 30 s ([src/thread.rs:590](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L590), `BLOCKED_DEBOUNCE_SECS` at [:15](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L15)) | **Skip.** herdr-core's signal is the agent telling us, not us guessing from prose. The phrase list would also fire on our own output (a README that says "do you want to") |
| 3 | **Working** | Scrape for phrases printed while an agent works: `esc to interrupt`, `esc interrupt`, `esc to cancel`, `esc to stop`, `ctrl+c to interrupt`, `ctrl-c to interrupt` | [agents.rs:37](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L37) (`WORKING`), [:162](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L162) | `4d06ea0`, phrases sorted in `bfd23a6` (2026-11-01) | **Yes.** Same OSC 7501 route; `working` is a state herdr-core reports, and herdr-projects' `Live::self_working` adds the report-file signal ([src/thread.rs:551](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L551)) | **Skip.** Same reason as #2 |
| 4 | **Only the foot of the screen counts** | Read the last 15 non-empty lines, so a hint printed 20 lines up is ignored | [agents.rs:32](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L32), [:167](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L167) | `4d06ea0` | **Not needed.** There is no screen to read | **Skip.** Only meaningful for a scraper |
| 5 | **Still printing** | Hash the pane's screen every tick; if it has not changed for 2 s the pane is not printing, so a working agent between two hints is still working, and one that stopped is done | [agents.rs:21](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L21) (`RECENT_MS` = 2000), [:223](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L223) (`Track::observe`) | `e8c3f90` (2026-11-01, "a tmux agent shows Done when it stops, even beside a busy pane"). Before that, `4d06ea0` used tmux's per-window `window_activity`, which a sibling pane's printing broke | **No equivalent, and none wanted.** herdr-core's turn counter and `done` state do this job without screen diffing | **Skip.** A cheap screen hash is the wrong tool when the agent reports its own state |
| 6 | **Idle / Working / Blocked / Done** | A four-state machine over the scrapes, with `since` (ms) and a `turn` counter that goes up on each `done` | [agents.rs:185](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L185) (`Status`), [:238](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/agents.rs#L238) (`Track::next`) | `4d06ea0` | **Yes, and richer.** herdr-core's states are `idle`, `working`, `done`, `blocked`, `error` with `progress` ([status.rs:14-30](https://github.com/herdrdev/herdr-core/blob/d9e68262268b25a33bfe79cabb41fe60baf5db07/crates/herdr-core/src/status.rs#L14-L30)), plus a turn counter ([status.rs:74-80](https://github.com/herdrdev/herdr-core/blob/d9e68262268b25a33bfe79cabb41fe60baf5db07/crates/herdr-core/src/status.rs#L74-L80)). herdr-projects groups into six groups ([src/thread.rs:460-530](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L460-L530)) | **Skip.** Our state set is a superset; Moonmux has no `error` state, and it folds `error` into "needs you" only for helper agents ([sidebar/main.luau:76-83](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/sidebar/main.luau#L76-L83)) |
| 7 | **Done collapses to Idle once you looked at it** | The sidebar remembers the last turn it showed per terminal; a `done` whose turn was already seen (or whose pane is visible) is drawn as idle, so the user is not nagged about work they have seen | [sidebar/main.luau:63-72](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/sidebar/main.luau#L63-L72) (`shown_status`) | `a571cc5` (2026-11-01, "herdr on Moonframe, with spaces, split panes and an agents sidebar", the first commit), later reworked in `8fcf76a` | **No.** herdr-projects has an analogous idea only for reports: `thread.acked_report_hash` vs `thread.report_hash` decides whether a new report is unread ([src/thread.rs:601-604](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L601-L604), [src/steps.rs:199-260](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/steps.rs#L199-L260)) | **Worth copying the idea (not the code).** A `blocked` we already looked at should stop shouting. This is presentation, not detection, so it fits our layering |
| 8 | **A helper's result belongs to its parent** | A child agent's `done` shows as idle; a child's `error` shows as needs-you; the parent's own `done` is the news | [sidebar/main.luau:76-83](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/sidebar/main.luau#L76-L83) (`helper_status`) | `8fcf76a` (2026-11-01, "group agents by status, with their helpers and time in state") | **No.** herdr-projects has no parent/child agent model in the overview; a delegated thread is its own board row | **Skip for now.** We would need a parent link in our thread model first; the herdr-core `parent` field exists ([terminals.rs:80](https://github.com/herdrdev/herdr-core/blob/d9e68262268b25a33bfe79cabb41fe60baf5db07/crates/herdr-core/src/terminals.rs#L80)), so it is possible later |
| 9 | **One urgency order, one place** | Four sections, most urgent first: `blocked`, `working`, `done`, `idle`, with a loudness scale (`blocked` 4 > `working` 3 > `done` 2 > `idle` 1) that also picks the loudest agent for the status bar | [sidebar/main.luau:39-42](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/sidebar/main.luau#L39-L42), [:336](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/sidebar/main.luau#L336), [:506-508](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/sidebar/main.luau#L506-L508) | `8fcf76a` | **Yes, in our own words.** `Group::DISPLAY_ORDER` puts `WaitingOnYou` first, then `ReadyForReview`, `Landing`, `Working`, `Idle`, `Resolved` ([src/thread.rs:520-527](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L520-L527)); the sidebar and the text overview both use it ([src/sidebar.rs:25-38](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/sidebar.rs#L25-L38), [src/overview.rs:146-170](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/overview.rs#L146-L170)) | **Skip.** We already have one order, shared by the CLI and the ticker, which is the better shape |
| 9a | **A screen is read for one case only** | not in Moonmux: Moonmux has no trust-dialog concept | (Moonmux has nothing to compare) | (n/a) | **Yes, narrowly.** `trust_screen::detect` matches harness trust-dialog phrases on the pane's screen before a prompt is typed ([src/trust_screen.rs:36-42](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/trust_screen.rs#L36-L42), [src/brief.rs:115](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/brief.rs#L115)); a trust screen makes the pane `blocked` for the brief ([src/ticker.rs:644-646](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/ticker.rs#L644-L646)) | **Keep ours.** It is a safety check, not a needs-you signal, and Moonmux has no equivalent |
| 10 | **A sound and a notification, on a change only** | Watch the agent list; alert when an agent turns `blocked` or `done`, but only on a status change it saw happen: never for what the first look after a launch finds, never for a terminal it had not seen before, once per change | [alerts/main.luau:62-110](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L62-L110) (`look`), [:30](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L30) (`TITLES`) | `dc3b848` (2026-11-01, "a sound and a notification when an agent needs you or finishes unseen") | **Yes, already.** A transition is only recorded when the group changed and there was a previous group ([src/ticker.rs:682-686](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/ticker.rs#L682-L686)), and the move into `WaitingOnYou` sends one `Sound::Request` ([src/steps.rs:198-225](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/steps.rs#L198-L225)). So we already never alert on the first look | **Mostly skip.** The one thing we do not have: we diff the *group*, not the raw agent status. An agent that goes `blocked` and back to `idle` inside one group change is invisible to us, and an agent that goes `blocked` while its group stays `WaitingOnYou` alerts only once. See recommendation 1 |
| 11 | **No alert for what is already on screen** | An alert is skipped when the window is active and the agent's pane is visible (or a peek shows it); an agent in another space, tab or session is "elsewhere" and can be included by a setting | [alerts/main.luau:84-92](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L84-L92), the `elsewhere` switch read at [:146-149](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L146-L149) | `dc3b848` (the alerts mod and its `elsewhere` switch) | **No.** herdr-projects notifies regardless of where the pane is ([src/notify.rs:43-51](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/notify.rs#L43-L51)) | **Copy the idea.** It is the cheapest way to cut alert fatigue: do not sound for a pane the user is already looking at |
| 12 | **Click the alert, land on the agent** | The notification's id encodes the terminal address, so a click focuses the pane, or opens a peek when the pane is off screen | [alerts/main.luau:36-46](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L36-L46), [:111-124](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L111-L124); peek path [sidebar/main.luau:447-449](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/sidebar/main.luau#L447-L449) | `dc3b848`, fixed for tmux in `7c3940b` (2026-11-01) | **Yes.** herdr-projects' overview prints `needs you in pane <id>` ([src/overview.rs:166-170](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/overview.rs#L166-L170)) and the mac-ops cockpit overlay jumps to a blocked agent ([coordinator/mods/cockpit/main.js:707-712](https://github.com/shyamsivakumar/mac-ops/blob/93a1467360f27d8d9d7b6e105432a419142c46fa/coordinator/mods/cockpit/main.js#L707-L712)) | **Skip.** We already have the jump; the id-encoding trick only matters for a notification we own |
| 13 | **Time in the current state** | `status_ms` per terminal: when the status last changed, so the sidebar can show "3 min" and sort by it | [tmux/mod.rs:362](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/mod.rs#L362); herdr path [herdr.rs:158-180](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/herdr.rs#L158-L180) (`status_ms`) | `4d06ea0` | **Yes.** `Live::state_secs` is herdr-projects' own bookkeeping: it counts from `thread.last_state_change` while the agent's state still matches `thread.last_state` ([src/thread.rs:651-654](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L651-L654)); the tick resets it on a state change ([src/ticker.rs:648-650](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/ticker.rs#L648-L650)) | **Skip.** Already ours, from our own clock rather than herdr-core's |
| 14 | **Agents started outside the app are seen too** | On herdr-core, every terminal in the session is listed, not only the ones the app started; a label marks which are ours (`ours`). On tmux, each tick lists the panes of the app's own server **and of every other server this user runs** (the default one, and any `tmux -L name`) | [herdr.rs:396-403](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/herdr.rs#L396-L403), [:450](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/herdr.rs#L450); tmux [tmux/mod.rs:4-9](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/mod.rs#L4-L9), [:173](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/mod.rs#L173) | `a571cc5` (herdr-core: every terminal listed, the `ours` label), `4d06ea0` (tmux: every server scanned) | **Partly.** The mac-ops cockpit sees every agent in the herdr session ([cockpit/main.js:707](https://github.com/shyamsivakumar/mac-ops/blob/93a1467360f27d8d9d7b6e105432a419142c46fa/coordinator/mods/cockpit/main.js#L707), via the herdr-app `agents()` list). herdr-projects tracks the threads it launched and the ones it **adopted** (`Kind::Adopted`, [src/thread.rs:40](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L40), `src/adopt.rs`), and it marks a pane holding someone else's agent as not ours ([src/thread.rs:648](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L648)) | **Copy the idea for herdr-projects.** A needs-you overview that ignores an agent the user started by hand will miss the one that actually matters. Decide which surface Shyam reads before doing anything |
| 15 | **A failed agent is a need** | An agent that errored counts as needing you | [sidebar/main.luau:78](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/sidebar/main.luau#L78) (a helper's `error` becomes `blocked`) | `8fcf76a` | **Partly, and we are the weaker one.** herdr-projects maps a thread whose own status is `Failed` to `WaitingOnYou` ([src/thread.rs:585](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L585)), but it does **not** look at an agent reporting `agent_status == "error"`, so such an agent falls through to `Idle` or `Working`. herdr-core does report `error` as a state | **Copy the gap, not the code.** Add `error` to the states that mean needs-you. This is the one detection-side gap we have, and it is not Moonmux's idea (Moonmux only folds a helper's error in) |

## What we would gain, honestly

Three things.

- **The alert discipline** (#10): alert on a witnessed transition, never on
  a first look, never for a pane already on screen. We already do the first
  two; we do not do the third.
- **The seen-and-dismissed state** (#7): a `blocked` the user has already
  looked at should stop being the loudest thing in the overview.
- **`error` means needs you** (#15): the one detection-side gap we have.

Everything else Moonmux does in this area is either a screen scraper we
should not copy (we have the agent's own report), or a presentation choice
we already made, in our own words.

## Recommendations, ordered by value

1. **Treat an agent in `error` as needing you.** herdr-core reports `error`
   as one of its five states, and our `group()` never looks at it, so a
   crashed agent sits in `Idle` until someone opens it. Add `error` beside
   `blocked` in the needs-you test. Source: herdr-core `status.rs:14-30`;
   our gap in `src/thread.rs:565-600`. This is the only detection change the
   comparison turns up.
2. **Diff the agent status, not only the group, before alerting.** We alert
   on a move into `WaitingOnYou` and never on a first look, which is right,
   but the trigger is the group. An agent that goes `blocked` and back to
   `idle` without changing group is silent, and an agent that stays
   `blocked` alerts once, however long it waits. Key the alert on
   `agent_status` plus `state_change_seq` (herdr-core hands both out).
   Source: Moonmux `app/mods/alerts/main.luau:62-110` (`dc3b848`); our
   current trigger at `src/ticker.rs:682-686` and `src/steps.rs:198-225`.
3. **Add a "seen" memory for needs-you.** Remember the turn or
   `state_change_seq` of each terminal the user has already looked at, and
   draw a `blocked` the user has seen as a quieter "waiting" row instead of
   the top needs-you entry. Source: Moonmux `app/mods/sidebar/main.luau:63-72`
   (`a571cc5`). This is the one place where Moonmux is ahead of us, because
   herdr-core gives us `state_change_seq` to key the memory on.
4. **Do not sound for a pane the user is already looking at.** Suppress the
   request sound when the pane holding the blocked agent is the focused pane
   of the active workspace. Source: Moonmux `app/mods/alerts/main.luau:84-92`
   (`dc3b848`). Cheap, and it makes the remaining alerts trustworthy.
5. **Show the time in state next to a needs-you row.** `state_secs` already
   gives "waiting 4 min", which tells the user whether to look now or later.
   Source: Moonmux `src/core/tmux/mod.rs:362`, `src/core/herdr.rs:158-180`.
   We already keep `state_secs` ([src/thread.rs:651-654](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L651-L654)),
   so this is a display change only.
6. **Skip the tmux screen scraper entirely.** It exists because a tmux pane
   has no OSC 7501 report to read. If we ever need tmux panes on the board,
   the honest options are to read the agent's own report through tmux
   (tmux passes OSC through only when it is wrapped in a DCS sequence, so
   this needs proving before anyone relies on it) or to keep using
   herdr-core, which already has the report. No code to copy: Moonmux is MIT
   (Fabien Penso, 2026) and copying it would require keeping the notice, and
   there is nothing here worth the notice.

## License

Moonmux is MIT (Copyright (c) 2026 Fabien Penso). `NOTICE` also credits
`herdr-app` (Apache-2.0) for the Pi icon. herdr-core is Apache-2.0. So
copying is legally allowed with the notice kept, and nothing here needs it:
this ticket copies no code, and the recommendation is not to.

## Method and limits

- Read: Moonmux `src/core/tmux/agents.rs`, `src/core/tmux/mod.rs`,
  `src/core/herdr.rs`, `app/mods/sidebar/main.luau`, `app/mods/alerts/main.luau`,
  `LICENSE`, `NOTICE`; herdr-core `crates/herdr-core/src/status.rs`,
  `crates/herdr-core/src/notes.rs`, `crates/herdr-core/src/terminals.rs`,
  `LICENSE`; herdr-projects `src/thread.rs`, `src/progress.rs`,
  `src/herdr.rs`, `src/overview.rs`, `src/sidebar.rs`, `src/notify.rs`,
  `src/ticker.rs`, `src/steps.rs`, `src/trust_screen.rs`, `src/brief.rs`,
  `src/adopt.rs`; mac-ops `coordinator/mods/cockpit/main.js`.
- Upstream commits were found with `git log -S` on the Moonmux clone
  (shallow, depth 50) and read with `git log --format`. For four rows the
  `git log -S` hit was a later refactor, and the first commit that carried
  the signal was found by reading that commit's diff instead (rows 5, 7, 11
  and 14); those rows name the first commit.
- Not checked: Moonmux's Moonframe upstream (the app framework it draws
  with) beyond the mods in this repo; the herdr-app `agents()` helper that
  the mac-ops cockpit imports (it lives outside this repo, so the cockpit's
  agent list is described from its call site only); the tmux OSC pass-through
  claim in recommendation 6, which is stated as something to prove, not as a
  fact.
- Not run: Moonmux itself. No install, per the brief.

## Corrections after the review

The in-session Opus 5.5 review of the first version of this file (merged as
PR #194) found these wrong, and they are fixed above:

1. Rows 10 and recommendation 1 claimed we alert on state rather than on
   transitions. We do not: the ticker only records a transition when the
   group changed and there was a previous group, and the alert fires once on
   the move into `WaitingOnYou`. Recommendation 1 is now the real gap
   (the `error` state), and the group-versus-status point is recommendation 2.
2. Row 5 credited the screen-hash mechanism to `4d06ea0`; it arrived in
   `e8c3f90`, which replaced tmux's per-window `window_activity`.
3. Row 7 credited `shown_status` to `8fcf76a`; it came with the first
   commit, `a571cc5`.
4. Row 11 credited the `elsewhere` switch to `50f21c0`; it came with the
   alerts mod, `dc3b848`, and the line was wrong (it is read at
   `alerts/main.luau:146-149`).
5. Row 14 credited the herdr-core listing and the `ours` label to `50f21c0`;
   they came with `a571cc5`, and the tmux side came with `4d06ea0`.
6. Row 15 claimed our side handles `error` better than Moonmux. It does not:
   we never look at an agent reporting `error`, which is now recommendation 1.
7. Row 13 said `state_secs` comes from herdr-core's `state_change_seq`. It
   comes from our own `thread.last_state_change`.
8. Recommendation 6 stated the tmux OSC pass-through as fact. It is now
   stated as something to prove.
9. The file now carries real `blob/<sha>` links rather than only
   `path:line` text, as the acceptance asks.
10. The caveat that herdr-projects `main` has moved 585 commits past the
    pinned release and is now a TypeScript app is new, and the recommendations
    say which tree they apply to.
