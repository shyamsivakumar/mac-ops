# Shared worktree setup

Mac-ops owns `scripts/shared_npm_install.py`. It prepares fresh npm dependency roots on macOS without changing board settings or installing host services.

```sh
python3 "$HOME/Code/mac-ops/scripts/shared_npm_install.py" .
```

The first caller runs `~/.local/bin/heavy npm ci --no-audit --no-fund` in the requested dependency root. The script caches an APFS copy-on-write clone under the repository's common Git directory. Further worktrees receive private clones without calling heavy or npm ci. Cache keys include the manifest, lockfile, effective npm configuration, NODE_ENV, Node/npm versions, OS release, and architecture. The cache is shared within a repository, not between unrelated repositories.

A destination lock serializes setup of the same worktree, and a cache-key lock serializes publication. A failed installation never publishes a cache entry. Existing node_modules, including dangling symlinks, are rejected without replacement. Install failures can leave npm's partial node_modules in the calling worktree; the script will not delete it or claim it is ready.

The first slice supports npm lockfile versions 2 and 3 with public npm registry dependencies. It rejects workspaces, local and Git dependencies, shrinkwrap files, root install lifecycle scripts, binding.gyp, ESBUILD_BINARY_PATH, and dependency install scripts other than canonical registry esbuild 0.27.0 and fsevents 2.3.3. Those exceptions require their recorded SHA-512 integrity as well as package identity and registry URL. Absolute or escaping dependency symlinks are rejected before caching. These limits avoid silently skipping generated outputs or copying paths tied to another worktree. Other package managers and native dependency setup remain on their existing commands.

## Workspace setup commands

Set these only after the script is present in the canonical mac-ops checkout. Do not activate host installers during worktree setup.

| Repository | Dependency-only workspace.setup command | Coverage |
|---|---|---|
| scripture-scroll | `"$HOME/.local/bin/heavy" npm ci --no-audit --no-fund` | Existing install; sharp/unrs-resolver need relocation proof before sharing |
| CineJar | `"$HOME/.local/bin/heavy" npm ci --no-audit --no-fund` | Existing install; unrs-resolver needs relocation proof before sharing |
| recoup | `python3 "$HOME/Code/mac-ops/scripts/shared_npm_install.py" convex` | Backend npm only |
| catalogue | `python3 "$HOME/Code/mac-ops/scripts/shared_npm_install.py" .` | Backend npm only |
| mac-ops | `true` | No dependency install is required |
| omni | `(cd tools/omni-mcp && "$HOME/.local/bin/heavy" uv sync --locked)` | Existing uv flow, not shared environment cloning |
| dbt | `"$HOME/.local/bin/heavy" dbt deps` | Requires an already provisioned dbt CLI; does not install the unpinned adapter |
| llmwiki | `(cd claude/hooks && "$HOME/.local/bin/heavy" npm ci --no-audit --no-fund --ignore-scripts)` | Existing CI preparation only; native hook runtime is not proven by this command |

The dbt ingestion uv project and llmwiki's optional Bun tools are separate dependency roots. Python virtual environments contain absolute entrypoint paths, and CocoaPods/SPM depend on native project paths and shared Xcode caches. They must not be treated as relocatable node_modules directories.

## Deferred gateway consolidation

The shared Executor gateway already runs at `http://127.0.0.1:4789/mcp`. Reuse that daemon rather than starting another per worktree. Client configuration is owned by `install_agents.py` and the existing Executor migration tooling, not workspace.setup. Preserve repository-scoped integrations and documented native exceptions. New sessions must be checked against the intended HTTP catalog before removing direct server entries. Active sessions retain their old MCP inventory until restart.

No gateway or client settings are changed by the dependency script. Memory savings require a before/after process census after an approved client cutover; sums of candidate process RSS alone do not establish reclaimable memory.
