# MO-182 · Can pi-claude-cli run omp sessions on the Claude subscription?

- Ticket: shyamsivakumar/mac-ops#121 (Refs #121), type research, read-only.
- Run id: `ticket:shyamsivakumar/mac-ops#121:a1`.
- Executed 2026-11-12 in a fresh worktree from `origin/main` on branch `t3/mo-182-report`.
- Scope observed: no install, no global setup change, no env var set, no API key, no hub/empq/installer/launchd change. Only public GitHub reads, local `--version` commands and read-only inspection of already-installed source trees were run. No `.env` or credential file was opened.

## Short answer

| Question | Answer |
| --- | --- |
| Does omp load pi packages? | **Not automatically.** omp does not read pi's agent directory (`~/.pi/agent`) and does not load packages installed by `pi install`. It *can* load a pi package's declared extension entry point, because omp reads the `pi` manifest key and ships a legacy-pi extension loader. **But the package as written is very unlikely to work inside omp:** its provider-registration calls do not match omp's API (see section 3). |
| Versions found vs required | Node **v22.23.1** (needs 22.18+) and Claude Code **2.1.323** (needs 2.1.265+). Both satisfied. |
| Memory cost | ~500 MB per parked Claude process, one per session, at most four parked: ~0.5 GB per live session, ~2 GB ceiling. |
| Usage-credit guard default | Blocked by default: with `PI_CLAUDE_CLI_ALLOW_USAGE_CREDITS` unset, a call that lands on usage credits ends with a `billing` error and pi does not retry it. The call that crossed the line is already charged. |
| Recommendation | Do not install pi-claude-cli into omp under this ticket, and do not install it later without a code change: as written it does not match omp's provider API. pi already has the package installed on this Mac and is the supported path. If omp needs the Claude subscription, the work is an omp-native provider, not an install. |

## Sources

### 1. The package

Read from the GitHub source of `dmmulroy/pi-claude-cli` (`gh api repos/dmmulroy/pi-claude-cli/contents/...`) and from the identical checkout already on this Mac at `~/.pi/agent/git/github.com/dmmulroy/pi-claude-cli` (listed in `~/.pi/agent/settings.json` under `packages` as `git:github.com/dmmulroy/pi-claude-cli`; checkout commit `5f86053`).

- `README.md`, "Quick start": "You need macOS or Linux, Node 22.18+, and `claude` on your `PATH`. Windows is not supported."
- `README.md`, "Logging in": "Claude Code owns the login. This package never reads, copies or refreshes your credentials."
- `README.md`, "Processes and memory": "Each parked process holds about 500 MB. The pool keeps one per pi session, for an hour by default (as long as the prompt cache lasts), and at most four in total."
- `README.md`, "Usage-credit guard": on a limit status that says "usage credits", the call ends with a "billing" error and "pi does not retry it"; the guard stops the agent loop from making more calls, and "The charged call is already paid for".
- `README.md`, "Configuration": `PI_CLAUDE_CLI_ALLOW_USAGE_CREDITS` default is *unset*.
- `AGENTS.md`: "pi loads `index.ts` and its TypeScript imports"; "Never extract OAuth tokens"; "A model call charged to usage credits ends the episode unless the user allowed it."
- `package.json`: `"engines": { "node": ">=22.18.0" }`, `"pi": { "extensions": ["index.ts"] }`. `peerDependencies` are `"@earendil-works/pi-ai": "*"` and `"@earendil-works/pi-coding-agent": "*"` (unpinned); the `1.2.0` pins are in `devDependencies`, together with `effect` and `@effect/platform-node-shared` 4.0.3 as runtime dependencies.
- `src/cli-requirements.ts`: `MIN_SUPPORTED_CLI_VERSION = "2.1.265"` and `MIN_STRUCTURED_IMPORT_CLI_VERSION = "2.1.292"`, with the reason (2.1.265 is the first that re-lists tools after `notifications/tools/list_changed`).
- `src/provider-config.ts:65`: `const MAX_PARKED = 4;`
- `src/claude-process-pool.ts:14-15`: "At most `maxParked` processes are parked at once (each holds hundreds of megabytes)".
- `src/usage-credits.ts`: `ALLOW_USAGE_CREDITS_ENV = "PI_CLAUDE_CLI_ALLOW_USAGE_CREDITS"`; allowed only when the value is `1`, `true` or `yes`; the error text starts with "Claude billing:" and every message contains "billing" so pi's retry classifier does not retry it.
- `index.ts`: the entry point the manifest names. Line 21: `import { registerApiProvider } from "@earendil-works/pi-ai/compat";`. Line 22: `import { getBuiltinModels as getModels } from "@earendil-works/pi-ai/providers/all";`. Line 166: `registerApiProvider({ api: PROVIDER_ID, stream: streamSimple, streamSimple }, PROVIDER_ID);`. Line 238: `pi.registerProvider(nativeProvider);` — a single Provider object.

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

