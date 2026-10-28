# Board agent parity (pi and omp)

mac-ops installs board-worker parity for pi and omp, apart from the heavy
tools. llmwiki is the reference for shared skills, omp rules, and Executor MCP.

## Install

From any checkout of this repository (including a task worktree):

```sh
./install.sh agents --no-prove
./install.sh agents
```

The second command refreshes pi model catalogs and runs GPT 6.1 Terra proofs
through `heavy`. Receipt: `~/.local/state/mac-ops/agents-installation.json`.

Status:

```sh
./install.sh agents-status
```

## Board worker strings

| Harness | `worker.agent` | Model id | Max effort |
| --- | --- | --- | --- |
| pi | `pi/openai/gpt-6.1-terra` | `openai/gpt-6.1-terra` | max |
| omp | `omp/openai-codex/gpt-6.1-terra` | `openai-codex/gpt-6.1-terra` | max |

`pi/openai-codex/gpt-6.1-terra` works after refreshing pi's
openai-codex login. Here the ChatGPT (`openai`) route ran at max effort.

Board `worker.effort max` maps to `--thinking max`. No per-harness effort
file exists beyond the board setting.

## What the installer sets

- pi: `~/.pi/agent/AGENTS.md`, llmwiki skills paths, Executor MCP, Terra
  enabled, board trust paths.
- omp: wiki `runtime/omp` rules and agents, Executor MCP, Terra in
  `enabledModels`, shared skills directory.
- Leaves board `worker.instructions`, `worker.fallback`, and coordinator
  settings unchanged.

Suggested Coordinator fallback order (not applied by the installer):
`cursor`, `pi/openai/gpt-6.1-terra`, `omp/openai-codex/gpt-6.1-terra`,
`codex`, `claude`, then the rest.

## Parity gaps closed

| Capability | Cursor/Codex/Claude | pi/omp before | After |
| --- | --- | --- | --- |
| Shared skills | Codex symlinks | pi: some | Both use wiki skills |
| AGENTS / rules | Global + repo | pi: no index | pi repo index |
| MCP | Executor + extras | Executor only | Others via `execute` |
| GPT 6.1 Terra | Codex native | Not in pi | Enabled, proved |
| heavy | `~/.local/bin/heavy` | Same | In pi AGENTS |
| Board CLI skill | herdr-projects | pi copy | Symlinked |
| Progress hooks | Codex/Claude | None | Unchanged; use `report` |

Hooks and 1Password env stay a board launch duty. Herdr Projects plugin
settings are untouched.
