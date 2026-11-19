# Harbor eval harness (step 1)

Harbor (https://github.com/harbor-framework/harbor, Apache-2.0) runs an agent
against a task in a Linux container and scores the result as a reward of 1 or
0. This folder is step 1 of ticket
[#507](https://github.com/shyamsivakumar/mac-ops/issues/507): install Harbor,
scaffold one task with `harbor init`, and run that task with the pi agent.

Steps 2 to 5 of the ticket (the 20 merged PR tasks, the oracle filter, the
three baseline runs, the comparison table) come after this step passes.

## What the runtime needs

Harbor runs every task in a Linux container, so the host needs:

- **Docker Desktop** with a running Linux engine. The container image is Linux,
  not macOS. On this Mac the engine is `linux/arm64` (Docker Desktop 4.55.0).
  Docker Desktop has to be running before the job starts; Harbor does not
  start it for you.
- **Outbound network from the container.** The pi adapter installs Node with
  `nvm` and then `npm install -g @earendil-works/pi-coding-agent`, so the
  build needs `nodejs.org` and the npm registry.
- **A model endpoint and an API key.** The key travels as an environment
  variable, and Harbor projects it into the container under the name given by
  `--api-key-name`. The key never reaches the task files or the saved logs.

A mac-ops check that needs macOS cannot run inside this harness. The Linux
container is the limit that shapes the ticket, not a missing dependency.

## Install

```sh
evals/harbor/install.sh
```

That runs `uv tool install harbor==0.26.0`, which puts one pinned release at
`~/.local/bin/harbor`. The version is pinned so a later run scores the same
harness the first run scored.

## Run the example task

The task is the scaffold `harbor init` writes, filled in with one file to
create and one check:

```
evals/harbor/tasks/example/
  instruction.md          what the agent is asked to do
  environment/Dockerfile  the agent sandbox (Ubuntu 24.04, workdir /app)
  tests/test.sh           the verifier; writes 1 or 0 to /logs/verifier/reward.txt
  solution/solve.sh       the oracle solution
  task.toml               task metadata; the verifier runs in the agent sandbox
```

To rebuild the scaffold from scratch:

```sh
harbor init mac-ops/example --task --output-dir evals/harbor/tasks \
  --description "Harbor step 1 example task" \
  --author "Shyam Sivakumar <shyam@example.com>"
```

To run it with the pi agent:

```sh
export MINIMAX_API_KEY=<the model API key>
evals/harbor/run-example.sh
```

The script defaults to the MiniMax Anthropic-compatible endpoint
(`https://api.minimax.io/anthropic`) and the `MiniMax-M3.1-Flash` model. Point
it elsewhere with `HARBOR_MODEL`, `HARBOR_BASE_URL`, `HARBOR_API_FORMAT` and
`HARBOR_API_KEY_NAME`. The script reads the key from the environment by name,
never prints it and never writes it to disk.

## Recorded runs

Both runs are under `evals/harbor/logs/`, with the Harbor job log, the pi
transcript, the trajectory and the reward file.

| Run | Agent | Result |
| --- | --- | --- |
| `logs/oracle-run/2026-11-18__18-49-03` | oracle | reward 1.0, 5s |
| `logs/pi-run/2026-11-18__18-49-19` | pi, MiniMax-M3.1-Flash | reward 1.0, 32s |

The pi run used 3344 input tokens, 1792 cache tokens and 56 output tokens.
`cost_usd` is `null` in the result file: Harbor prices the providers it knows,
and a custom endpoint has no price row. A run against a priced provider fills
the field, which is what steps 4 and 5 need for the cost column.

## Limits found while running this

- The harness proves the agent, the task and the reward path. It does not
  prove the mac-ops check, because that check needs macOS.
- `harbor run` writes one job directory per run. The saved runs here are the
  evidence for step 1; later steps will add one task folder per merged PR.
- Harbor deletes the container after a trial by default (`--delete`). The
  saved logs are what is left of a run.

## The frozen eval set (ticket #633, PR 1)

`evals/harbor/sets/ladder.json` lists the merged PRs the ladder gate scores
models on (`{"tasks": [...]}`, each with `id`, `type`, `heldout`, repo, PR,
ticket, merge and parent commits, test files and test command). About a
quarter of the tasks are held out, chosen by `sha256(id) % 4 == 0` and recorded
in the file so the slice never moves; `build_tasks.py check` fails if a
recorded value disagrees with the hash.

```sh
evals/harbor/build_tasks.py build      # task folders from the selection
evals/harbor/build_tasks.py prepare    # parent-commit snapshots into .cache
evals/harbor/build_tasks.py check
timeout 900 heavy harbor run -p evals/harbor/tasks/<id> -a oracle -n 1 -o <dir> -y
```

`prepare` runs `git archive <parent>` from the local clone into the gitignored
`evals/harbor/.cache/<id>/` and links the tarball into the task's build
context. No token enters the image, the task files or the logs. The PR's own
test files live under `tests/files/` and are copied over `/app` only at
grading. Oracle and nop results per task are in `evidence/MO-633/oracle.md`.
