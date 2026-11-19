# Agent tickets: a Linear-like backlog for the Herdr board

Revision 2, 2026-11-09. Replaces the local-files draft (revision 1). Nothing is built yet.

## Goal

Shyam manages every ticket for his personal projects, including backlog ones, as markdown he can edit anywhere, and picks a builder model and a reviewer model per ticket. The shape follows Linear's agent model: a human owns the issue, an agent is its delegate, and the agent's work shows as activity on the issue.

Decisions so far (Shyam):

- Linear-like, not a new Linear workspace (no webhook, no tunnel).
- A ticket's own builder or reviewer overrides routing for that ticket; routing stays the default.
- Ascend work (the `slash-eureka` repos: AUH, ascend-mcp, data-ops, dbt, omni) keeps its tickets in Ascend's Linear. T3 threads for that work carry a link to the Linear issue; nothing about them moves.
- Personal projects need the new structure. Revision 1's local markdown files are not the right home.

## Where personal tickets live

Hub projects with a personal GitHub home (checked 2026-11-09, all private with issues enabled): CineJar, cairn, catalouge, fantasy-football-toolkit, sams-llm-wiki, mac-ops, openscan, qabot, recoup, scrapers, scripture-scroll, strategy-replay-workbench, tunerise, strata, and digitized/Concerning (write access). Repos with no remote (proof-repo, bench-*) are test fixtures and get no tickets.

- Each ticket is a GitHub issue in its project's own repo.
  - PRs link and close issues natively with `Fixes #n`.
  - An agent in that repo's worktree reads its ticket with `gh issue view n`.
  - GitHub numbers issues atomically per repo.
- Work that spans repos: a parent issue in the main repo, with linked issues in the others (sub-issues or "blocked by" links).
- Fields are labels, the same set in every repo: `stage:backlog`, `stage:todo`, `stage:hold`, `priority:1` to `priority:4`, `builder:<model>`, `reviewer:<model>` and `type:<taskType>`. A one-time script creates them in each repo.
- `stage:hold` is Shyam's hold. It is not a stage: the ticket keeps its own stage, and `ticket start` refuses a held ticket until Shyam removes the label.
- The board finds every repo's tickets with one search: `gh search issues --owner shyamsivakumar --state open label:stage:todo` (and the same for backlog), plus the same search with `--owner digitized` for Concerning. No GitHub Project and no `project` token scope; the Herdr board is the cross-repo view.
- GitHub allows two labels of one kind (two `builder:` labels). The dispatcher refuses a ticket with more than one builder, reviewer, priority or stage label and shows why on the card.

A single central `tickets` repo was considered and rejected. Its only advantages were keeping tickets away from colleagues (not an issue for private personal repos) and holding tickets for repos without a remote (only test fixtures). It loses native PR links and puts tickets away from the code.

## Why GitHub Issues over local files

Revision 1 was critiqued by GPT-6.1 Sol (MO-137) and GLM 5.3 (MO-138): `~/Code/coordinator/evidence/local-tickets-design-critiques-2026-11-09.md`. Several of their risks come from local files themselves.

| Risk in revision 1 | Local files | GitHub Issues |
| --- | --- | --- |
| Two writers on one file (Coordinator and board) | Needs a shared front-matter writer and compare-and-swap | GitHub stores the issue; each edit is its own API call and history entry |
| "Kept in git" protects nothing; the Coordinator may not commit | Needs a commit job | Every body edit is kept in the issue's history |
| Key minting race | One minter plus a lock | GitHub numbers issues atomically; the Coordinator still mints the key in the title |
| Editing a ticket | Only on this Mac | GitHub editor on web and phone; `gh issue edit` |
| Blockers and parents | A custom field | Native dependencies (GA, REST) and sub-issues; `gh issue list --json blockedBy,parent,subIssues,issueType` (gh 2.98 here) |
| Offline | Works | Board shows its last cached list; creating and editing need the network |

## Ownership: intent on the issue, execution on the thread

