# Agent session traces and daily evals (MO-124)

One scrubbed trace per T3 thread run on this Mac (Cursor, Codex, Claude,
MiniMax, GLM, …). Source is read-only local data under `~/.t3` (primarily
`userdata/statev2.sqlite`). Nothing writes to the T3 server.

Store: local files always; **PostHog** when a project API key is present
(same free store SRW-619 picks — ask the coordinator before creating an
account or key).

## Trace fields

Per run: thread, project, task key, provider, model, start/end, tool calls
with durations, tokens/cost when the projection has them, final state
(`completed` / `interrupted` / `failed` / …), and outcome links (PR URL,
merge sha when present, CI `checksState`, review decision). Prompts, tool
inputs/outputs, diffs, secrets, emails, and home-directory user segments are
scrubbed or dropped.

## Commands

```sh
# Collect today's runs into ~/.local/state/mac-ops/session-traces/
python3 mo124 collect --day 2026-11-03 --no-export

# Score stored traces → session-evals/<day>.{md,json}
python3 mo124 eval --day 2026-11-03

# Collect + eval (LaunchAgent entry)
./scripts/session-traces/daily.sh 2026-11-03

python3 mo124 status   # paths + whether POSTHOG_API_KEY is set
```

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
| Ended with merge or blocker | PR `state=merged`, or named blocker in title |
| Claimed done with proof | Done run, PR, CI green, no `CHANGES_REQUESTED` |
| Stopped while green | Cancelled while checks passed and not merged |
| Outside worktree | `file_change` paths not in worktree or project root |
| Preview / Playwright | Tools matching preview/playwright/html_render/device |
| Time / cost per merge | Mean duration (and cost) over merged-PR runs |

The daily table lists every run; flagged rows are called out. Compared to the
previous day's JSON, rises in the bad flags (or a drop in proof) are marked
**REGRESSION**.

## Privacy

Never ship raw prompts or secrets. Scrubbing is by field name and pattern in
`session_traces/scrub.py`. Local state stays under `~/.local/state/mac-ops`,
outside git.
