# MO-901 runs

## What "scoped" means (pi-subagent-manager 1.9.0, installed under ~/.pi/agent-coordinator/npm/node_modules/pi-subagent-manager)

- `src/prefs/settings.ts:47` and `:85`: `pick-first-scoped` is a `modelSelection` mode and the default.
- `docs/settings.md:187`: "Same, but the model must also be in the main session's `/scoped-models`."
- `docs/settings.md:192`: "No match -> spawn fails clearly. An empty `/scoped-models` means unrestricted."
- `src/orch/runtime.ts:224-228`: `restricted = filtering && scopedModels.length > 0`; when restricted, only models in `ctx.scopedModels` that also have credentials (`availableScopedModels`, `:214`) are eligible.
- `src/prefs/models.ts:58-63`: the first entry of the agent's `models` list found among those eligible wins; otherwise it throws `ModelPreferenceError`, with no fallback.

Scoped is the main session's `/scoped-models` list, not a subagent-manager setting. The package source does not read `enabledModels`; the link from `enabledModels` to `/scoped-models` is in pi core, which is outside this package (INFERRED, not read). Because `enabledModels` is non-empty in coordinator/pi/settings.json, the scope is restricted, so `morph/morph-dsv41flash` is added to it.

## Proof command

Before (origin/main):

    AssertionError: ['architect.yml', 'coder.yml', 'researcher.yml', 'reviewer.yml', 'tasker.yml', 'writer.yml']

After (this branch): exit 0.

## Merge check with PR #899 (origin/mo898-defaulttools)

See PR body.
