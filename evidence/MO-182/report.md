# MO-182 · Can pi-claude-cli run omp sessions on the Claude subscription?

- Ticket: shyamsivakumar/mac-ops#121 (Refs #121), type research, read-only.
- Run id: `ticket:shyamsivakumar/mac-ops#121:a1`.
- Executed 2026-11-12 in a fresh worktree from `origin/main` on branch `t3/mo-182-report`.
- Scope observed: no install, no global setup change, no env var set, no API key, no hub/empq/installer/launchd change. Only public GitHub reads and local `--version` commands were run. No `.env` or credential file was opened.

## Short answer

| Question | Answer |
| --- | --- |
| Does omp load pi packages? | **Not automatically.** omp does not read pi's agent directory (`~/.pi/agent`) and does not load packages installed by `pi install`. It *can* load a pi package's declared extension entry point, because omp reads the `pi` manifest key and ships a legacy-pi extension loader. |
| Versions found vs required | Node **v22.23.1** (needs 22.18+) and Claude Code **2.1.323** (needs 2.1.265+). Both satisfied. |
| Memory cost | ~500 MB per parked Claude process, one per session, at most four parked: ~0.5 GB per live session, ~2 GB ceiling. |
| Usage-credit guard default | Blocked by default: with `PI_CLAUDE_CLI_ALLOW_USAGE_CREDITS` unset, a call that lands on usage credits ends with a `billing` error and pi does not retry it. The call that crossed the line is already charged. |
| Recommendation | Do not install into omp in this ticket. pi already has this package installed on this Mac and is the supported path. If omp coverage is wanted, open a separate approved ticket that installs the package as an omp plugin and proves one real subscription call. |

## Sources

### 1. The package

Read from the GitHub source of `dmmulroy/pi-claude-cli` (`gh api repos/dmmulroy/pi-claude-cli/contents/...`) and from the identical checkout already on this Mac at `~/.pi/agent/git/github.com/dmmulroy/pi-claude-cli` (listed in `~/.pi/agent/settings.json` under `packages` as `git:github.com/dmmulroy/pi-claude-cli`).

- `README.md`, "Quick start": "You need macOS or Linux, Node 22.18+, and `claude` on your `PATH`. Windows is not supported."
- `README.md`, "Logging in": "Claude Code owns the login. This package never reads, copies or refreshes your credentials."
- `README.md`, "Processes and memory": "Each parked process holds about 500 MB. The pool keeps one per pi session, for an hour by default (as long as the prompt cache lasts), and at most four in total."
- `README.md`, "Usage-credit guard": on a limit status that says "usage credits", the call ends with a "billing" error and "pi does not retry it"; the guard stops the agent loop from making more calls, and "The charged call is already paid for".
- `README.md`, "Configuration": `PI_CLAUDE_CLI_ALLOW_USAGE_CREDITS` default is *unset*.
- `AGENTS.md`: "pi loads `index.ts` and its TypeScript imports"; "Never extract OAuth tokens"; "A model call charged to usage credits ends the episode unless the user allowed it."
- `package.json`: `"engines": { "node": ">=22.18.0" }`, `"pi": { "extensions": ["index.ts"] }`, peer dependencies `@earendil-works/pi-ai` and `@earendil-works/pi-coding-agent`.
- `src/cli-requirements.ts`: `MIN_SUPPORTED_CLI_VERSION = "2.1.265"` and `MIN_STRUCTURED_IMPORT_CLI_VERSION = "2.1.292"`, with the reason (2.1.265 is the first that re-lists tools after `notifications/tools/list_changed`).
- `src/provider-config.ts:65`: `const MAX_PARKED = 4;`
- `src/claude-process-pool.ts:14-15`: "At most `maxParked` processes are parked at once (each holds hundreds of megabytes)".
- `src/usage-credits.ts`: `ALLOW_USAGE_CREDITS_ENV = "PI_CLAUDE_CLI_ALLOW_USAGE_CREDITS"`; allowed only when the value is `1`, `true` or `yes`; the error text starts with "Claude billing:" and every message contains "billing" so pi's retry classifier does not retry it.

### 2. Versions on this Mac (command output, verbatim)

```console
$ node --version
v22.23.1

$ claude --version
2.1.323 (Claude Code)
```

- Node v22.23.1 ≥ 22.18.0 required by `package.json` `engines.node` and the README. Satisfied.
- Claude Code 2.1.323 ≥ 2.1.265 (`MIN_SUPPORTED_CLI_VERSION`) and ≥ 2.1.292 (`MIN_STRUCTURED_IMPORT_CLI_VERSION`). Satisfied, with structured history import available.
- No `claude auth status` was run, no credential was read, and no login state was inspected.

### 3. Does omp load pi packages?

omp is a fork of pi shipped as `@oh-my-pi/pi-coding-agent` 18.13.3 (`~/.bun/install/global/node_modules/@oh-my-pi/pi-coding-agent`, binary `~/.bun/bin/omp`, `omp --version` → `omp/18.14.0`).

**No, not automatically.**

- omp's global config directory is its own: `src/sdk.ts:552` — "Global config directory. Default: `~/.omp/agent`".
- omp's user-level config roots are omp's and other agents' own: `src/config.ts:81` — "User-level: `~/.omp/agent`, Claude's active config directory, `~/.codex`, `~/.gemini`". `~/.pi/agent` is not among them.
- A repository-wide grep of omp's source for `pi-package` returns nothing: the pi package keyword and pi's package store are not a thing omp knows about.
- pi's own package store on this Mac is `~/.pi/agent/git/github.com/...` (where the pi-claude-cli checkout lives), which omp never reads. omp has its own plugin store and its own `~/.omp/agent/extensions`.

