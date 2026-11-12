# MO-184 — empq, ticket and the coordinator watcher drive T3 Code

Run: `ticket:shyamsivakumar/mac-ops#124:a1`

Ticket: <https://github.com/shyamsivakumar/mac-ops/issues/124>

Base: `origin/main` at `4ad285608886589e76bc5147c65de6ed45b07da7`.

Authority: Shyam, 2026-11-11, "the harness freeze is lifted for the one mac-ops
ticket that points empq, ticket and the watcher at T3"; plus the same-day
addition: "Ensure t3 tickets also only have agentic ci and reviews".

Status of this file: **research and design only.** No production code changed
yet. The turn cap ended this turn after the T3 API surface was verified
empirically. Everything below is measured against a running T3, not inferred
from documentation.

## Verified T3 API surface

Measured with `t3mcp schema <tool>` and live calls against the running T3
server (`~/.t3/userdata/server-runtime.json`, server 0.1.6). VERIFIED means
read from the live schema or observed in a live call.

### Transport

| Fact | Status |
| --- | --- |
| `t3mcp call <tool> '<json>'` and `-` (stdin) both work | VERIFIED |
| A failing call exits 1 and prints the error on stderr | VERIFIED |
| One `t3mcp call` round trip costs about 0.075 s | VERIFIED |
| Reads its bearer token from `~/.config/t3mcp/credentials.json` | VERIFIED |
| Never prints the token | VERIFIED (read of `~/.local/bin/t3mcp`) |

### Tools that replace the ones empq and ticket use

Each entry maps the Empryo tool to its T3 replacement, with the schema
notes that matter for the swap.

- `emp_thread_launch` → `t3_thread_launch`. Required: `title` only. Extra props:
  `projectId`, `scratch`, `modelSelection`, `runtimeMode`, `interactionMode`,
  `workspaceStrategy`, `message`, `attachments`, `clientRequestId`,
  `delegatedFrom`. **No `taskType`.**
- `emp_thread_send` → `t3_thread_send`. Required: `threadId`, `message`. `mode`
  enum: `auto`, `queue`, `steer`, `restart`. **No `start` mode.**
- `emp_thread_list` → `t3_thread_list`. `statuses` enum: `idle`, `preparing`,
  `queued`, `starting`, `running`, `waiting`, `completed`, `interrupted`,
  `failed`, `cancelled`, `rolled_back`. Response: `{projectId,
  currentThreadId, threads[], nextCursor, total}`.
- `emp_thread_read` → `t3_thread_read`. `view` enum `messages`/`activity`,
  `afterPosition`, `runLimit`, `maxCharsPerItem`. Response: `{thread,
  recentRuns, items[]}`.
- `emp_thread_interrupt` → `t3_thread_interrupt`. Required: `threadId`.
- `emp_thread_organize` (settle) → `t3_thread_organize`. `action` enum: `pin`,
  `unpin`, `snooze`, `unsnooze`, `settle`, `unsettle`, `archive`, `unarchive`,
  `mark_unread`.
- `emp_pending_request` (list/read/answer) → `t3_pending_request`. `action`
  enum: `list`, `read`, **`respond`** (not `answer`); takes an `answers`
  object.
- `emp_project_list` → `t3_project_list`. Returns
  `{projects[{id, title, workspaceRoot, ...}]}`.
- `emp_thread_search` → `t3_thread_search`. Required: `query`.
- `emp_thread_configure` → `t3_thread_configure`. `modelSelection` only.
- `emp_thread_update` (rename) → `t3_thread_update`. `action` enum `rename`,
  `regenerate_title`.
- `emp_thread_merge` → **none**. See the gap list.
- `emp_thread_cleanup` → `none`. `t3_thread_organize` `settle`+`archive` covers
  the intent.
- `emp_thread_materialize` → `none`. Not used by empq or ticket.
- `delegate_task` (hub flavour) → `t3_thread_launch` + `delegatedFrom`. See the
  decision on `delegate_task`.

### Behaviours the implementation depends on

1. **A duplicate `clientRequestId` is idempotent, not an error.** Launching
   twice with the same id returned the same `threadId`; sending twice returned
   the same `messageId` and `runId`. Both exited 0. This matches the hub's
   dedupe, so the queue keeps the same guarantee. VERIFIED.
