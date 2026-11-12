# MO-182 · Decisions ledger

- Ticket: shyamsivakumar/mac-ops#121 (Refs #121). Type: research, read-only report.
- Run id: `ticket:shyamsivakumar/mac-ops#121:a1`.
- Executed 2026-11-12 in a worktree from `origin/main` on branch `t3/mo-182-report`.
- Scope: report only. No install, no global setup change, no env var set, no API key, no hub/empq/installer/launchd change, no `.env` or credential read.

## Decisions made on the agent's own initiative

| # | Decision | Why it was not forced | Verdict | Confidence |
| --- | --- | --- | --- | --- |
| 1 | Wrote `evidence/MO-182/report.md` as the full report, `evidence/MO-182/findings.md` as the short answer, and `evidence/MO-182/decisions.md` as this ledger. | The ticket brief names `report.md`; issue #121 asks for `findings.md` and requires `decisions.md` in its Finish section. The issue's "must show only the findings file" is therefore read as "nothing outside `evidence/MO-182/`", which the report states. | sound | high |
| 2 | Treated "does omp load pi packages" as two questions: does omp read pi's *installed packages* (no) and can omp *load* a pi package (yes, via the `pi` manifest key). | The issue asks for one yes/no. Answering only "no" would have hidden the more useful half. | sound | high |
| 3 | Cited the package's own README and source files (read from GitHub and from the identical checkout already on this Mac) as the authority for version floors, memory and guard behaviour, rather than the issue's summary. | The issue says "claims to verify, not assume". | sound | high |
| 4 | Did not run `claude auth status` or open `~/.pi/agent/auth.json`, and did not measure memory locally. | Both are credential-adjacent or install-adjacent; the ticket forbids credential reads, and a real memory number needs a live provider session. | sound | high |
| 5 | Recommended against installing into omp, and named provider-registration compatibility as the risk. | The ticket forbids installs and asks for a recommendation only. | sound | medium |
| 6 | Reported pi's existing installation of the package (`~/.pi/agent/settings.json` `packages`) as context. | It changes the answer to "can pi use it" and is public configuration, not a secret. | sound | high |
| 7 | On the reviewer's MAJOR finding, replaced "omp offers the API the package needs" with the three concrete API mismatches, and changed the recommendation from "install as an omp plugin in a later ticket" to "an omp-native provider or a two-host package change is required". | The original claim was false; keeping any version of it would have supported an install recommendation that the evidence contradicts. | sound | high |

## In-session review round

One read-only review round, Claude Opus 5.5, against `git diff origin/main...HEAD` on the ticket text. Verdict: **FAIL**, one MAJOR finding.

- **MAJOR (fixed).** The first revision of `report.md` cited `types.ts:2033` as the API the package needs and said it was "exactly what `pi-claude-cli/index.ts:238` calls". It is not: omp declares `registerProvider(name, string, config)`, the package calls `pi.registerProvider(nativeProvider)` with one Provider object, and no adapter exists under omp's `src/extensibility/plugins/`. Fixed by stating the mismatch, adding the two further mismatches the fix uncovered (`registerApiProvider` from `@earendil-works/pi-ai/compat`, and `@earendil-works/pi-ai/providers/all`), and softening the conclusion to a static-evidence statement rather than a runtime claim.
- **Minor (fixed).** The first revision said the package "peers on `@earendil-works/pi-ai` and `@earendil-works/pi-coding-agent` 1.2.0". The peer ranges are `"*"`; the `1.2.0` pins are `devDependencies`. Corrected.
- **Minor (fixed).** "omp never reads `~/.pi/agent`" was too broad: `src/lsp/config.ts:408` reads `~/.pi/agent/lsp.*` for LSP settings. The sentence now names that exception and says it changes nothing here.
- **Minor (fixed).** `decisions.md` claimed the review findings "are recorded in the PR body" before a PR existed. That line now states the finding was fixed in the report and recorded here.
- **Minor (accepted, explained).** The diff shows three files rather than one. Explained in the report's "Scope note" and in decision 1 above; the issue itself requires two of the three.

No existing test or check was edited or weakened.

## Claims and their sources

Every factual claim in `report.md` is cited to a file and line: `README.md` (Quick start, Logging in, Processes and memory, Usage-credit guard, Configuration), `AGENTS.md`, `package.json`, `index.ts:21,22,166,238`, `src/cli-requirements.ts`, `src/provider-config.ts:65`, `src/claude-process-pool.ts:14-15`, `src/usage-credits.ts`; for pi 1.5.2 `@earendil-works/pi-coding-agent/dist/core/extensions/types.d.ts:1403`, `dist/core/model-registry.d.ts:54`, `node_modules/@earendil-works/pi-ai/dist/compat.d.ts:51`; for omp `@oh-my-pi/pi-coding-agent` `src/sdk.ts:552`, `src/config.ts:81`, `src/lsp/config.ts:408`, `src/extensibility/plugins/manager.ts:300`, `src/extensibility/plugins/loader.ts:194`, `src/extensibility/plugins/installer.ts:71,108`, `src/extensibility/plugins/legacy-pi-compat.ts:839,2724`, `src/extensibility/extensions/directory-resolution.ts:69`, `src/extensibility/extensions/types.ts:2033`, `src/config/model-registry.ts:3508`, `src/discovery/helpers.ts:842`, plus `@oh-my-pi/pi-ai/src/api-registry.ts:74-109` and the absence of `src/providers/all.ts`. The two version outputs are pasted verbatim in the report.

## Known limits

- The three API mismatches in section 3 of the report are static reading of two source trees; they are not confirmed at runtime, because confirming them needs an install, which this ticket forbids.
- The ~500 MB per process figure is the package author's number, not a measurement on this Mac.
- omp source quoted is from the installed 18.13.3 tree; the installed binary reports 18.14.0. pi source quoted is from the installed 1.5.2 tree.

## Proof

- `node --version` → `v22.23.1`; `claude --version` → `2.1.323 (Claude Code)`.
- `git diff --stat` shows only `evidence/MO-182/` files.
- `python3 scripts/mac_ops_fast_check.py` → passed.
- Full local check per `README.md` ("Check a task"): `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` → passed.
- One read-only in-session review round (Claude Opus 5.5) ran against the branch diff; its MAJOR finding is fixed above, and the follow-up verification of the fix is recorded in the PR body.
