# The model list

`coordinator/models.json` is the only place a model is listed. The installer
copies it to `~/.coordinator/models.json`. The ticket tool, `coordq`, the lane
driver and the pi route generator read it through `coordinator/bin/models.py`.
Nothing else keeps a copy of a model id.

## Lists

| List | Used for | Order rule |
| --- | --- | --- |
| `build` | Every build type: standard, risky, design, large, ui, research, rca and chore. | The first entry that is not blocked, led by the entries whose `leads` names the task type. A `builder:<id>` label puts that entry first. |
| `fix` | Fix and finish rounds. | The first entry that is not blocked. |
| `review` | The gate. | The first entry that is not blocked and whose vendor differs from the builder's executed vendor. A `reviewer:<id>` label puts that entry first. |
| `panel` | A panel, only when Shyam asks for one. | Nothing starts a panel on its own. |

The workhorses are the two Morph models, DeepSeek V4.1 Flash and Kimi K3.1,
behind one `router` entry on the T3 `router` instance. The entry's `routes`
table names the chain a task type runs and its `chains` table lists the models
of each chain, so the order inside Morph is owned by the router's `ROUTES`
table and the order after Morph by this file. A Morph rate limit therefore
falls back to the next Morph model inside the same thread instead of failing
the launch. Cursor auto (`cursor`, model `default`) is the next choice and no
other Cursor model is listed. Two optional entry fields shape the list per
task type. `leads` puts an entry first for the types it names. `only` limits
an entry to the types it names (Terra serves quick, chore, standard, ui and
research; Sol serves rca, risky, design and hard). Without a task type the
whole list applies in order.

| Task types | Order |
| --- | --- |
| quick, chore, standard, ui, research | router (`task/standard`: DeepSeek, Kimi), Cursor, Terra |
| rca, risky, design, hard | router (`task/rca`, `task/risky`, `task/design`; `hard` uses the rca chain: Kimi, DeepSeek), Cursor, Sol |
| fix | router (`task/standard`), Cursor, Sol at max reasoning (`sol-max`) |

`sol-max` carries `options: [{"id": "reasoningEffort", "value": "max"}]` in its
selection. `models.py` and `coordq` pass a selection through unchanged, and T3
stores it in that shape. A router entry's selection is resolved for the task
type, so `coordq` and `ticket start` send `{instanceId: router, model:
task/<chain>}`. A payload that still names a direct `pi` Morph model is mapped
to the router entry instead of refused, and a `builder:kimi` or
`builder:deepseek` label on an older ticket is read as `builder:router`.
Reviews are Astra, then Opus. Fable
runs only when Shyam asks for it. `coordq` and `ticket start` pass the task
type to `models.py`, and the installer builds each `ROUTES` row from the same
order (the router entry's chains), so one file holds the preference. When a
model is blocked, the next entry of the type's order runs.

A builder that ran on Kimi, DeepSeek or Cursor is reviewed by Astra first. A
builder that ran on Terra or Sol (OpenAI) is reviewed by an Anthropic entry
(Opus). OpenAI API instance models (`openai-api`) never build.

## Blocked providers

A provider that fails with no credits, a usage limit or an auth error is
recorded in `providers-blocked.json` in the queue folder. Every caller skips a
blocked entry until the hourly probe of that provider answers. `models.py` reads
that file and `block_provider` writes an entry with an `expires_at` epoch time;
the reader drops an entry once that time has passed, and an entry without
`expires_at` (a manual block) stays until removed. The router entry covers one
identity per Morph model in its chains, so it counts as blocked only when every
one of them is blocked. When every entry of a list is blocked, the caller waits
and says so.

## Callers

- `ticket start` picks the builder, `ticket gate` picks the reviewer, and
  `ticket gate --print-model` prints the allowed reviewers in order as JSON.
- `coordq` resolves a `taskType` to the first available entry of its list and
  chooses the gate reviewer in the gatekeep and the backstop.
- The lane driver picks a fix model for every send and a build model for every
  dead-run relaunch. A thread whose model is not the first available entry gets
  a fresh thread in the same worktree.
- `install_coordinator.py` regenerates the `ROUTES` table of
  `~/.pi/agent/extensions/task-router.ts` from the router entry's chains in the
  build list, so pi cannot drift from the file.

## Changing a model

Edit `coordinator/models.json`, merge, and reinstall. Do not edit the installed
copy or `task-router.ts`.

The earlier lists (`models` and `types` in `tickets.json`, the backup files and
`task-router-blocks.json`) are archived in
`~/.coordinator/archive/2026-11-18-model-lists/`. To roll back, reinstall the
earlier release and move those files back.