| Data | Owner | Writers |
| --- | --- | --- |
| Key, title, body (ticket template), type label, blockers, parent | Issue | Coordinator creates; Shyam edits anywhere |
| Priority, Builder, Reviewer, Stage (Backlog, Todo) | Labels | Shyam; Coordinator on create; Coordinator on escalation |
| Thread ids, dispatched body hash, request id | One issue comment written at launch, with a machine-readable line (`<!-- coordinator-ticket {"thread":…,"hash":…,"requestId":…} -->`) | The dispatcher only |
| Status, runs, actual models, PRs, verdict | T3 thread | T3 |
| Closed (done or cancelled) | Issue state | Coordinator after the gate passes; Shyam |

A fact lives in one place. The board reads both sides and shows disagreement (for example a closed issue with a running thread) as a red chip. Nothing syncs by last writer.

## Keys

- The Coordinator mints `<KEY>-<n>` as today and puts it first in the issue title (`SRW-760 · Bot 2 lane system design`). The `repo#number` is the stable id; the key is what threads and review titles use, so existing grouping keeps working.
- An issue Shyam opens without a key is a draft. The Coordinator keys it when it triages it.
- A ticket opened by tooling carries a key from the moment it is opened: the key is mandatory and `ticket open` is the one minter (MO-370). `ticket open --repo <owner/repo> --title "<title>"` reads the repo's key from `~/.coordinator/tickets.json`, mints the number one past the repo's highest key (open and closed issues, so a number is never reused), and opens the issue as `<KEY>-<n> · <title>`. A title that already starts with the repo's key is kept as it is and refused when that key is taken. `--require-key` refuses a keyless title instead of minting one. `--dry-run` prints the title the call would use and opens nothing. One lock per repo keeps two opens from minting the same key.

## Dispatch (one path)

Start, from the board or the Coordinator, runs one command: `coordq start` with
`{projectId, taskType, message, clientRequestId: "ticket-<repo>#<n>-<bodyhash>", modelSelection?}`.

- `message` is the issue body at that moment plus a first line naming the issue URL.
- `clientRequestId` makes a retry find the existing thread (`tool_thread_launch` returns it for a known request id) instead of starting a second agent.
- The dispatcher refuses to start, with the reason on the card, when a blocker is open, a required template section is empty, the key is missing, or the model check fails.
- A merged pull request that says `Refs #<ticket>` refuses the start only when it delivered: it changed a file outside `evidence/`, `docs/` and `*.md`, or a gate comment on the ticket says `VERDICT: PASS. Merged via #N`. A merge that changed only plans and documents reports `merged PR #N changed only docs; not treated as delivery` and the start goes ahead, so a plan PR cannot keep a ticket refused after the work moved to an unmerged branch. Agent rules and prompts are not documents for this rule: a `.md` under `.agents/`, `coordinator/config/` or `runtime/`, or one named `AGENTS.md`, `CLAUDE.md` or `SKILL.md`, is delivery. An unreadable, empty or truncated file list counts as delivery.
- Queue and cap (6) stay in `coordq`. The board never calls `t3_thread_launch`.

## Model choice per ticket

- Each role resolves to the ticket field, else the model `coordq` maps from taskType. `taskType` is always passed too.
- Field values map through one table to `{instanceId, model}`; an unknown value refuses the start.
- Vendor rule: the gate reviewer's vendor differs from the builder's actual vendor. Checked at start against the requested models, and again before the gate launches against the actual author models from the run records, including fallbacks. Same-vendor pairs and Cursor gates are refused. Panels keep "no fallback; a seat that fell back does not count".
- A pinned builder whose provider is out waits in the queue with a red chip; it does not quietly use routing. The card shows the actual model once the thread runs.
- Escalation wins over a pin: after two failed gates the Coordinator swaps the `builder:` label and comments why.

## Edits after start

The agent saw the body at launch. When the body's hash no longer matches the launch comment, the card shows "changed since launch". Applying it sends the diff as a follow-up through `coordq start` with the thread id. A change to the acceptance section invalidates an earlier gate verdict.

