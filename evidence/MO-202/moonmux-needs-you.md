# MO-202: how Moonmux detects that an agent needs you

Run id: `ticket:shyamsivakumar/mac-ops#167:a3` (run a3 carries runs a1 and a2's
work forward). Refs #167.

Research only. Nothing was installed, nothing was copied out of Moonmux, no
code in any repo changed.

Revision 2 (2026-11-13): corrected after the in-session Opus 5.5 review of
the merged PR #194. What changed is listed under "Corrections after the
review" at the end.

Revision 4 (2026-11-13, run a3): the Moonmux half of the table is unchanged
and re-checked: `moonframehq/moonmux` `main` is still `ef34516` (read with
`git ls-remote` on 2026-11-13), so every Moonmux line reference below still
stands. The **our side** half is new, because revision 3's caveat was wrong.
It said the live `herdr-projects` tree has "no agent-status detection at
all". It does have detection, and it is in TypeScript, in
`server/core/source.ts:228-241` and `server/core/agents.ts:243-247`. The
table and the recommendations therefore now name the live tree, and a new
section, "The live tree compared signal by signal", does the comparison
against the code that actually runs. The old caveat is corrected in place
rather than left standing next to a new table.

Amendment to revision 4 (run a3): the in-session Opus 5.5 review of this
revision found that two rows described `reconcile()` wrongly, that
recommendation 2 overstated its effect, and that four rows were loose about
what the code does. All of it is fixed in place; the list is under
"Corrections in revision 4". One finding changed the substance: the live
tree only knows the agents it launched itself, so Moonmux's "sees agents
started outside the app" is a live gap, not a thing we already have, and it
is now recommendation 1.

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
| herdr-projects (our side, the live tree) | `shyamsivakumar/herdr-projects` | `a862ac947306621bac9e8130db8b3cd6ffead6fe` (`origin/main`, 585 commits past 0.2.34) | 2026-11-01 | MIT, Copyright (c) 2026 Elias Stravik (`LICENSE`) |
| mac-ops (the coordinator panel) | `shyamsivakumar/mac-ops` | `93a1467360f27d8d9d7b6e105432a419142c46fa` | 2026-11-12 | repo licence |

Every link below is a `blob/<sha>/<path>#L<line>` link at the pinned commit,
so the line numbers can be checked without a clone.

The Moonmux checkout was a read-only shallow clone in `$TMPDIR`; nothing was
installed and no Moonmux file was copied into any of our repos.

**A caveat, corrected in revision 4.** `herdr-projects` `origin/main`
(`a862ac9`) is 585 commits ahead of the pinned release and has been
rewritten: there is no `src/thread.rs`, `src/ticker.rs` or any other Rust
file there any more, and the app is now TypeScript ("Shepherdr"). The
rows below describe the released Rust line (0.2.34), because that is the
code the tables were first written against. **The live tree does detect
agent status**, so "the recommendations are about ideas, so they carry over,
but the file and line pointers do not" was too weak: the pointers do exist,
in the live tree, and the new section below points at them.

**What the live tree detects** (`a862ac9`, our own code, no Moonmux
involved): an agent needs the user when there is an open secret, an open
question or an open permission
([server/core/source.ts:232](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L232)),
when the agent's process is gone but its terminal still lives
([:235](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L235)),
when the agent reports `blocked` or holds an open permission
([:237](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L237)),
or when a provider retry has run out
([:239](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L239));
the agent's own hooks set `blocked` on `PermissionRequest`
([server/core/agents.ts:247](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L247)),
`working` on `UserPromptSubmit` and `PreToolUse`
([:244](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L244))
and `idle` on `SessionStart`, `Stop` and `SessionEnd`
([:243](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L243)). A task whose agent finished, or that waits on a log, is `need`
([server/core/tasks.ts:121](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L121)),
drawn as "Needs you"
([:130](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L130)).
An agent state of `error` is still not a need: `status()` reads the state
word at [:236](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L236)
and only `blocked` is a need, so `error` falls through to `idle` at
[:240](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L240).

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

