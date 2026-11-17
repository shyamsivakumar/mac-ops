# Traces trial on this Mac (2026-11-17)

Step 1 of the approved plan (Refs #491): prove that the Traces CLI finds our
T3 Code sessions on this Mac and masks secrets before anything is shared.
Nothing was uploaded. No hook was installed. Nothing under
`~/Code/slash-eureka` was opened or reported here.

## What was installed

```sh
brew install market-dot-dev/tap/traces
traces --version   # traces v0.6.48
```

| Item | Value |
| --- | --- |
| Binary | `/opt/homebrew/Cellar/traces/0.6.48/bin/traces` |
| Local database | `~/Library/Application Support/traces/traces.db` |
| Config directory | `~/Library/Preferences/traces` |
| Sign-in | GitHub OAuth, remote URL plus a six character code |

Sign-in needs no local browser. `traces login --no-browser` prints a URL and a
code, and the CLI waits for the approval on the phone. The URL and the code
are in the ticket thread.

## Account

Sign-in is not confirmed. `traces whoami` still reported "Not logged in" at
13:26 PT on 2026-11-17, after two full polling windows, so no account is
named here. The CLI is still waiting for the approval. Confirm with
`traces whoami` and record the namespace slug here before this trial is
treated as signed in.

## Read-only listing for today

Command:

```sh
traces list --since 1794902400000 --limit 2000 --json
```

`1794902400000` is 2026-11-17 00:00 PT. The listing ran without sign-in and
without network calls; it reads the local session files only. The counts below
are the snapshot taken at 13:08 PT, so a later run gives slightly different
numbers as new sessions land.

222 traces were indexed for today across all agents. 7 of them have a project
path under `~/Code/slash-eureka`; those were excluded from this document
without opening their content. The remaining 215 break down as follows.

| Agent | Traces today | Source folder | Found |
| --- | --- | --- | --- |
| `codex` | 81 | `~/.codex/sessions` | yes |
| `claude-code` | 29 | `~/.claude/projects` | yes |
| `pi` (`~/.pi/agent`) | 88 | `~/.pi/agent/sessions` | yes |
| `pi` (`~/.pi/agent-openai-api`) | 0 of 57 session files | `~/.pi/agent-openai-api/sessions` | no |
| `pi` (`~/.pi/agent-coordinator`) | 0 of 1 session file | `~/.pi/agent-coordinator/sessions` | no |
| `pi` (`~/.pi/agent-deepseek`) | 0 of 0 | same layout | no, idle today |
| `pi` (`~/.pi/agent-minimax`) | 0 of 0 | same layout | no, idle today |
| `pi` (`~/.pi/agent-glm`) | 0 of 0 | same layout | no, idle today |
| `amp` | 17 | indexed on this Mac | out of scope, see below |

Codex, Claude Code and the default pi folder are all visible, so those T3
runs on this Mac are covered by Traces today. The other pi folders are not
covered, so coverage is incomplete. The `amp` traces are out of scope: Amp
runs on the M1, and that machine has no Traces CLI yet.

The pi rows marked "no" are the reason for the overrides below. The
`agent-deepseek`, `agent-minimax` and `agent-glm` folders had no session
today, so they could not be counted live; their layout is identical to
`agent-openai-api`, so they need the same override.

## Overrides the pi adapter needs

The pi adapter in the CLI has one fixed sessions path:
`<home>/.pi/agent/sessions`. It is not configurable. The published adapter
path overrides cover Cursor (`TRACES_CURSOR_GLOBAL_DB`), OpenCode
(`TRACES_OPENCODE_DIR`) and Claude Code (`TRACES_CLAUDE_DIR`); there is no pi
equivalent, and no pi flag or environment variable in the CLI.

The first three options were tested in a sandbox `HOME`, so the real session
folders were never touched. The last one is the recommendation from the pi
documentation, not a tested end to end run.

| Option | Result |
| --- | --- |
| Symlink the other config folders' `sessions` directory into `~/.pi/agent/sessions` | Not indexed. The scanner does not follow directory symlinks. |
| Symlink a single session file into `~/.pi/agent/sessions` | Not indexed. |
| Hardlink a session file into `~/.pi/agent/sessions/<project>/` | Indexed, and the project directory is still reported correctly. |
| Set `PI_CODING_AGENT_SESSION_DIR=$HOME/.pi/agent/sessions` for the other pi agents | Recommended. pi documents this variable as the session storage directory, so those agents would write their sessions where the Traces pi adapter already looks. No copy, no Traces change. Not run yet. |

The recommended override is not applied in this trial, because it changes how
the other pi agents are launched. It only needs the environment variable in
the launcher for `agent-openai-api`, `agent-coordinator`, `agent-deepseek`,
`agent-minimax` and `agent-glm`. The variable is listed in the installed pi
package at `~/.local/lib/node_modules/@earendil-works/pi-coding-agent/docs/environment-variables.md`,
and pi stores its sessions under `~/.pi/agent/sessions/` by default, which is
the path the Traces pi adapter reads.

A cleaner long term fix belongs to Traces: a `TRACES_PI_DIR` or
`TRACES_PI_SESSION_DIR` override for the pi adapter, next to the ones that
already exist for Cursor, OpenCode and Claude Code.

## Redaction

The CLI has no local preview command. `traces list` and `traces show` print
the raw session text, so the fake secret below appeared verbatim in the local
index and in `traces show --markdown`. Redaction happens on the client at
publish time.

To see what would leave the machine without sending anything to Traces, the
publish target was pointed at a local capture server and the scratch session
was shared against it:

```sh
TRACES_HTTP_URL=http://127.0.0.1:8765 \
TRACES_API_URL=http://127.0.0.1:8765 \
TRACES_URL=http://127.0.0.1:8765 \
traces share --source-path <scratch session> --agent pi --json
```

The scratch session held one fake key, `sk-EXAMPLEEXAMPLEEXAMPLEEXAM`, in the
first user message and once in the assistant reply. The captured request
bodies show:

| Payload | Result |
| --- | --- |
| Trace metadata (`title`) | `Here is my fake key: sk-EXAMPLEEXAMPLEEXAMPLEEXAM please keep it secret` — **not masked** |
| Message text and parts | `Here is my fake key: [REDACTED] please keep it secret` — masked |

So this synthetic key was masked in the message bodies and kept in the title.
The title is derived from the first user message, so a secret in the opening
message of a session would reach the server. Two rules follow: do not open a
session with a secret, and ask Traces to scrub the title as well. One key is
one sample, so this says nothing about how many other secret shapes are
covered.

The CLI's own secret list covers AWS keys, GitHub tokens, Anthropic keys,
Google API keys, Slack tokens, npm, PyPI, Hugging Face, Vercel and Supabase
keys, private keys, database URLs with a password, bearer tokens and email
addresses. The generic OpenAI style rule `sk-` followed by at least 20
characters is what masked the fake key.

The scratch session was deleted after the test, and its row was removed from
the local database.

## Nothing was shared

* The only `traces share` run was the capture above, and its publish target was
  `127.0.0.1`, so nothing left this Mac.
* The current local database holds no trace with a remote id or a remote url,
  so no publication is recorded.
* `traces doctor` reports the agent hooks as "Not installed or outdated" and
  the git hooks as not installed. `traces setup` was never run in this
  trial.
* Sign-in itself only asks Traces for an OAuth grant; it sends no session.

After sign-in, `traces share status` shows the shared count per folder and
must read zero for every folder before sharing is ever switched on.

## Rollback

```sh
traces logout
brew uninstall traces
```

Nothing else was changed on this Mac. The scratch session and its database
row are gone.

## Left for later

* Apply `PI_CODING_AGENT_SESSION_DIR` to the other pi agents, or ask Traces
  for a pi path override, so all six pi folders are covered.
* Ask Traces to scrub the trace title, not only the message bodies.
* Install the CLI on the M1 so the Amp sessions there are covered.
* Only then open the "Shyam Personal" org and turn on sharing. Out of scope
  for this step.
