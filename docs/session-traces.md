# Agent session traces and daily evals (MO-124)

One scrubbed trace per Empryo hub run on this Mac. The collector reads
`~/.empryo-hub/threads.json`, `hub.log`, and transcript files read-only.
It does not invoke the hub.

Store: local files always; **PostHog** when a project API key is present
(same free store SRW-619 picks — ask the coordinator before creating an
account or key).

## Trace fields

Per run: thread, project, task key and type, requested and actual model,
fallbacks, start/end, tool-call counts and available durations, final state,
PR, merge SHA, CI state and review verdict and model when supported by
recorded evidence. Missing evidence stays unknown. Only a review thread’s
final verdict word, run model, thread ID and time are retained from its report.
Prompts, outputs, diffs, secrets and emails are never retained.

## Evidence limitations (approved MO-152 scope)

Outside-worktree and preview detection are unavailable from the permitted hub
metadata. The collector does not inspect tool arguments, command titles, paths,
or output to reconstruct them. The legacy flag lists remain empty and path /
branch fields remain null; these mean **not collected**, not a clean audit.
Equivalent scorer behavior is tested using synthetic inputs only.

Requested models come only from a run's explicit requested-model field or an
unambiguous routing event near its start. Thread-current model selection is
never historical evidence, even for a single run. Without run-scoped evidence,
`requested_model` is null and the legacy false fallback flag means unknown;
it does not establish that the run used its requested model.

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
| Time / cost per merge | Distinct PRs; summed contributing run duration/cost |

The daily table lists every run; flagged rows are called out. Compared to the
previous day's JSON, rises in the bad flags (or a drop in proof) are marked
**REGRESSION**.

## Privacy

Never ship raw prompts or secrets. Scrubbing is by field name and pattern in
`session_traces/scrub.py`. Local state stays under `~/.local/state/mac-ops`,
outside git.
