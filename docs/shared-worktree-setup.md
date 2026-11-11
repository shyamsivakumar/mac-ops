# Shared worktree setup

Mac-ops owns `scripts/shared_npm_install.py`. It prepares fresh npm dependency roots on macOS without changing board settings or installing host services.

```sh
python3 "$HOME/Code/mac-ops/scripts/shared_npm_install.py" .
```

The first caller runs `~/.local/bin/heavy npm ci --no-audit --no-fund` in the requested dependency root. The script caches an APFS copy-on-write clone under the repository's common Git directory. Further worktrees receive private clones without calling heavy or npm ci. Cache keys include the manifest, lockfile, effective npm configuration, NODE_ENV, Node/npm versions, OS release, and architecture. The cache is shared within a repository, not between unrelated repositories.

A destination lock serializes setup of the same worktree, and a cache-key lock serializes publication. A failed installation never publishes a cache entry. Existing node_modules, including dangling symlinks, are rejected without replacement. Install failures can leave npm's partial node_modules in the calling worktree; the script will not delete it or claim it is ready.

The script selects the package manager from the requested directory before reading an npm manifest. `package-lock.json` or `npm-shrinkwrap.json` selects npm, `pnpm-lock.yaml` selects pnpm, `bun.lock` or `bun.lockb` selects Bun, `uv.lock` selects uv, and `requirements.txt` selects pip only when no uv lock is present. `Package.resolved` selects `swift package resolve`, and `Podfile.lock` selects `pod install --deployment`. Those native commands do not compile an app. More than one family of lockfile is rejected so the script does not guess.

npm lockfile versions 2 and 3 can reuse a copy-on-write `node_modules` cache. That path accepts public npm registry dependencies and rejects workspaces, local and Git dependencies, shrinkwrap files, root install lifecycle scripts, binding.gyp, ESBUILD_BINARY_PATH, and dependency install scripts other than canonical registry esbuild 0.27.0 and fsevents 2.3.3. Those exceptions require their recorded SHA-512 integrity as well as package identity and registry URL. Absolute or escaping dependency symlinks are rejected before caching.

pnpm, Bun, uv, and pip run through heavy in each worktree. Their package caches live under the repository's common Git directory and are keyed by the lockfile, manager version, and operating system. pnpm imports packages with clones, Bun uses clonefile, and uv uses clone mode with the environment path pinned to the requested directory. pip creates a local `.venv` and requires hashes. These managers do not copy an installed environment, because those environments can contain absolute paths. Swift and CocoaPods use their existing shared download caches.

The pnpm path rejects ancestor workspaces and configured `workspace-dir` overrides, and pins its lockfile and output directories inside the requested root. Native setup requires a local `Package.swift` or CocoaPods manifest and passes the requested project directory to the tool.

Some repositories have more than one dependency root. A repository table inside the script names the roots that one command prepares. `strategy-replay-workbench` prepares the repository root and `b2c`. The repository is recognised from `remote.origin.url` when the requested directory is the repository top level; a request for a subdirectory keeps the single-root behaviour. Each root is detected, installed and cached on its own, and a root that fails does not stop the others. The command exits non-zero and names every failed root.

## Workspace setup commands

Set these only after the script is present in the canonical mac-ops checkout. Do not activate host installers during worktree setup.

| Repository | Dependency-only workspace.setup command | Coverage |
|---|---|---|
| scripture-scroll | `"$HOME/.local/bin/heavy" npm ci --no-audit --no-fund` | Existing install; sharp/unrs-resolver need relocation proof before sharing |
| CineJar | `"$HOME/.local/bin/heavy" npm ci --no-audit --no-fund` | Existing install; unrs-resolver needs relocation proof before sharing |
| recoup | `python3 "$HOME/Code/mac-ops/scripts/shared_npm_install.py" convex` | Backend npm only |
| catalogue | `python3 "$HOME/Code/mac-ops/scripts/shared_npm_install.py" .` | Backend npm only |
| mac-ops | `true` | No dependency install is required |
| omni | `python3 "$HOME/Code/mac-ops/scripts/shared_npm_install.py" tools/omni-mcp` | uv lock, shared uv cache, worktree-local environment |
| dbt | `"$HOME/.local/bin/heavy" dbt deps` | Requires an already provisioned dbt CLI; does not install the unpinned adapter |
| llmwiki | `(cd claude/hooks && "$HOME/.local/bin/heavy" npm ci --no-audit --no-fund --ignore-scripts)` | Existing CI preparation only; native hook runtime is not proven by this command |
| strategy-replay-workbench | `python3 "$HOME/Code/mac-ops/scripts/shared_npm_install.py" .` | Root and `b2c` npm roots |

dbt's ingestion project, llmwiki's Bun tools, and strategy-replay-workbench's `b2c` service are separate dependency roots. Point the script at the directory that contains the lockfile, or at the repository top level when the repository table prepares every root for you. dbt package installation remains `dbt deps` because it is not a Python or JavaScript lockfile. Python environments and CocoaPods or Swift checkouts stay in the worktree that created them.

## Deferred gateway consolidation

The shared Executor gateway already runs at `http://127.0.0.1:4789/mcp`. Reuse that daemon rather than starting another per worktree. Client configuration is owned by `install_agents.py` and the existing Executor migration tooling, not workspace.setup. Preserve repository-scoped integrations and documented native exceptions. New sessions must be checked against the intended HTTP catalog before removing direct server entries. Active sessions retain their old MCP inventory until restart.

No gateway or client settings are changed by the dependency script. Memory savings require a before/after process census after an approved client cutover; sums of candidate process RSS alone do not establish reclaimable memory.
