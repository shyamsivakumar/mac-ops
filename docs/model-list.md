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

## Blocked providers

A provider that fails with no credits, a usage limit or an auth error is
recorded in `providers-blocked.json` in the queue folder. Every caller skips a
blocked entry until the hourly probe of that provider answers. `models.py` only
reads that file; the provider health store writes it. When every entry of a list
is blocked, the caller waits and says so.

## Callers

- `ticket start` picks the builder, `ticket gate` picks the reviewer, and
  `ticket gate --print-model` prints the allowed reviewers in order as JSON.
- `coordq` resolves a `taskType` to the first available entry of its list and
  chooses the gate reviewer in the gatekeep and the backstop.
- The lane driver picks a builder for every launch and every send: the
  first entry of the build list that is not blocked, with the ticket's
  `builder:<id>` label first. The label on the issue itself wins. The
  board's ticket record names the builder only when the issue carries no
  `builder:<id>` label. A thread takes the send only when it runs
  that builder, its provider is not blocked, and it works in a worktree of
  its own. A thread that fails any of those - a legacy Sol thread, another
  builder of the list, a blocked provider, the shared root of a repository -
  takes no send: the work starts a fresh thread on the chosen builder
  instead, in the same worktree when the thread has one.
- The lane driver sends no work to a protected destination. A herdr
  branch is Shyam's to merge, and a folder herdr made is his whatever
  branch it sits on, so a herdr branch, a herdr folder, the folder a path
  resolves to, a detached head and a branch that cannot be read are all
  refused: the work starts again on the verified pull request branch, or
  waits. The branch is read as a full ref, so a tag that shares a branch
  name cannot hide it.
- The lane driver's dead-run recovery names a builder as out only when the
  provider's own failure message says so, and only when that failure
  belongs to the run that stopped: an earlier run's quota error is not the
  stopped run's, and an assistant reply - a progress note, a gate report
  that ended without a verdict - is the thread talking, so it never marks
  the builder as failed. The relaunch can then run on that builder again.
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