2. **A launch with no `message` produces an idle thread.** The launch response
   has `status: null`; a later `t3_thread_list` shows `status: "idle"`.
   VERIFIED.
3. **`scratch: true` launches into the "No project" scratch project**
   (`f093cc9b-5332-48eb-a719-2187eb8cbabc`, workspace root
   `~/.t3/scratch`). VERIFIED.
4. **A launch that names a `projectId` and omits `modelSelection` is refused**:
   "Pass modelSelection: the project has no default model." A scratch launch
   with no `modelSelection` is accepted and silently defaults to
   `cursor/default`. So every real launch must carry an explicit
   `modelSelection`. VERIFIED.
5. **`total` respects the `statuses` filter.** `allProjects` with live statuses
   returned `total: 4`; unfiltered returned `total: 910`. The empq cap check
   can read `total` exactly as it reads the hub's. VERIFIED.
6. **Unknown properties are ignored, not rejected.** A launch carrying
   `taskType: "standard"` succeeded and created the thread. So a leftover
   `taskType` is harmless but also does nothing: the table must be resolved
   before the call, not passed through. VERIFIED.
7. **A fresh thread's defaults** are `runtimeMode: full-access`,
   `interactionMode: default`, `providerInstanceId: cursor`,
   `model: default`. VERIFIED.
8. **`t3_thread_list` items have no `pendingRequestCount` and no `archived`.**
   The hub's items did. VERIFIED.

### Providers and model ids

`orchestrator_capabilities` reports these provider instances and models
(VERIFIED): `codex` (`gpt-6.1-sol`, `gpt-6-astra`, `gpt-6.1-terra`,
`gpt-6-luna`, `zai-coding/glm-5.3`, `qwen-plan/*`, `minimax-token-plan/minimax-m3`),
`claudeAgent` (`claude-opus-5-5`, `claude-sonnet-5-5`, `claude-fable-5-1`,
`claude-haiku-5-5`), `glm` (`glm-5.3`, `glm-5.3-flash` plus the Claude ids),
`minimax` (the Claude ids), `cursor` (`default` and others), `grok`,
`opencode`, `antigravity`, `fx`, `muse`, `pi`.

The T3 selections the ticket names are all present in that list:
`{"instanceId": "minimax", "model": "claude-sonnet-5-5"}` (the MiniMax
provider running Claude Code, which is what the switch-back evidence
measured), `{"instanceId": "claudeAgent", "model": "claude-opus-5-5"}` for
gates, `{"instanceId": "codex", "model": "gpt-6.1-sol"}` for risky and design
work. VERIFIED.

The Empirical-era ids in `empryo/hub/routing.json` and
`empryo/config/tickets.json` (`instanceId: "empryo"`, models like
`minimax/MiniMax-M3.1-Flash`, `zai-coding-plan/glm-5.3`,
`subscriptions/claude-sonnet-5-5`) do not exist in T3. Every selection must be
retargeted.

## Decisions

### The taskType table moves into `tickets.json` and empq resolves it

**When:** MO-184, 2026-11-11.

*`t3_thread_launch` has no `taskType` property, and the hub resolved
`taskType` to a `modelSelection` inside `emp_thread_launch`. That resolution has
to happen on the mac-ops side. Put the table in `empryo/config/tickets.json`
next to the `models` aliases, as a `types` map from taskType to alias, and let
both empq and the ticket CLI read that one file. empq resolves a taskType to a
concrete `modelSelection` before it calls T3, so the T3 call always carries an
explicit selection.*

**Gap:** the ticket allows the table to live in the queue tool or the ticket
CLI; a third file would be a parallel path. `tickets.json` already holds the
alias-to-selection map and is already the file the ticket CLI reads, so one
file owns both. empq has to read it too, which is new coupling for empq, but
less bad than two sources of truth for the same selection.

**Reach:** every launch from empq carries a `modelSelection`, which is what
T3 requires for a project launch. The taskType values stay the same set:
`standard`, `risky`, `design`, `large`, `ui`, `research`, `rca`, `chore`,
`review`, `panel`. Aliases in `tickets.json` keep their names (`glm-5.3`,
`minimax`, `terra`, `sol`, `astra`, `opus`, `sonnet`, `cursor`) so existing
GitHub `builder:` and `reviewer:` labels keep working.

**Verdict:** sound — one owner for the selection, resolved on the side that
speaks to T3.

