# The model list

`coordinator/models.json` is the only place a model is listed. The installer
copies it to `~/.coordinator/models.json`. The ticket tool, `coordq`, the lane
driver and the pi route generator read it through `coordinator/bin/models.py`.
Nothing else keeps a copy of a model id.

## Lists

| List | Used for | Order rule |
| --- | --- | --- |
| `build` | Every build type: standard, risky, design, large, ui, research, rca and chore. | The first entry that is not blocked. A `builder:<id>` label puts that entry first. |
| `fix` | Fix and finish rounds. | The first entry that is not blocked. |
| `review` | The gate. | The first entry that is not blocked and whose vendor differs from the builder's executed vendor. A `reviewer:<id>` label puts that entry first. |
| `panel` | A panel, only when Shyam asks for one. | Nothing starts a panel on its own. |

A builder that ran on Terra (OpenAI) is reviewed by an Anthropic entry.
Sol and other OpenAI API models never build.

The `build` list order is terra, minimax, glm, deepseek, cursor, sonnet. Terra is
also first in the `fix` list, so build and fix rounds share the Codex quota. When
the Codex provider is blocked, the list falls through to minimax as before. The
production numbers behind the order are in
`evidence/MO-633-build-order/why.md`.

## Blocked providers

A provider that fails with no credits, a usage limit or an auth error is
recorded in `providers-blocked.json` in the queue folder. Every caller skips a
blocked entry until the hourly probe of that provider answers. `models.py` reads
that file and `block_provider` writes an entry with an `expires_at` epoch time;
the reader drops an entry once that time has passed, and an entry without
`expires_at` (a manual block) stays until removed. When every entry of a list
is blocked, the caller waits and says so.

## Callers

- `ticket start` picks the builder, `ticket gate` picks the reviewer, and
  `ticket gate --print-model` prints the allowed reviewers in order as JSON.
- `coordq` resolves a `taskType` to the first available entry of its list and
  chooses the gate reviewer in the gatekeep and the backstop.
- The lane driver picks a fix model for every send and a build model for every
  dead-run relaunch. A thread whose model is not the first available entry gets
  a fresh thread in the same worktree.
- `install_coordinator.py` regenerates the `ROUTES` table of
  `~/.pi/agent/extensions/task-router.ts` from the pi-prefixed entries of the
  build list, so pi cannot drift from the file.

## Changing a model

Edit `coordinator/models.json`, merge, and reinstall. Do not edit the installed
copy or `task-router.ts`.

The earlier lists (`models` and `types` in `tickets.json`, the backup files and
`task-router-blocks.json`) are archived in
`~/.coordinator/archive/2026-11-18-model-lists/`. To roll back, reinstall the
earlier release and move those files back.