**Yes, but only by re-hosting the package.**

- omp reads the pi manifest key when it resolves a plugin: `src/extensibility/plugins/manager.ts:300`, `src/extensibility/plugins/loader.ts:194`, `src/extensibility/plugins/installer.ts:71,108` — `pluginPkg.omp || pluginPkg.pi`.
- omp reads the pi manifest key when it resolves an extension directory: `src/extensibility/extensions/directory-resolution.ts:69` — `const manifest = isRecord(pkg) ? (pkg.omp ?? pkg.pi) : undefined;`
- omp's discovery rule for a subdirectory with a manifest: `src/discovery/helpers.ts:842` — "Subdirectory with package.json: `extensions/<ext>/package.json` with "omp"/"pi" field → load declared paths".
- omp ships a loader for legacy pi extension modules: `src/extensibility/plugins/legacy-pi-compat.ts:2724` — "Load a legacy Pi extension module from its real on-disk location."
- the extension API omp offers includes the one the package needs: `src/extensibility/extensions/types.ts:2033` — `registerProvider(name: string, config: ProviderConfig): void;` — which is exactly what `pi-claude-cli/index.ts:238` calls (`pi.registerProvider(nativeProvider)`).

So a pi package can be loaded *inside* omp (installed as an omp plugin, or placed/symlinked under `~/.omp/agent/extensions`), but pi's own `pi install` result is invisible to omp. omp also carries compatibility shims for pi-era package specifiers (`src/extensibility/plugins/legacy-pi-compat.ts`), which is what would let a package that peers on `@earendil-works/pi-ai` resolve at all.

**What is not verified.** The package's provider registration path was written against pi 1.x (`peerDependencies` on `@earendil-works/pi-ai` and `@earendil-works/pi-coding-agent` 1.2.0; pi on this Mac is 1.5.2). omp's provider registry, auth hooks (`ctx.env`) and `session_shutdown` lifecycle are fork-specific. Whether omp accepts this provider at runtime was **not** tested, because testing it means installing the package into omp, which this ticket forbids. This is the single largest unknown in this report.

### 4. Memory cost

- Per parked Claude Code process: about 500 MB (README, "Processes and memory"; `src/claude-process-pool.ts:14-15` says "hundreds of megabytes").
- Parked processes: one per pi session, kept for an hour by default, at most four in total (`src/provider-config.ts:65`, `MAX_PARKED = 4`).
- Ceiling: about **2 GB** of extra resident memory for the four-process cap, roughly **0.5 GB** for a single live omp session.
- This is on top of the omp process itself and its own models. No measurement was taken on this Mac; the number is the package's own figure, not a local observation.

### 5. Usage-credit guard, default state

- Default is **not allowed**: `PI_CLAUDE_CLI_ALLOW_USAGE_CREDITS` is unset by default (README, "Configuration"), and `src/usage-credits.ts` allows usage-credit spending only for `1`, `true` or `yes`.
- Behaviour when a call is charged to usage credits: the episode ends with a "Claude billing: ..." error containing the word "billing", so pi's retry classifier does not retry it, and any held tool call is stopped before its result is sent (README, "Usage-credit guard"; `src/usage-credits.ts`).
- The charged call is already paid for; the guard prevents the *next* calls. Setting the variable to `1` is the only way to let calls spend usage credits, and that was not done.
- The package never touches credentials: `README.md` ("Logging in") and `AGENTS.md` invariant 6 ("Never extract OAuth tokens"; never forward API keys or `ANTHROPIC_BASE_URL` to the CLI).

### 6. Current state of this Mac (context, not a change)

- pi already has the package installed: `~/.pi/agent/settings.json` lists `git:github.com/dmmulroy/pi-claude-cli` in `packages`, and the checkout is at `~/.pi/agent/git/github.com/dmmulroy/pi-claude-cli`.
- omp has its own extension directory (`~/.omp/agent/extensions`, currently `herdr-omp-agent-state.ts`) and its own plugin system; the package is not present there.

## Recommendation

1. **Do not install pi-claude-cli into omp under this ticket.** The ticket asked for a report, and the install would change the daily setup.
2. **The supported path today is pi**, where the package is already installed and the Node and Claude Code versions on this Mac both satisfy the package's floors.
3. If Shyam wants omp to use the Claude subscription, open a separate, explicitly approved ticket that: installs the package as an omp plugin (`omp plugin install`, manifest key `pi`), runs one real subscription call through `omp` to prove provider registration works against the fork, and records the measured memory delta against the ~2 GB ceiling above. Expect the provider-registration compatibility (section 3, "What is not verified") to be the work, not the install.
4. Keep the usage-credit guard unset. If usage credits ever need to be allowed, that is an explicit, separate decision, not a side effect of an install.

## Uncertainty statement

- Versions, memory figures, guard behaviour and the omp source lines above were read directly (commands and file paths cited). The package's own README and source are the authority for its behaviour; no claim here rests on a summary.
- The runtime behaviour of this provider inside omp is **unverified** and cannot be verified without an install, which this ticket forbids.
- The ~500 MB figure is the package author's number; it was not measured on this Mac.
- The omp source quoted is from the installed `@oh-my-pi/pi-coding-agent` 18.13.3 tree on this Mac, and the omp binary reports 18.14.0; upstream may differ.

## Proof

- `node --version` → `v22.23.1`; `claude --version` → `2.1.323 (Claude Code)` (both pasted above).
- No install, no config change, no env var, no credential read: `git diff --stat` on this branch shows only `evidence/MO-182/` files.