## Board changes (v1)

- Backlog column: open issues labelled `stage:backlog` or `stage:todo` across the personal repos, by priority then age. One search per refresh, cached; the last copy shows when offline.
- Ticket view: renders the issue body; Priority, Builder and Reviewer pickers that swap labels; "Edit on GitHub"; Start (dispatch above); blockers with their state.
- Cards: priority, builder and reviewer chips; the effective model and a "fell back" chip once running; "changed since launch"; a disagreement chip; a Linear link on Ascend cards.
- No embedded body editor in v1.

## Coordinator changes

- Create personal-project tickets as issues in the project's repo with the template and labels, instead of launching straight from a brief.
- Start through the same dispatch command; read Reviewer from the ticket when launching the gate.
- Close the issue after the gate passes, with the verdict in a comment.
- Ascend tasks: put the Linear issue link in the thread's first message.

## Migration

Existing idle personal-project threads with no issue stay on the board as today. A one-time import creates an issue from each one's first message or handoff file and writes the launch comment that maps it; mapped threads stop showing as separate cards. Ambiguous matches are listed for Shyam, never merged by title.

## Prerequisites

1. Create the label set in the 15 personal repos (Shyam's OK; outward-facing).
2. Fix `routing.json` so its primaries match the agreed model order (MO-138: every build type routes to Terra while the notes say MiniMax and GLM first), so per-ticket overrides sit on a correct default.

## Open questions for review

1. Issues per project repo with labels as fields: does anything break for cross-repo work or for the board's grouping by key?
2. Is a launch comment the right place for the dispatch record?
3. Board refresh: a poll each minute, or only on demand and when the board gains focus?
4. Does anything in the vendor rule or the dispatch checks still let a same-vendor gate or a duplicate agent through?
5. Who closes issues for tasks that are abandoned rather than finished?

## Revision 3 additions (after round-two critiques, 2026-11-09)

Round two (MO-139 Sol: conditional go; MO-140 GLM: go with conditions), full text in `~/Code/coordinator/evidence/local-tickets-design-critiques-round2-2026-11-09.md`. Shyam approved building v1 with these conditions:

- **Default routing:** build task types defaulted to GLM 5.3 and chores to MiniMax M3.1 Flash (`routing.json`, commit 078cc91). Superseded: every build type now uses the `build` list in `coordinator/models.json`, Terra first (#633). Review stays on Opus.
- **One command owns GitHub:** `coordinator/bin/ticket` (labels, list, start, abandon, show). The board calls it; nothing else talks to GitHub.
- **Durable dispatch:** the start writes an intent comment before `coordq start` and a receipt after; the request id is `ticket:<repo>#<n>:a<attempt>`, not tied to the body, so an edit cannot start a second agent. A start is refused while the latest attempt's thread is live or queued. A failed receipt retries the comment, never the start. Machine lines are trusted only from the authenticated gh user.
- **T3:** `t3_thread_send` dedupes on `clientRequestId` like launch does, so follow-ups cannot be sent twice.
- **Fresh checks at start:** the issue, labels and blockers are re-read from GitHub before every start, never from the cache.
- **Identity:** tickets join on `repo#number` and the request id; the title key is for people and review titles.
- **Vendor rule on every fallback:** checked at start, again before the gate, and at verdict-read against the gate's actual model; a same-vendor or unknown-author verdict is discarded. A pass counts only for the reviewed commit.
- **Closing:** only the Coordinator closes an issue, after a passed gate. Agent PRs use `Refs #n`, never closing keywords. Shyam owns abandonment: `ticket abandon` closes as not planned and interrupts or unqueues any live attempt.
- **Labels:** `ticket labels --apply` is idempotent and is rerun whenever the model table changes.
- **Refresh:** list served from a 60 s cache, single-flight, refreshed while the board is visible and on focus; rate-limit, auth and offline failures are shown distinctly with the cache age.