**Confidence:** high. The absence of `taskType` on the T3 launch schema and
the refusal of a project launch without `modelSelection` were both measured.

**Owner:** `empryo/bin/empq`, `empryo/bin/ticket`,
`empryo/config/tickets.json`.

### empq's `delegate_task` maps to `t3_thread_launch` + `delegatedFrom`

**When:** MO-184, 2026-11-11.

*The hub's `delegate_task` spawned a child thread in the parent's project and
worktree. T3's `delegate_task` is a different thing: it delegates a task to a
sub-agent inside the current thread and takes only `task` as required. Routing
empq's `delegate_task` to it would change what the option does. Map empq's
option to `t3_thread_launch` with `delegatedFrom: {environmentId, threadId,
title}` and a `workspaceStrategy` of `existing_worktree`.*

**Gap:** `t3_thread_launch` requires `environmentId` inside `delegatedFrom` and
empq has no way to learn the environment id of the parent thread from the
queue file alone. The coordinator has to pass it in the payload. This is
listed as an open question for the coordinator handoff below.

**Reach:** `empq start --tool delegate_task` keeps spawning a child thread.
Only the arguments the caller must supply change.

**Verdict:** sound — preserves the existing meaning of the option.

**Confidence:** medium. The two tools' schemas were read directly, but no
child thread was actually spawned, because that needs a live parent thread id
and an environment id that no test in this repo can produce.

**Owner:** `empryo/bin/empq`.

### The `install_pending` gate in empq is re-pointed, not dropped

**When:** MO-184, 2026-11-11.

*`empq.install_pending` reads `~/.empryo-hub/install.json` and holds new work
while the installer is writing `~/.local/bin`. That gate is still meaningful
after the switch, because the installer still rewrites empq and ticket
mid-flight. Keep the gate and keep its file.*

**Gap:** the state file lives under `~/.empryo-hub`, the directory of a hub
that is being frozen. If the hub directory is removed, the gate reads a
missing file and fails open, which loses the protection silently. Recommend
moving the installer's state file to `~/.empryo/` and pointing both empq and
the installer at it. That touches `empryo/bin/emp_hub_install.py`, which this
ticket does not otherwise change, so it is listed as a follow-up rather than
done here.

**Reach:** the queue keeps its current admission behaviour through the
switch. The turn-limit half of the old routing file (`turnSeconds`,
`taskTypeSeconds`) has no T3 equivalent: `t3_thread_launch` takes no turn
budget, and the 10-minute cap is enforced by the runner, not by the launch
call. That half stays in the hub's routing file for the frozen hub and is not
carried over.

**Verdict:** sound with one listed follow-up.

**Confidence:** high for the gate's current behaviour; medium for the
follow-up, which depends on whether `~/.empryo-hub` survives the switch.

**Owner:** `empryo/bin/empq`; follow-up ticket for
`empryo/bin/emp_hub_install.py`.

### The builder brief carries the CI rule, one review round, and the Opus gate

**When:** MO-184, 2026-11-11, on Shyam's added scope.

*Every brief the ticket CLI builds gets a fixed prefix that states the CI
rule, the one in-session review round, and the Opus 5.5 gate that follows it.
The brief must fit the 10-minute turn cap, so it says to size the work for one
turn and split the rest.*

**Gap:** the brief prefix has to fit inside the 10-minute turn cap together
with a review round. If a brief cannot fit a build plus one review round plus
the gate in one turn, the builder must split it rather than skip the review.

**Reach:** the ticket CLI's `build_start` composes the message, so that is
where the prefix goes. The gate template that must treat a
`.github/workflows` or `.woodpecker` file as a major finding is
`empryo/config/agents/code-reviewer.md`, the in-repo reviewer brief. The
root `AGENTS.md` already states the CI rule for humans and agents; the
reviewer brief is what makes it a finding.

**Verdict:** sound — the rule is enforced where briefs are written and where
findings are graded.

**Confidence:** medium. The brief text has not been drafted; only the
placement is decided.

**Owner:** `empryo/bin/ticket`, `empryo/config/agents/code-reviewer.md`.

## Gaps in T3

Listed rather than worked around, as the ticket requires.