omp is a fork of pi shipped as `@oh-my-pi/pi-coding-agent` 18.13.3 (`~/.bun/install/global/node_modules/@oh-my-pi/pi-coding-agent`, binary `~/.bun/bin/omp`, `omp --version` → `omp/18.14.0`). pi on this Mac is 1.5.2 (`~/.local/lib/node_modules/@earendil-works/pi-coding-agent`).

**No, omp does not load pi's installed packages.**

- omp's global config directory is its own: `src/sdk.ts:552` — "Global config directory. Default: `~/.omp/agent`".
- omp's user-level config roots do not include pi's: `src/config.ts:81` — "User-level: `~/.omp/agent`, Claude's active config directory, `~/.codex`, `~/.gemini`". (One unrelated exception: `src/lsp/config.ts:408` reads `~/.pi/agent/lsp.*` for LSP settings only. That does not change anything here.)
- A grep of omp's source for `pi-package` returns nothing: the pi package keyword and pi's package store are not a thing omp knows about.
- pi's package store on this Mac is `~/.pi/agent/git/github.com/...` (where the pi-claude-cli checkout lives), which omp does not read. omp has its own plugin store and its own `~/.omp/agent/extensions`.

**Yes, omp can load a pi package's entry point, if the package is re-hosted in omp.**

- omp reads the pi manifest key when it resolves a plugin: `src/extensibility/plugins/manager.ts:300`, `src/extensibility/plugins/loader.ts:194`, `src/extensibility/plugins/installer.ts:71,108` — `pluginPkg.omp || pluginPkg.pi`.
- omp reads the pi manifest key when it resolves an extension directory: `src/extensibility/extensions/directory-resolution.ts:69` — `const manifest = isRecord(pkg) ? (pkg.omp ?? pkg.pi) : undefined;`
- omp's discovery rule for a subdirectory with a manifest: `src/discovery/helpers.ts:842` — "Subdirectory with package.json: `extensions/<ext>/package.json` with "omp"/"pi" field → load declared paths".
- omp ships a loader for legacy pi extension modules: `src/extensibility/plugins/legacy-pi-compat.ts:2724` — "Load a legacy Pi extension module from its real on-disk location."

**But the package does not match omp's API, so loading it would not give omp a working provider.** Three static mismatches, all read from source:

1. **Provider registration.** The package calls `pi.registerProvider(nativeProvider)` (`index.ts:238`) with one argument, a Provider object. pi accepts that: pi's extension API declares `registerProvider(provider: Provider): void` (`@earendil-works/pi-coding-agent/dist/core/extensions/types.d.ts:1403`, with the same overload on the model registry, `dist/core/model-registry.d.ts:54`). omp does not: its extension API declares only `registerProvider(name: string, config: ProviderConfig): void` (`src/extensibility/extensions/types.ts:2033`) and its implementation is `registerProvider(providerName: string, config: ProviderConfigInput, sourceId?: string)` (`src/config/model-registry.ts:3508`). No adapter for the one-argument form exists under `src/extensibility/plugins/`.
2. **The pi-ai compatibility registry.** The package imports `registerApiProvider` from `@earendil-works/pi-ai/compat` (`index.ts:21`) and calls it at `index.ts:166`. pi-ai 1.2.0 exports it (`@earendil-works/pi-coding-agent/node_modules/@earendil-works/pi-ai/dist/compat.d.ts:51`). omp's bundled pi-ai has no such export: its registry module exports `registerCustomApi`, `getCustomApi`, `unregisterCustomApis` and `clearCustomApis` (`@oh-my-pi/pi-ai/src/api-registry.ts:74-109`), and no file in that package mentions `registerApiProvider`. omp's legacy remap sends `pi-ai/compat` to `pi-ai` (`src/extensibility/plugins/legacy-pi-compat.ts:839`), i.e. to a root that does not export it.
3. **The model catalogue subpath.** The package imports `getBuiltinModels` from `@earendil-works/pi-ai/providers/all` (`index.ts:22`). omp's bundled pi-ai has no `src/providers/all.ts`; its `src/providers/` holds per-provider modules plus `register-builtins.ts`, and the package's `"./*"` export wildcard would resolve that specifier to a file that does not exist.

**What is not verified.** These three points are static reading of the two source trees, not a runtime test: verifying them at runtime means installing the package into omp, which this ticket forbids. So the correct statement is "the package does not match omp's provider API as written, and the evidence points to it failing there", not "it fails there". The mismatch is also a provider-fork problem, not a loader problem: omp can read the package's `pi` manifest and its `index.ts`, but the provider registration path inside it is pi-1.x-specific.

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

1. **Do not install pi-claude-cli into omp.** Beyond the ticket's read-only scope, the source evidence in section 3 says the package would not register a working provider in omp anyway.
2. **The supported path today is pi**, where the package is already installed and the Node and Claude Code versions on this Mac both satisfy the package's floors.
3. If Shyam wants omp to use the Claude subscription, the work is **an omp-native provider** (register through omp's `registerProvider(name, config)` and omp's `registerCustomApi` surface, and pin the model catalogue to what omp ships), or a change to the package that supports both hosts. That is a code change and a separate ticket with its own approval, not an install.
4. Keep the usage-credit guard unset. If usage credits ever need to be allowed, that is an explicit, separate decision, not a side effect of an install.

## Uncertainty statement

- Versions, memory figures, guard behaviour, the API-mismatch findings and the omp source lines above were read directly (commands and file paths cited). The package's own README and source are the authority for its behaviour; no claim here rests on a summary.
- The three API mismatches in section 3 are static reading of two source trees. They were **not** confirmed at runtime, because that requires an install, which this ticket forbids.
- The ~500 MB figure is the package author's number; it was not measured on this Mac.
- The omp source quoted is from the installed `@oh-my-pi/pi-coding-agent` 18.13.3 tree on this Mac, and the omp binary reports 18.14.0; upstream may differ.
- The pi source quoted is from the installed `@earendil-works/pi-coding-agent` 1.5.2 tree on this Mac.

## Scope note

`git diff --stat origin/main...HEAD` shows three files, not one. The issue's "Finish" section requires `evidence/MO-182/decisions.md`, the issue's acceptance section names `evidence/MO-182/findings.md`, and the ticket brief for this run names `evidence/MO-182/report.md`. All three are under `evidence/MO-182/`; no file outside that directory changed, and no harness, installer, hub, launchd or configuration file was touched.

## Proof

- `node --version` → `v22.23.1`; `claude --version` → `2.1.323 (Claude Code)` (both pasted above).
- No install, no config change, no env var, no credential read: `git diff --stat` on this branch shows only `evidence/MO-182/` files.
- One read-only in-session review round (Claude Opus 5.5) ran against the branch diff; its MAJOR finding (a wrong `registerProvider` claim) was fixed in this revision, and the corrections are recorded in `evidence/MO-182/decisions.md`.