So: on the states an agent reports about itself (blocked, working, done)
our detection matches Moonmux's or beats it, because we read the agent's own
report instead of scraping its screen. Two things Moonmux covers and we do
not: a helper agent that reports `error` (Moonmux turns only a helper's
error into a need, and we turn neither kind into one), and the agents the
user started by hand. Everything else Moonmux does in this area is
presentation, and some of that we already have. The recommendations are
aimed at the live tree, and they say which tree they apply to.

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
| 10 | **A sound and a notification, on a change only** | Watch the agent list; alert when an agent turns `blocked` or `done`, but only on a status change it saw happen: never for what the first look after a launch finds, never for a terminal it had not seen before, once per change | [alerts/main.luau:62-110](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L62-L110) (`look`), [:30](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L30) (`TITLES`) | `dc3b848` (2026-11-01, "a sound and a notification when an agent needs you or finishes unseen") | **Yes, already.** A transition is only recorded when the group changed and there was a previous group ([src/ticker.rs:682-686](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/ticker.rs#L682-L686)), and the move into `WaitingOnYou` sends one `Sound::Request` ([src/steps.rs:198-225](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/steps.rs#L198-L225)). So we already never alert on the first look | **Mostly skip.** The one thing we do not have: we diff the *group*, not the raw agent status. An agent that goes `blocked` and back to `idle` inside one group change is invisible to us, and an agent that goes `blocked` while its group stays `WaitingOnYou` alerts only once. See recommendation 4 (revision 4 numbering) |
| 11 | **No alert for what is already on screen** | An alert is skipped when the window is active and the agent's pane is visible (or a peek shows it); an agent in another space, tab or session is "elsewhere" and can be included by a setting | [alerts/main.luau:84-92](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L84-L92), the `elsewhere` switch read at [:146-149](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L146-L149) | `dc3b848` (the alerts mod and its `elsewhere` switch) | **No.** herdr-projects notifies regardless of where the pane is ([src/notify.rs:43-51](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/notify.rs#L43-L51)) | **Copy the idea, for the Rust line.** It is the cheapest way to cut alert fatigue: do not sound for a pane the user is already looking at. The live tree already has the in-app half of this (live row 11) |
| 12 | **Click the alert, land on the agent** | The notification's id encodes the terminal address, so a click focuses the pane, or opens a peek when the pane is off screen | [alerts/main.luau:36-46](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L36-L46), [:111-124](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/alerts/main.luau#L111-L124); peek path [sidebar/main.luau:447-449](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/sidebar/main.luau#L447-L449) | `dc3b848`, fixed for tmux in `7c3940b` (2026-11-01) | **Yes.** herdr-projects' overview prints `needs you in pane <id>` ([src/overview.rs:166-170](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/overview.rs#L166-L170)) and the mac-ops cockpit overlay jumps to a blocked agent ([coordinator/mods/cockpit/main.js:707-712](https://github.com/shyamsivakumar/mac-ops/blob/93a1467360f27d8d9d7b6e105432a419142c46fa/coordinator/mods/cockpit/main.js#L707-L712)) | **Skip.** We already have the jump; the id-encoding trick only matters for a notification we own |
| 13 | **Time in the current state** | `status_ms` per terminal: when the status last changed, so the sidebar can show "3 min" and sort by it | [tmux/mod.rs:362](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/mod.rs#L362); herdr path [herdr.rs:158-180](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/herdr.rs#L158-L180) (`status_ms`) | `4d06ea0` | **Yes.** `Live::state_secs` is herdr-projects' own bookkeeping: it counts from `thread.last_state_change` while the agent's state still matches `thread.last_state` ([src/thread.rs:651-654](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L651-L654)); the tick resets it on a state change ([src/ticker.rs:648-650](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/ticker.rs#L648-L650)) | **Skip.** Already ours, from our own clock rather than herdr-core's |
| 14 | **Agents started outside the app are seen too** | On herdr-core, every terminal in the session is listed, not only the ones the app started; a label marks which are ours (`ours`). On tmux, each tick lists the panes of the app's own server **and of every other server this user runs** (the default one, and any `tmux -L name`) | [herdr.rs:396-403](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/herdr.rs#L396-L403), [:450](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/herdr.rs#L450); tmux [tmux/mod.rs:4-9](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/mod.rs#L4-L9), [:173](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/tmux/mod.rs#L173) | `a571cc5` (herdr-core: every terminal listed, the `ours` label), `4d06ea0` (tmux: every server scanned) | **Partly.** The mac-ops cockpit sees every agent in the herdr session ([cockpit/main.js:707](https://github.com/shyamsivakumar/mac-ops/blob/93a1467360f27d8d9d7b6e105432a419142c46fa/coordinator/mods/cockpit/main.js#L707), via the herdr-app `agents()` list). herdr-projects tracks the threads it launched and the ones it **adopted** (`Kind::Adopted`, [src/thread.rs:40](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L40), `src/adopt.rs`), and it marks a pane holding someone else's agent as not ours ([src/thread.rs:648](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L648)) | **Copy the idea for herdr-projects.** A needs-you overview that ignores an agent the user started by hand will miss the one that actually matters. Decide which surface Shyam reads before doing anything |
| 15 | **A failed agent is a need** | An agent that errored counts as needing you | [sidebar/main.luau:78](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/sidebar/main.luau#L78) (a helper's `error` becomes `blocked`) | `8fcf76a` | **Partly, and we are the weaker one.** herdr-projects maps a thread whose own status is `Failed` to `WaitingOnYou` ([src/thread.rs:585](https://github.com/shyamsivakumar/herdr-projects/blob/4e4548c3c43888e6be1c96906215998f07dc63f0/src/thread.rs#L585)), but it does **not** look at an agent reporting `agent_status == "error"`, so such an agent falls through to `Idle` or `Working`. herdr-core does report `error` as a state | **Copy the gap, not the code.** Add `error` to the states that mean needs-you. This is the one detection-side gap we have, and it is not Moonmux's idea (Moonmux only folds a helper's error in) |

## The live tree compared signal by signal

The same fifteen signals, against the code that actually runs today
(`herdr-projects` `a862ac9`, TypeScript). "Live tree" is the column to read
before acting on a recommendation: revision 3's recommendations were written
against the released Rust line and are re-targeted below.

| # | Signal | Live tree (`a862ac9`) | Verdict |
| --- | --- | --- | --- |
| 1 | The agent exists | Agents come from the app's own launch records. `reconcile()` walks those records and attaches the herdr-core terminal that carries this launch's labels ([server/core/agents.ts:63-69](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L63-L69), the terminal match at [:56-62](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L56-L62)), and the refresh calls it ([server/core/source.ts:223](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L223)) | **Skip.** No process walking needed |
| 2 | Needs you (blocked) | `status()` returns `need` for an open secret, question or permission ([server/core/source.ts:232](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L232)), for a dead agent whose terminal lives ([:235](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L235)), for the state word `blocked` or an open permission ([:237](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L237)), and for an exhausted provider retry ([:239](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L239)). The agent's own `PermissionRequest` hook sets `blocked` ([server/core/agents.ts:247](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L247)) | **Skip.** Ours, and by better routes than a screen scraper |
| 3 | Working | `working` and `starting` are `work` ([server/core/source.ts:240](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L240)); the hooks set `working` on `UserPromptSubmit` and `PreToolUse` ([server/core/agents.ts:244](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L244)) | **Skip.** Same reason |
| 4 | Only the foot of the screen counts | No screen is read for needs-you in the live tree | **Skip.** Only meaningful for a scraper |
| 5 | Still printing | A finished terminal is `idle` ([server/core/source.ts:234](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L234)), and a task whose agent finished is `need` ([server/core/tasks.ts:121](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L121)) | **Skip.** The finished agent is the news, which is the point |
| 6 | The state set | `need`, `ready`, `merging`, `work`, `idle`, `queued`, `todo`, `done`, `off` ([shared/types.ts:7](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/shared/types.ts#L7)) | **Skip.** Richer than Moonmux's four states, but with no `error` of its own: see row 15 |
| 7 | Done collapses to idle once you looked at it | **No.** `keptTags` drops the chats open in the app right now ([shared/alerts.ts:31-36](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/shared/alerts.ts#L31-L36), used at [plugins/alerts/client.tsx:45](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/plugins/alerts/client.tsx#L45) with the visible chats from [src/kernel.ts:1141](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/src/kernel.ts#L1141)), but it keeps no memory of a needs-you the user looked at and then closed | **Copy the idea.** The memory is the missing half |
| 8 | A helper's result belongs to its parent | **Partly.** The live tree drops a helper's lifecycle events so they cannot overwrite its parent's status or session ([server/core/agents.ts:237](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L237)), but nothing turns a helper's `error` into a need. Moonmux does ([sidebar/main.luau:76-83](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/app/mods/sidebar/main.luau#L76-L83)) | **Partly ours.** The parent rule is ours; the helper's error is not |
| 9 | One urgency order, one place | What waits on you is filtered, not ordered: `waiting()` keeps the tasks whose status is `need` or `ready` and the coordinator's open questions ([shared/alerts.ts:24-29](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/shared/alerts.ts#L24-L29)), and the app icon counts exactly those. The order the sidebar draws them in was not checked in this pass | **Skip.** The filter is ours; the ordering itself was not read |
| 10 | A sound and a notification, on a change only | Alerts go out as push when an `alert` event fires ([server/app.ts:103-111](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/app.ts#L103-L111)), and a task that turns `need` raises a `needs-you` event on that change ([server/core/automations.ts:146](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/automations.ts#L146), checked at [server/core/news.ts:63](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/news.ts#L63)) | **Mostly skip.** It is change-based already; the gap is a `blocked` that clears inside `need`, which no status change reports |
| 11 | No alert for what is already on screen | **Partly.** In the app, `keptTags` keeps an alert only when its chat is not among the chats visible in the window ([shared/alerts.ts:31-36](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/shared/alerts.ts#L31-L36), [plugins/alerts/client.tsx:45](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/plugins/alerts/client.tsx#L45), [src/kernel.ts:1141](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/src/kernel.ts#L1141)). The push path is coarser: it skips a whole device whose app is visible, not the one agent whose chat is visible ([server/app.ts:109-111](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/app.ts#L109-L111), [server/push.ts:53-58](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/push.ts#L53-L58)) | **Partly done.** The in-app rule is Moonmux's; the push rule is per device. Revision 3's recommendation 4 therefore no longer holds for the live tree |
| 12 | Click the alert, land on the agent | The alert carries `go: { place, task }` ([shared/alerts.ts:97](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/shared/alerts.ts#L97)) and the `focus` of the message to open, for a done task or an open card ([:101](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/shared/alerts.ts#L101), [:108](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/shared/alerts.ts#L108)) | **Skip.** Already ours |
| 13 | Time in the current state | **Partly.** A task carries an age ([server/core/tasks.ts:123-128](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L123-L128)); an agent has no time-in-state next to its status | **Copy the idea.** Display only, on the agent row |
| 14 | Agents started outside the app are seen too | **No.** The live tree knows only the agents it launched itself: `reconcile()` walks its own `agent` records ([server/core/agents.ts:63-69](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L63-L69)), and `terminal()` matches only a herdr-core terminal labelled with this installation and this launch ([:56-62](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L56-L62)). An agent the user started by hand has no record and no label match, so it is never seen, and the live tree has no adopt path for a foreign agent (its `adopt` is about moving a task's worktree, [server/core/task-relocation.ts:12](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/task-relocation.ts#L12)). The Rust line does adopt such panes (`Kind::Adopted`) | **Copy the idea.** The gap is in the live tree too. It is recommendation 1 |
| 15 | A failed agent is a need | **No.** The state word is read at [server/core/source.ts:236](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L236) and only `blocked` is a need, so herdr-core's `error` state falls through to `idle` at [:240](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L240). A task whose agent is in that state then reads as `work` ([server/core/tasks.ts:121](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L121)), unless the agent's log shows a closed turn with nothing open and no background job running, which makes the task `need` ([tasks.ts:118](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L118), [server/core/logs.ts:71-87](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/logs.ts#L71-L87)) | **The gap, in the live tree.** Recommendation 2 |

Not checked in the live tree in this pass: the Rust line's trust-screen
check (`src/trust_screen.rs`), which has no counterpart in the TypeScript
tree that this pass read. The live tree handles permissions through its own
permission records rather than by reading a pane's screen
([server/core/source.ts:232](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L232)),
which is the better route, but this file does not claim the trust-screen
check has a live-tree equivalent.

## What we would gain, honestly

Against the live tree, four things.

- **The agents the user started by hand** (#14): the live tree only knows
  the agents it launched, so a hand-started agent that blocks never shows
  up.
- **The seen-and-dismissed state** (#7): the live tree silences what is on
  screen right now, but a `blocked` the user looked at and then closed comes
  back at full volume.
- **A new `blocked` inside a task that is already `need`** (#10): no fresh
  alert, because the task's status did not change.
- **`error` means needs you** (#15): an agent that is alive and reports
  `error` before its logged turn ends reads as working, in the live tree as
  in the Rust line.

The alert discipline of #10 is already ours (a change raises an event, a
first look does not), and #11 is ours in the app but only per device for
push, so both recommendations from revision 3 that pointed at them are now
narrower or gone.

Everything else Moonmux does in this area is either a screen scraper we
should not copy (we have the agent's own report and its own hooks), or a
presentation choice we already made, in our own words.

## Recommendations, ordered by value

1. **See the agents the user started by hand.** The live tree knows only
   the agents it launched: `reconcile()` walks its own records and
   `terminal()` matches only a terminal carrying this launch's labels
   ([server/core/agents.ts:63-69](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L63-L69),
   [:56-62](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/agents.ts#L56-L62)).
   An agent started outside the app never appears, so the one the user
   started by hand and that now waits on them is invisible. Moonmux lists
   every terminal in the session and marks which ones are "ours"
   ([src/core/herdr.rs:396-403](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/herdr.rs#L396-L403),
   [:450](https://github.com/moonframehq/moonmux/blob/ef345161a9adcd5e5f1ea0e9b8e0466607f3d24f/src/core/herdr.rs#L450)).
   Source: Moonmux `a571cc5`; the Rust line's adopt path (`Kind::Adopted`)
   shows we had this once and lost it in the rewrite.
2. **Treat an agent whose state is `error` as needing you.** The state word
   is read at
   [server/core/source.ts:236](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L236)
   and only `blocked` is a need, so an agent that is alive and reports
   `error` falls through to `idle` at
   [:240](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L240).
   A crashed process is already caught (a dead pid is a need at
   [:235](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L235),
   a finished terminal makes the task `need` at
   [server/core/tasks.ts:121](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L121)),
   and provider failures have their own path
   ([:238-239](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L238-L239)).
   The gap is an agent that is alive and reports an error before its log
   shows a closed turn: until then the task reads as `work`
   ([server/core/tasks.ts:121](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L121)),
   and only when the log shows a closed turn with nothing open and no
   background job running does it become `need`
   ([tasks.ts:118](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L118),
   [server/core/logs.ts:71-87](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/logs.ts#L71-L87)).
   Add `error` beside `blocked` at
   [:237](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L237)
   (and, in the Rust line, beside `blocked_long` at `src/thread.rs:590`).
3. **Keep a "seen" memory for needs-you.** The live tree silences what is
   visible in the window right now
   ([shared/alerts.ts:31-36](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/shared/alerts.ts#L31-L36))
   but forgets it when the chat closes. Remember the state-change sequence
   of each terminal the user has already looked at, and draw a `blocked`
   the user has seen as a quieter "waiting" row instead of the top
   needs-you entry. Source: Moonmux
   `app/mods/sidebar/main.luau:63-72` (`a571cc5`); herdr-core hands out
   the sequence to key the memory on.
4. **Alert on the agent state change, not only on the task status change.**
   A task that turns `need` raises a `needs-you` event on that change
   ([server/core/automations.ts:146](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/automations.ts#L146)),
   which is right. What no status change reports is a new `blocked`
   arriving while the task is already `need`: the task's status did not
   change, so no fresh alert goes out. (A `blocked` that clears needs no
   alert.) Key the alert on the agent's state change sequence as well.
   Source: Moonmux `app/mods/alerts/main.luau:62-110`
   (`dc3b848`).
5. **Show the time in the state next to a needs-you row.** The live tree
   has a task age ([server/core/tasks.ts:123-128](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L123-L128))
   but no time-in-state for an agent, and "waiting 4 min" is what tells the
   user whether to look now or later. Source: Moonmux
   `src/core/tmux/mod.rs:362`, `src/core/herdr.rs:158-180`. Display only.
6. **Skip the tmux screen scraper entirely.** It exists because a tmux pane
   has no OSC 7501 report to read. If we ever need tmux panes on the board,
   the honest options are to read the agent's own report through tmux
   (tmux passes OSC through only when it is wrapped in a DCS sequence, so
   this needs proving before anyone relies on it) or to keep using
   herdr-core, which already has the report. No code to copy: Moonmux is MIT
   (Fabien Penso, 2026) and copying it would require keeping the notice, and
   there is nothing here worth the notice.

One more thing to check, not a recommendation: the mac-ops coordinator panel
reads herdr-app's agent list
([coordinator/mods/cockpit/main.js:707](https://github.com/shyamsivakumar/mac-ops/blob/93a1467360f27d8d9d7b6e105432a419142c46fa/coordinator/mods/cockpit/main.js#L707))
and works out its own grouping, while the live tree now owns the detection
([server/core/source.ts:228-241](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/source.ts#L228-L241)).
Two detectors will drift. Check first whether the panel already reads that
status; this file does not claim it does or does not.

## License

Moonmux is MIT (Copyright (c) 2026 Fabien Penso). `NOTICE` also credits
`herdr-app` (Apache-2.0) for the Pi icon. herdr-core is Apache-2.0.
herdr-projects (the live tree, `a862ac9`) is MIT (Copyright (c) 2026 Elias
Stravik). So copying is legally allowed with the notice kept, and nothing
here needs it: this ticket copies no code, and the recommendation is not to.

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
- Read for revision 4: `herdr-projects` `origin/main` (`a862ac9`),
  `server/core/source.ts`, `server/core/agents.ts`, `server/core/tasks.ts`,
  `server/core/automations.ts`, `server/core/news.ts`, `server/app.ts`,
  `server/push.ts`, `shared/alerts.ts`, `shared/attention.ts`,
  `shared/types.ts`, `src/attention.ts`, `LICENSE`; and
  `moonframehq/moonmux` `main` re-read with `git ls-remote` (still
  `ef34516`).
- Not run: Moonmux itself. No install, per the brief.
- Not checked in the live tree: the trust-screen check from the Rust line,
  and whether the mac-ops cockpit panel already reads the live tree's `need`
  status. The closing note under the recommendations says to check before
changing anything.

## Corrections after the review

The in-session Opus 5.5 review of the first version of this file (merged as
PR #194) found these wrong, and they are fixed above:

1. Rows 10 and recommendation 1 claimed we alert on state rather than on
   transitions. We do not: the ticker only records a transition when the
   group changed and there was a previous group, and the alert fires once on
   the move into `WaitingOnYou`. Recommendation 1 is now the real gap
   (the `error` state), and the group-versus-status point is recommendation 2.
   (In revision 4's numbering, with the outside-agents idea put first, the
   `error` gap is recommendation 2 and the group-versus-status point is
   recommendation 4.)
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
   we never look at an agent reporting `error`, which is now the error
   recommendation (recommendation 2 in revision 4's numbering).
7. Row 13 said `state_secs` comes from herdr-core's `state_change_seq`. It
   comes from our own `thread.last_state_change`.
8. Recommendation 6 stated the tmux OSC pass-through as fact. It is now
   stated as something to prove.
9. The file now carries real `blob/<sha>` links rather than only
   `path:line` text, as the acceptance asks.
10. The caveat that herdr-projects `main` has moved 585 commits past the
    pinned release and is now a TypeScript app is new, and the recommendations
    say which tree they apply to.

## Corrections in revision 4 (run a3)

Revision 3's caveat said the live tree has "no agent-status detection at
all". That was wrong, and the recommendations were written as if it were
true. Fixed above:

1. The live tree does detect: `status()` in
   `server/core/source.ts:228-241` returns `need` for an open secret,
   question or permission, a dead agent with a live terminal, the state
   word `blocked`, an open permission, or an exhausted provider retry; the
   agent hooks set `blocked`, `working` and `idle` in
   `server/core/agents.ts:243-247`.
2. A new section, "The live tree compared signal by signal", compares all
   fifteen signals against `a862ac9` with `blob/<sha>` links. (The Rust
   table has sixteen rows: the same fifteen plus row 9a, the trust-screen
   check Moonmux has no counterpart for.)
3. Two recommendations from revision 3 changed. The "do not sound for a
   pane the user is already looking at" recommendation is already done in
   the app in the live tree (`shared/alerts.ts:31-36`,
   `plugins/alerts/client.tsx:45`) and only per device for push
   (`server/app.ts:109-111`), so it no longer applies there as a whole.
   The "diff the agent status, not only the group" recommendation became
   narrower: the live tree already raises a `needs-you` event on a status
   change, and what is left is a new `blocked` arriving while the task is
   already `need`.
4. The Moonmux half of the file is unchanged and re-verified: `main` is
   still `ef34516`.
5. `herdr-projects` at `a862ac9` is MIT (Copyright (c) 2026 Elias Stravik),
   now named in the licence section next to the other two.

### The run-a3 reviewer round

The in-session Opus 5.5 review of revision 4 returned `VERDICT: FAIL` with
eight findings. All eight are fixed above:

1. **Row 14 was wrong and it hid a recommendation.** It said the live tree
   "reconciles every agent herdr-core reports". It does not: `reconcile()`
   walks the app's own `agent` records
   (`server/core/agents.ts:63-69`) and `terminal()` matches only a
   herdr-core terminal carrying this installation's and this launch's
   labels (`:56-62`). The row now says "No", and the idea is
   recommendation 1.
2. **Row 1 described the same code wrongly.** It said agents come from
   herdr-core and are reconciled on every refresh. They come from the app's
   own launch records; the refresh only attaches terminals to them. Fixed.
3. **The error recommendation overstated its effect.** "A crashed agent reads as
   idle" was wrong: a crashed process leaves a dead pid (a need at
   `source.ts:235`) or a finished terminal (the task becomes `need` at
   `tasks.ts:121`), and provider failures have their own path
   (`source.ts:238-239`). The gap is an agent that is alive and reports
   `state=error`. Reworded. (That item is recommendation 2 in revision 4's
   numbering.)
4. **Row 9 called a filter an order.** `waiting()`
   (`shared/alerts.ts:24-29`) filters tasks by status; it orders nothing.
   The row now says so and says that the sidebar's own order was not read.
5. **Row 12's shape was off.** `go` is `{ place, task }`
   (`shared/alerts.ts:97`); `focus` is added at `:101` and `:108`. Fixed.
6. **A hook event was missing.** `agents.ts:243` sets `idle` on
   `SessionStart` as well as `Stop` and `SessionEnd`. Added.
7. **Rows 7 and 11 overstated `keptTags`.** The in-app rule is per chat
   (`plugins/alerts/client.tsx:45` with `visibleChats` from
   `src/kernel.ts:1141`); the push skip is per device
   (`server/app.ts:109-110` skips any device whose app is visible). Live
   row 11 now says "Partly" and live row 7 keeps its "No", with the
   wording corrected; revision 3's recommendation 4 is gone.
8. **A stale cross-reference.** The revision 2 corrections list pointed at
   "recommendation 2" for the group-versus-status point; in revision 4's
   numbering it is recommendation 4. The list now says so.

The reviewer also confirmed, by reading the code at the pinned commits: the
Moonmux upstream pin (`ef34516`) is still `main`; the herdr-projects line
numbers cited in the new table are right; the `error` gap is real
(`CoreTerminal.status.state` is a plain `string` at
`server/core/protocol.ts:15`, and `status()` treats only `blocked` as a
need); the licences are as named; the diff touches only the two evidence
files, copies no Moonmux code and installs nothing; and the acceptance
criteria are met.

### The run-a3 re-check round

A second in-session Opus 5.5 round re-read the fixed branch and returned
`VERDICT: FAIL` again, on stale cross-references rather than on code
facts: it verified all eight code fixes above, then found that the text
still pointed at the wrong recommendation numbers in six places, and made
four smaller accuracy points. All are fixed:

1. Live row 15 said "Recommendation 1" for the `error` gap; it is
   recommendation 2 in revision 4's numbering. Fixed.
2. Rust row 10 said "See recommendation 1" for the group-versus-status
   point; it is recommendation 4. Fixed.
3. Two places said "Recommendation 5 says to check" about the mac-ops
   cockpit panel; that check is the unnumbered closing note. Fixed.
4. Revision 2's correction 6 called the `error` gap "recommendation 1";
   it now gives the revision 4 number. Fixed.
5. The claim that "both rows now say 'Partly'" was wrong: live row 11 says
   "Partly" and live row 7 keeps its "No". Fixed.
6. The reviewer's own numbering complaint about the fix list ("the error
   recommendation") was applied there too.
7. The `error` gap is narrower than written: a task whose agent reports
   `error` reads as `work` while the agent's logged turn is still running
   ([server/core/tasks.ts:121](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L121)),
   and only a closed turn with nothing open and no background job makes it
   `need`
   ([tasks.ts:118](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/tasks.ts#L118),
   [server/core/logs.ts:71-87](https://github.com/shyamsivakumar/herdr-projects/blob/a862ac947306621bac9e8130db8b3cd6ffead6fe/server/core/logs.ts#L71-L87)).
   Row 15 and recommendation 2 now say so.
8. Live row 8 said Moonmux's helper rule is "already ours"; the live tree
   drops helper events but never turns a helper's `error` into a need. The
   row now says "Partly". Fixed.
9. Recommendation 4 said the missed case was a `blocked` that clears; the
   case that raises no fresh alert is a new `blocked` arriving while the
   task is already `need`. Reworded.
10. "What we would gain" listed three things and left out the alert case;
    it now lists four, matching the recommendations.

### The run-a3 third round

A third in-session Opus 5.5 round checked the cross-references (all
correct) and the two narrowed code claims, and returned `VERDICT: FAIL` on
one wrong citation, plus four smaller points. All are fixed:

1. **A wrong function was cited in four places.** The text said that once
   the agent's logged turn has ended the task becomes `need`, citing
   `server/core/logs.ts:59-69`. That range is `providerTurn()`. It does
   feed the task status, but not through `waiting`: its "cut" becomes the
   provider-retry row (`server/core/provider-retries.ts:40-56`), and that
   row reaches the status through `providerRetries.get()`
   (`server/core/source.ts:238-239`, `server/core/tasks.ts:119-121`). What
   decides `waiting` is `waiting()` at `server/core/logs.ts:71-87`: it is
   true when the agent's role is `task` (`:73`), the log has caught up
   (`:78`), a turn has closed, no turn is open and no background job is
   running (`activityOf` at `server/activity.ts:42`), and before the log
   cursor has loaded it falls back to a saved snapshot (`:74-77`). All
   four citations now name `logs.ts:71-87`, and the prose says what
   `waiting()` checks.
2. **A stale cross-reference in `decisions.md`.** Its review-round list
   still gave the revision 2 numbering. It now carries the revision 4
   numbers, like the evidence file.
3. **A reach statement that contradicted the recommendations.**
   `decisions.md` said only the alert discipline and the seen state were
   worth copying, both presentation. It now says that was true for
   revision 1 and that revision 4 found two detection gaps as well.
4. **The short answer overstated the comparison.** It said our detection
   is at least as good as Moonmux's and that only presentation ideas were
   missing. This round removed the second half of the overclaim and left
   "at least as good as Moonmux's on every signal Moonmux has", which was
   still false; the fourth round finished the job (see its list below).
5. **A small overclaim in `decisions.md`.** It said every recommendation
   names a file and a line; recommendation 6 names none, because it says
   what not to copy. It now says five of six do.

### The run-a3 fourth round

A fourth in-session Opus 5.5 round checked the new citation (right) and
every cross-reference (right), and returned `VERDICT: FAIL` on one
overstatement that was still standing, one wrong claim about a function,
and three smaller points. All are fixed:

1. **The short answer still overstated our detection.** It said our
   detection is "at least as good as Moonmux's on every signal Moonmux
   has", which is false: Moonmux's hand-started-agents signal (row 14) and
   its helper-error rule (row 8) are not covered by us in either tree. The
   round-3 fix had removed only the second half of the overclaim. It now
   says our detection matches or beats Moonmux's on the states an agent
   reports about itself (blocked, working, done), and names the two things
   Moonmux covers and we do not: a helper agent that reports `error`
   (Moonmux turns only a helper's error into a need, and we turn neither
   kind into one), and the agents the user started by hand.
2. **A wrong claim about `providerTurn()`.** It said the "cut" it returns
   does not feed the task status. It does, indirectly: the cut becomes the
   provider-retry row (`server/core/provider-retries.ts:40-56`), which
   reaches the status through `providerRetries.get()`
   (`server/core/source.ts:238-239`, `server/core/tasks.ts:119-121`). What
   `providerTurn()` does not do is decide `waiting`. The text now says
   that.
3. **The `waiting()` summary was incomplete.** It now also says the agent's
   role must be `task` (`server/core/logs.ts:73`) and that, before the log
   cursor has loaded, `waiting()` falls back to a saved snapshot
   (`:74-77`).
4. **A count.** The Rust table has sixteen rows, the fifteen signals plus
   row 9a, the trust-screen check. The count is now said as such.
5. The reframe sentence went away with fix 1.

### The run-a3 fifth round

A fifth in-session Opus 5.5 round checked the `providerTurn()` and
`waiting()` claims (right), every cross-reference (right) and the scope
(clean), and returned `VERDICT: FAIL` on one sentence about Moonmux that
the Moonmux source does not support, plus two smaller points. All are
fixed:

1. **The short answer overstated what Moonmux does with `error`.** It said
   "an agent that reports `error` (a helper's error is not a need for us
   either)", which reads as if Moonmux treats any agent's `error` as a
   need. At `ef34516` it does not: `helper_status()` turns `error` into
   `blocked` only for a helper
   (`app/mods/sidebar/main.luau:76-79`), `shown_status()` returns `error`
   unchanged for any other agent (`:63-72`), and `error` is in neither
   `LOUDNESS` nor `SECTIONS` (`:40-42`), so it is never drawn as "Needs
   you". The sentence now says that Moonmux turns only a helper's error
   into a need and we turn neither kind into one.
2. **An em dash** in that same sentence, which the voice rules ban. It is
   gone; the sentence uses parentheses.
3. **The third-round list described the fourth-round fix.** Its item 4
   said "This round fixed it properly" and then called the round-3 version
   of the fix incomplete, which is the fourth round's work. Item 4 now
   describes what round 3 did, and the fourth-round list carries the rest.

The reviewer also confirmed what was right: the `providerTurn()` and
`waiting()` citations, every recommendation cross-reference, the row
counts, and that only the two evidence files changed, with nothing
installed, copied or read that was out of bounds.