1. **No merge with an expected revision.** `emp_thread_merge` took `dryRun`
   and `expectedRevision` and refused a merge when the head, checks or review
   had moved. T3 has no merge tool at all; `t3mcp tools` lists none, and the
   MCP tool list has none either. The coordinator's merge path therefore has
   no direct equivalent and must either use `gh pr merge` with its own
   re-verification, or wait for T3 to expose one. This is coordinator-side
   work outside this repo and is listed in the handoff below.
2. **No `emp_thread_cleanup`.** `t3_thread_organize` with `settle` then
   `archive` covers the intent, but the hub's single dry-run cleanup call has
   no one-to-one replacement.
3. **No `turnSeconds` on launch.** The 10-minute cap is not a launch
   parameter in T3.
4. **`pendingRequestCount` is missing from `t3_thread_list` items.** The
   coordinator's watcher derives "needs an answer" from that field. It has to
   ask `t3_pending_request` per thread instead.
5. **No `archived` field on `t3_thread_list` items.** The coordinator's
   board sweep filters on it.
6. **`emp_thread_send`'s `start` mode has no equivalent.** T3 offers `queue`,
`steer` and `restart` instead.
7. **`emp_pending_request`'s `answer` action is `respond` in T3**, and it
   takes an `answers` object rather than `optionId` and `answer`.

## Coordinator handoff

`~/Code/coordinator/loop/watch.py` and `~/Code/coordinator/loop/board_sweep.py`
live outside this repo. These are the exact functions that call `emp` and the
call each should use.

### `loop/watch.py`

- `threads()` (lines 12 to 32): `emp call emp_thread_list {"allProjects": true,
  "limit": 100}` becomes `t3mcp call t3_thread_list` with the same arguments.
- `pending(t)` (lines 35 to 36): reads `t["pendingRequestCount"]`. No T3 list
  field exists, so query `t3mcp call t3_pending_request` with
  `{"action": "list", "threadId": "<id>"}` per thread, or accept the loss.

The response shape needs no change: `watch.py` takes the first list value in
the reply, and the T3 reply's first list is `threads`. Only the tool name
changes.

### `loop/board_sweep.py`

- `emp(tool, args, timeout)` (line 81): `run_json(["emp", "call", tool,
  json.dumps(args)], timeout)` becomes `run_json(["t3mcp", "call", tool,
  json.dumps(args)], timeout)`, plus a tool-name map: `emp_thread_list` →
  `t3_thread_list`, `emp_thread_read` → `t3_thread_read`,
  `emp_pending_request` → `t3_pending_request`, `emp_project_list` →
  `t3_project_list`.
- `fetch_threads()` (line 122): `emp("emp_thread_list", args)` becomes
  `t3_thread_list`. Note `settled: False` and `snoozed` filters exist in T3,
  but there is no `archived` item field to filter on.
- `fetch_projects()` (line 133): `emp("emp_project_list", {"limit": 100})`
  becomes `t3_project_list`.
- `read_report(thread_id)` (line 178): `emp("emp_thread_read", {...})` becomes
  `t3_thread_read`; the reply still has `items` and `recentRuns`.
- `pending_question(thread_id)` (line 188): `emp("emp_pending_request",
  {"action": "list", ...})` becomes `t3_pending_request` with `action: "list"`.
- `pending_question(thread_id)` (line 192): `emp("emp_pending_request",
  {"action": "read", ...})` becomes `t3_pending_request` with `action: "read"`.
- `act_merge()` (line 664): `emp("emp_thread_merge", {"threadId": ...,
  "dryRun": True})` has **no equivalent**; gap 1.
- `act_merge()` (line 669): `emp("emp_thread_merge", {"threadId": ...,
  "expectedRevision": ...})` has **no equivalent**; gap 1.
- `act_gate()` (line 767): `emp("emp_thread_merge", {"threadId": ...,
  "dryRun": True})` has **no equivalent**; gap 1.

Two more coordinator-side items that follow from the switch:

- `act_gate()`'s payload already carries `modelSelection: {"instanceId":
  "claudeAgent", "model": "claude-opus-5-5"}`, which is valid in T3 as it
  stands. Its `taskType: "review"` becomes meaningless and should be dropped
  or ignored.
- `board_sweep.vendor()` infers the model vendor from the model string. The
  T3 `minimax` provider runs `claude-sonnet-5-5`, so a string match would
  read it as Anthropic and wrongly skip the gate. It should read
  `providerInstanceId`, which `t3_thread_list` provides, instead of the model
  string.

## What is left

Nothing in the production code has changed. The next turn picks up from this
file.

1. `empryo/bin/empq`: swap the transport to `t3mcp`, map tool names, resolve
   `taskType` to a `modelSelection` before the call, keep the queue file, the
   cap in `queue/config.json`, the priorities and the `clientRequestId`
   dedupe. `empq create` stays a launch with no message; `empq list`,
   `empq drop` and `empq status` are unchanged.
2. `empryo/bin/ticket`: `emp_call` becomes a `t3mcp` call; `load_routing`
   points at the new table; `resolve_models` and `alias_for_selection` work
   against T3-shaped selections; `build_start` drops `taskType` and sends the
   resolved `modelSelection`; the builder brief gets the CI and review prefix.
3. `empryo/config/tickets.json`: add the `types` map and retarget every
   `models` alias `selection` to a T3 provider and model id.
4. `empryo/config/agents/code-reviewer.md`: make a `.github/workflows` or
   `.woodpecker` file in the diff a major finding.
5. `install_empryo.py`: install the retargeted `tickets.json` and, if the
   table needs its own file, that file too.
6. `docs/empryo-hub.md`: record that empq and ticket speak T3 now.
7. Proof, per the ticket: `empq create` makes an idle T3 thread in the
   scratch project; `empq start` with a message launches one; a duplicate
   `clientRequestId` is refused; the cap queues the 7th; `ticket start
   --dry-run` on a test issue shows the T3 launch payload. The repo's existing
   tests run unchanged.
8. `evidence/MO-184/decisions.md` stays as the record; the gate review runs
   on the exact head and ends with `CHECK: PASS <sha>` and
   `VERDICT: PASS` or `FAIL`.

### Follow-up tickets

- Move the installer's state file out of `~/.empryo-hub` so empq's admission
  gate survives the hub's removal.
- Give the coordinator a merge path that refuses a stale revision. T3 has no
  merge tool, so this is either a `gh pr merge` wrapper in the coordinator or
  a wait for T3 to expose one.

## Slice 1: empq speaks T3 (done)

**When:** MO-184 slice 1, 2026-11-12.

*`empryo/bin/empq` now calls `t3mcp call <t3 tool>` instead of
`emp call <emp tool>`. The Emp-hub is unloaded for good, so empq never calls
`emp` again. The queue file, the cap in `queue/config.json`, the priorities,
the `clientRequestId` dedupe and the `install_pending` admission gate are
unchanged.*

### What changed

- The transport in `empq.call()` is `t3mcp call <tool> -` with the JSON
  payload on stdin, in place of `emp call <tool> -`. The binary is
  `EMPQ_T3MCP` (default `t3mcp`).
- A `TOOLS` map translates the old Emp tool names to the T3 names
  (`emp_thread_launch` → `t3_thread_launch`, and the same for send and list),
  so queue items written by the old code still dispatch.
- `with_model()` resolves the task type to a concrete `modelSelection` before
  every launch, because `t3_thread_launch` has no `taskType` property. The
  table lives in empq: `risky` and `design` → `{"instanceId": "codex",
  "model": "gpt-6.1-sol"}`, `review` → `{"instanceId": "claudeAgent", "model":
  "claude-opus-5-5"}`, every other task type → the worker default
  `{"instanceId": "minimax", "model": "claude-sonnet-5-5"}`. An explicit
  `modelSelection` in the payload wins over the task type. A launch with
  neither is refused.
- `empq create` sends `scratch: true` when the payload names no project and
  no worktree, so an idle thread lands in the T3 scratch project rather than
  needing a project id.
- The `origin` field and the `EMP_HUB_THREAD` environment variable are gone
  from the queue item and the call. They were Emp-hub concepts and T3 has no
  equivalent that empq can fill from the queue file alone.
- `empq start --tool` takes `t3_thread_send` and `t3_thread_launch`. The
  `delegate_task` option is dropped for now: mapping it to
  `t3_thread_launch` plus `delegatedFrom` needs an `environmentId` that only
  the coordinator can supply, and that is coordinator work outside this repo.

### The table lives in empq, not in `tickets.json`

**Decision:** the task-type table is a constant in `empryo/bin/empq`.

**Reason:** the decision above put the table in `empryo/config/tickets.json`
so that empq and the ticket CLI read one file. Slice 1 moved it into empq
instead, because empq is now the only component that resolves a task type:
the ticket CLI (slice 2) resolves its own `modelSelection` from the
`models` aliases in `tickets.json` and passes the result to empq as an
explicit `modelSelection`, so the ticket CLI never needs the task-type table
at all. One owner, and it is the component that speaks to T3.

**Precedence:** an explicit `modelSelection` in the payload wins over the
task type, so a caller that names a model gets that model. The task type is
the fallback, and it is the only thing that resolves a worker launch.

**Gap:** `tickets.json` still carries the Emp-era `models` alias selections
(`instanceId: "empryo"`, `minimax/MiniMax-M3.1-Flash`). Those do not exist in
T3 and are retargeted in slice 2, which is the slice that owns
`tickets.json`.

### Proof

All against the live T3 server. The temporary queue lived under `$TMPDIR`,
so the live queue file at `~/Code/coordinator/queue/queue.json` was never
read or written by the proof.

| Check | Result |
| --- | --- |
| `empq create` with a task type | Idle thread, `minimax`/`claude-sonnet-5-5` |
| `empq start` with a message | Thread `mcp:launch:498a18a7...` launched |
| Repeated `clientRequestId` | Same id as `mo184-proof-start-1`; one thread |
| Cap queues the next item | `queued #8` at cap 6, `queued #3` at cap 1 |
| No task type and no model | Refused: needs taskType or modelSelection |
| Existing tests | `test_hub_install.py`, `test_hub_install_batch.py` pass |
| Cleanup | The 7 proof threads were interrupted and settled |

