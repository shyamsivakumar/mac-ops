# Agent session traces and daily evals (MO-124)

One scrubbed trace per T3 Code run on this Mac. The collector calls the
read-only `t3mcp` tools `t3_thread_list` (with `includeSubagents` false, paging
newest-updated first until it passes the window start) and `t3_thread_read`
(`recentRuns` for each run's requested model, executed model, status and
times). Review threads are also read with the messages view to find the final
verdict word. It calls no T3 write tool.

Store: local files always; **PostHog** when a project API key is present
(same free store SRW-619 picks — ask the coordinator before creating an
account or key).

## Trace fields

Per run: thread, project, task key, requested and actual model, fallbacks,
start/end, final state, PR and its state, and review verdict and model when
supported by recorded evidence. Missing evidence stays unknown. Only a review thread’s
final verdict word, run model, thread ID and time are retained from its report.
Prompts, outputs, diffs, secrets and emails are never retained.

## Evidence limitations (approved MO-152 scope)

T3 does not supply tool calls, token counts, cost, stop reason, task type,
worktree path, branch, merge time, merge SHA or CI state. Those fields stay
null (tool call count included); null means **not collected**, not a clean
audit. The outside-worktree and preview flag lists stay empty. Equivalent
scorer behavior is tested using synthetic inputs only.

The requested model is the run's `model` and the actual model is its
`executedModel`; a run is a fallback when their model names differ. A PR that
T3 reports as merged has no merge time, so it is stored as
`merged_unknown_timing` with timing `unknown` and is not credited as a merge
by the end of the run.

## Commands

```sh
# Collect a local calendar day into ~/.local/state/mac-ops/session-traces/
python3 mo124 collect --day 2026-11-10 --no-export

# Score stored traces → session-evals/<day>.{md,json}
python3 mo124 eval --day 2026-11-10

# LaunchAgent entry: previous local day by default, plus unfinished-run reconcile
./scripts/session-traces/daily.sh            # yesterday (America/Los_Angeles)
./scripts/session-traces/daily.sh 2026-11-10 # explicit day

python3 mo124 status   # paths + whether POSTHOG_API_KEY is set
```

Merged-PR metrics count **distinct** PRs (run durations summed per PR).

Optional export: set `POSTHOG_API_KEY` (or `POSTHOG_API_KEY_FILE`), and
optionally `POSTHOG_HOST` (default `https://us.i.posthog.com`). Export is a
no-op without a key.

## Agent cost per pull request (MO-504)

Report only: it reads the pi session logs, changes no code, fails no check and
blocks no merge. The cost of a turn is `usage.cost.total` in the log under
`~/.pi/agent*/sessions`, priced on the local day (America/Los_Angeles) the turn
ran. A session belongs to a pull request when its name carries `#N` or
`repo#N`, or when its branch has a pull request that existed when the session
ran. Every other session is listed with the reason, so the pull request rows
and the unattributed rows add up to the day's total.

```sh
python3 mo124 cost --day 2026-11-17 --out evidence/agent-cost-504/agent-cost-2026-11-17.md
```

Left for later: the before and after refactor comparison, and attribution by
ticket key.

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
| Time / cost per merge | Distinct PRs; summed contributing run duration/cost |

The daily table lists every run; flagged rows are called out. Compared to the
previous day's JSON, rises in the bad flags (or a drop in proof) are marked
**REGRESSION**.

## Privacy

Never ship raw prompts or secrets. Scrubbing is by field name and pattern in
`session_traces/scrub.py`. Local state stays under `~/.local/state/mac-ops`,
outside git.
