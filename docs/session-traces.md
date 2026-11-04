# Agent session traces and daily evals (MO-124)

Collects local Empryo user turns and legacy T3 thread runs. Sources are read-only:
`~/.empryo/threads.db` points to session directories containing `meta.json` and
`session.jsonl`; T3 uses `~/.t3/userdata/statev2.sqlite` when present. An absent
T3 database is treated as retired. `EMPRYO_THREADS_DB` overrides the Empryo
index for isolated collection. Nothing writes to either source.

Store: local files always; **PostHog** when a project API key is present
(same free store SRW-619 picks — ask the coordinator before creating an
account or key).

## Trace fields

Per run: thread, project, task key, provider, model, start/end, tool calls
with durations, token totals (summed over complete provider turns; Cursor
runs carry none), cost (always null: no local source has one), final state
(`completed` / `interrupted` / `failed` / …), and outcome links (PR URL,
merge sha when present, CI `checksState`, review decision). Prompts, tool
inputs/outputs, diffs, secrets, emails, and home-directory user segments are
scrubbed or dropped.

Empryo traces are keyed by a SHA-256 digest of `turnId` (thread IDs are also
hashed), and ordered by journal timestamps in epoch milliseconds. Only user
turns with usable timestamps and IDs are collected; missing, malformed, deleted,
or unindexed session files cannot be recovered. Assistant `complete` and `error`
mark completed and failed turns; turn-stop or a subsequent user turn on the same
tab marks a running turn interrupted. Unfinished turns older than three days are
unknown. Tool start/end pairs supply durations when both are present. Unknown tool
names become `other`; model IDs are validated. Preview tool use is recorded.
Empryo worktree assignment is not established by session cwd, so outside-worktree
status is unknown, not an inference from cwd. Shell writes are not inspected.
No journal prompts, tool arguments, outputs, titles, paths, or arbitrary metadata
are persisted. Project IDs are unsalted hashes. Empryo does not provide reliable
PR/CI proof, tokens, or cost here; completed turns have unknown outcome evidence
and count as missing proof in evals, including regression counts. Collection is a
best-effort snapshot; real journal formats have not been verified.

## Commands

```sh
# Collect a local calendar day into ~/.local/state/mac-ops/session-traces/
python3 mo124 collect --day 2026-11-03 --no-export

# Score stored traces → session-evals/<day>.{md,json}
python3 mo124 eval --day 2026-11-03

# LaunchAgent entry: previous local day by default, plus unfinished-run reconcile
./scripts/session-traces/daily.sh            # yesterday (America/Los_Angeles)
./scripts/session-traces/daily.sh 2026-11-03 # explicit day

python3 mo124 status   # paths + whether POSTHOG_API_KEY is set
```

Command tool calls are stored as the stable name `command_execution` (never the
command text). PR/CI outcomes are attributed only when merge timing is at or
before the run's end; otherwise evidence is `unknown` / `post_run_merge`.
Merged-PR metrics count **distinct** PRs (run durations summed per PR).

Optional export: set `POSTHOG_API_KEY` (or `POSTHOG_API_KEY_FILE`), and
optionally `POSTHOG_HOST` (default `https://us.i.posthog.com`). Export is a
no-op without a key.

## Daily job

Plist: `scripts/session-traces/com.shyam.session-traces-daily.plist`
(`com.shyam.session-traces-daily`, 17:30 local). Install:

```sh
DOMAIN=gui/$(id -u)
L=com.shyam.session-traces-daily
launchctl bootout "$DOMAIN/$L" 2>/dev/null || true
cp scripts/session-traces/com.shyam.session-traces-daily.plist ~/Library/LaunchAgents/
launchctl bootstrap "$DOMAIN" ~/Library/LaunchAgents/$L.plist
launchctl enable "$DOMAIN/$L"
```

The daily script copies `session-eval-<date>.{md,json}` into
`~/Code/coordinator/evidence/` when that directory exists.

## Eval checks

| Check | Meaning |
| --- | --- |
| Ended with merge or blocker | Merged by run end, or named blocker |
| Claimed done with proof | Merged by run end, CI passing, no `CHANGES_REQUESTED` |
| Claimed done without proof | Completed with CI red or `CHANGES_REQUESTED` |
| Missing proof | Completed with no proven merge/blocker |
| Stopped while green | Interrupted/cancelled while checks passed and not merged |
| Outside worktree | `file_change` outside assigned worktree or project checkout |
| Preview / Playwright | Tools matching preview/playwright/html_render/device |
| Time / cost / tokens per merge | Distinct PRs; summed contributing run duration, cost, and tokens |

The daily table lists every run; flagged rows are called out. Compared to the
previous day's JSON, rises in the bad flags (or a drop in proof) are marked
**REGRESSION**.

## Privacy

Never ship raw prompts or secrets. Scrubbing is by field name and pattern in
`session_traces/scrub.py`. Local state stays under `~/.local/state/mac-ops`,
outside git.