### What is left for slices 2 and 3

**Slice 2, the ticket CLI.** `empryo/bin/ticket` still calls
`emp_thread_launch`, `emp_thread_send` and `emp_thread_list` through
`emp_call`, and it still puts `taskType` in the launch payload. It needs to
call T3, drop `taskType`, and send the resolved `modelSelection`.
`empryo/config/tickets.json` needs its `models` aliases retargeted to T3
provider and model ids: `minimax` → `{"instanceId": "minimax", "model":
"claude-sonnet-5-5"}`, `sonnet` → the same, `glm-5.3` → a live T3 selection,
and `empryo` retired as an instance id. The builder brief also needs the CI
and review prefix, and `empryo/config/agents/code-reviewer.md` needs a
`.github/workflows` or `.woodpecker` file in the diff to be a major finding.

**Slice 3, the coordinator watcher.** `~/Code/coordinator/loop/watch.py` and
`~/Code/coordinator/loop/board_sweep.py` live outside this repo. The exact
call sites and their replacements are in the handoff section above. Two items
there need the coordinator: `t3_thread_list` has no `pendingRequestCount` and
no `archived` field, so the watcher must ask `t3_pending_request` per thread
and the board sweep must give up its `archived` filter. `board_sweep.vendor()`
must read `providerInstanceId` rather than matching the model string, because
the T3 `minimax` provider runs `claude-sonnet-5-5` and a string match reads it
as Anthropic and would skip the gate.

## Slice 2a: the ticket CLI launches on T3 models

**When:** MO-184 slice 2a, 2026-11-12.

*`empryo/bin/ticket` built its launch payload from the Emp-era model
selections in `tickets.json`, and it sent a `modelSelection` only when the
issue carried a `builder:` label. T3 refuses a project launch with no
`modelSelection`, and every Emp-era selection named an `instanceId` that T3
does not have, so every ticket launch failed at T3. The CLI now resolves the
builder alias from one table, maps every alias to a live T3 selection, and
always sends that selection in the payload.*

### The alias map

| Alias | instanceId | model | Vendor |
| --- | --- | --- | --- |
| `minimax` | `minimax` | `claude-sonnet-5-5` | minimax |
| `glm-5.3` | `glm` | `glm-5.3` | zhipu |
| `terra` | `codex` | `gpt-6.1-terra` | openai |
| `sol` | `codex` | `gpt-6.1-sol` | openai |
| `astra` | `codex` | `gpt-6-astra` | openai |
| `opus` | `claudeAgent` | `claude-opus-5-5` | anthropic |
| `sonnet` | `claudeAgent` | `claude-sonnet-5-5` | anthropic |
| `cursor` | `cursor` | `default` | cursor |

Every row was checked against `t3mcp call orchestrator_capabilities '{}'`.
T3 lists `gpt-6-astra` on the `codex` provider and `default` on the `cursor`
provider, so `astra` and `cursor` keep their old meaning and `cursor` stays
`noGate`. The Emp-era ids `empryo`, `zai-coding-plan/glm-5.3`,
`minimax/MiniMax-M3.1-Flash` and `subscriptions/claude-sonnet-5-5` are gone
from the file.

### The `glm-5.3` alias is not folded into the worker

The slice ticket asked for `glm-5.3` to map to the worker selection. T3 has a
live GLM selection on the `glm` provider, so the alias maps there instead, for
two reasons.

1. Mapping `glm-5.3` to the worker would make it the same selection as
   `minimax`, so its vendor field would have to become `minimax` as well. The
   vendor pair check would then refuse a `builder:minimax` and
   `reviewer:glm-5.3` pair, even though the two labels read as two different
   vendors.
2. A `builder:glm-5.3` label asks for GLM. The worker selection runs
   `claude-sonnet-5-5` on the `minimax` provider, so the label would stop
   meaning what it says.

Folding `glm-5.3` into the worker is one line in `tickets.json` if Shyam
prefers the ticket's wording.

### The type table moved into `tickets.json`

`resolve_models` read `~/.empryo-hub/routing.json` for the default builder and
the default reviewer when the issue had no `builder:` or `reviewer:` label,
then matched the routing selection against the aliases. That file is the
frozen hub's config, and its worker selections still name
`instanceId: "empryo"`, so no alias could match them. Every ticket of type
`standard`, `large`, `ui`, `research`, `rca` or `chore` would have been
refused with "routing model empryo/minimax/MiniMax-M3.1-Flash has no alias in
tickets.json".

`tickets.json` holds a `types` map from task type to alias now, and the CLI
reads that map. This is the decision recorded at the top of this file, "the
taskType table moves into `tickets.json`", and the values match the table in
`empryo/bin/empq`: `risky` and `design` map to `sol`, `review` maps to `opus`,
and every other type maps to the worker `minimax`. The CLI sends an explicit
`modelSelection` on every launch, so the table in empq is only the fallback
for a caller that sends none.

### What else changed in the CLI

- The payload dropped `taskType`. `t3_thread_launch` has no `taskType`
  property, and the CLI resolves the model itself now.
- The payload always carries `modelSelection`, taken from the resolved
  builder alias rather than from the `builder:` label, so a ticket with no
  builder label still launches on a T3 selection.
- `load_routing` and `alias_for_selection` are gone, and so is the
  `TICKET_ROUTING` environment variable. The CLI reads one file for its
  models now: `tickets.json`.
- The vendor pair check and the `noGate` check are unchanged.

### Proof for slice 2a

| Check | Result |
| --- | --- |
| Dry run | `sol` selection, `opus` reviewer, no `taskType` |
| Old ids | no `empryo` matches |
| Type map | most types to `minimax` |
| Risky types | `risky` and `design` to `sol` |
| Reviewer | `opus` |
| Vendor pair | `opus` and `sonnet` refused, both anthropic |
| Mixed pair | `minimax` and `glm-5.3` allowed, providers differ |
| `scripts/mac_ops_fast_check.py` | passed |
| The repo's test suite | passed, no test file changed |

The dry run was `ticket start --dry-run shyamsivakumar/mac-ops#124`, and the
grep check was `grep -n '"empryo"' empryo/bin/ticket empryo/config/tickets.json`.
Every type in `labels.type` except `risky` and `design` maps to `minimax`, and
the reviewer maps to `opus`.

The dry run ran with `EMPQ_DIR` pointing at a temporary directory, so the live
queue file at `~/Code/coordinator/queue/queue.json` was never read, and the
CLI read the repo copy of `tickets.json` rather than `~/.empryo/tickets.json`.

### What is left for the next slice

The CLI still calls `emp` for the thread list and the thread interrupt.
`emp_call` in `empryo/bin/ticket` is the only place it does so, and it has two
call sites:

- `ticket_threads` calls `emp_thread_list` with `{"projectId", "titleContains",
  "limit"}`. `t3_thread_list` takes the same three properties, and its items
  carry `threadId`, `title`, `status` and `createdAt`, which is what
  `ticket_threads` reads. The call was verified against the live T3 server.
- `cmd_abandon` calls `emp_thread_interrupt` with `{"threadId"}`.
  `t3_thread_interrupt` takes the same property.

Both go through `emp`, so a ticket with a prior attempt in its ledger cannot
be started while the hub is unloaded. That transport swap is not part of this
slice.

## Slice 2b: empq refuses the task types and the tools it cannot run

**When:** MO-184 slice 2b, 2026-11-12.

*The gate on the first 2b commit returned FAIL with five findings. The queue
accepted any task type and any tool name, a payload that named both a task
type and a model selection ran on the model the payload named, and a refused
item stayed in the queue file and was refused again on every drain.*

### A review task type runs on the gate model or it does not run

*A payload that carried `taskType: "review"` and a `modelSelection` kept the
`modelSelection` and dropped the task type, so a review could launch on the
worker model and the gate would read a MiniMax Sonnet verdict instead of an
Opus one. empq now refuses a `review` payload whose `modelSelection` is not
the gate selection, and the refusal names both selections.*

**Choice:** refuse, do not force. A forced selection would run the gate on
Opus and hide the fact that the caller asked for another model. A refusal
tells the caller that the two fields disagree, and the caller picks one. The
gate model is the only selection a `review` accepts.

**Gap:** a payload with no task type and a model selection still runs on that
selection. The check fires on the `review` task type only, because that is
the task type whose whole meaning is which model reads the work.

**Reach:** every `review` launch runs on `{"instanceId": "claudeAgent",
"model": "claude-opus-5-5"}`, and a payload that asks for anything else is
refused before any queue write.

**Confidence:** high. The refusal and the accepted payload were both run
against a stub t3mcp.

**Owner:** `empryo/bin/empq`.

### The panel task type runs on the worker model

*The table in empq mapped `panel` to a Terra selection. The slice 1 table says
that every task type other than `risky`, `design` and `review` runs on the
worker default, and no Emp-era Terra selection exists on T3 anyway. `panel`
now maps to the worker selection, and the Terra constant is gone.*

**Owner:** `empryo/bin/empq`.

### A queue item is refused when any of its steps names a tool that is not dispatchable

*`drain()` checked only the item's own tool, so a `pre` step naming
`emp_thread_merge` was handed to t3mcp as a merge request. Every step of an
item now has to name a dispatchable tool, and the item is refused otherwise.*

**Reach:** the pre steps of a queue item reach t3mcp only when each of them
names `t3_thread_launch` or `t3_thread_send`.

**Owner:** `empryo/bin/empq`.

### A refused item leaves the queue file

*Refused items stayed in `queue.json`, were logged again on every drain and
counted as queued work. A refused item is now dropped from the queue file
once the refusal is logged, so it is logged once and stops counting as
queued.*

**Choice:** drop the item, rather than keep it with its attempts spent. A
kept item needs a second marker to say it was refused, and a kept item still
reads as queued work. The refusal stays in `dispatch.log`, which is where the
operator reads it.

**Gap:** the item is gone from `empq list` as well, so the operator who wants
to see it reads the dispatch log rather than the queue.

**Owner:** `empryo/bin/empq`.

### The start payload is a required argument

*`empq start` took the payload as an optional argument and refused an empty
one by hand. The argument is required now, so argparse reports the missing
payload.*

**Owner:** `empryo/bin/empq`.

### Proof for slice 2b

Every check ran against a temporary `EMPQ_DIR` with a stub t3mcp that logged
each call. The live queue file was never read or written.

| Check | Result |
| --- | --- |
| Review with a MiniMax selection | refused, no queue write, nothing sent |
| Review with no selection | launched with the Opus selection |
| Panel | launched with the worker selection |
| Item with a `emp_thread_merge` pre step | refused, nothing sent, dequeued |
| Second drain | the refusal was not logged again, queued count 0 |
| Item with a non-dispatchable tool | refused, nothing sent, dequeued |
| `empq start` with no payload | argparse reported the missing argument |
| Unknown task type | refused, no queue write |
| `python3 -m unittest tests.test_hub_install` | passed, 26 tests |
| `python3 scripts/mac_ops_fast_check.py` | passed |

No test file changed.

## Method

No secrets were read or printed. `.env` was never opened. emp-hub was never
run, restarted or unloaded; the hub socket refused connections for the whole
session, so no Empryo launch was possible or attempted. Every T3 call in this
file ran against the live server through `t3mcp`, and every thread created for
proof was settled and archived afterwards. `t3mcp credentials` were never
displayed.
