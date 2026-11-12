# MO-182 · Decisions ledger

- Ticket: shyamsivakumar/mac-ops#121 (Refs #121). Type: research, read-only report.
- Run id: `ticket:shyamsivakumar/mac-ops#121:a1`.
- Executed 2026-11-12 in a worktree from `origin/main` on branch `t3/mo-182-report`.
- Scope: report only. No install, no global setup change, no env var set, no API key, no hub/empq/installer/launchd change, no `.env` or credential read.

## Decisions made on the agent's own initiative

| # | Decision | Why it was not forced | Verdict | Confidence |
| --- | --- | --- | --- | --- |
| 1 | Wrote `evidence/MO-182/report.md` as the full report, and `evidence/MO-182/findings.md` as a short answer that points at it. | The ticket brief names `report.md`; issue #121 asks for `findings.md`. Both files exist so neither reader misses the deliverable. | sound | high |
| 2 | Treated "does omp load pi packages" as two questions: does omp read pi's *installed packages* (no) and can omp *load* a pi package (yes, via the `pi` manifest key). | The issue asks for one yes/no. Answering only "no" would have hidden the more useful half. | sound | high |
| 3 | Cited the package's own README and source files (read from GitHub and from the identical checkout already on this Mac) as the authority for version floors, memory and guard behaviour, rather than the issue's summary. | The issue says "claims to verify, not assume". | sound | high |
| 4 | Did not run `claude auth status` or open `~/.pi/agent/auth.json`, and did not measure memory locally. | Both are credential-adjacent or install-adjacent; the ticket forbids credential reads, and a real memory number needs a live provider session. | sound | high |
| 5 | Recommended against installing into omp, and named provider-registration compatibility as the unverified risk. | The ticket forbids installs and asks for a recommendation only. | sound | medium |
| 6 | Reported pi's existing installation of the package (`~/.pi/agent/settings.json` `packages`) as context. | It changes the answer to "can pi use it" and is public configuration, not a secret. | sound | high |

## Claims and their sources

Every factual claim in `report.md` is cited to a file and line: `README.md` (Quick start, Logging in, Processes and memory, Usage-credit guard, Configuration), `AGENTS.md`, `package.json`, `src/cli-requirements.ts`, `src/provider-config.ts:65`, `src/claude-process-pool.ts:14-15`, `src/usage-credits.ts`, and for omp `@oh-my-pi/pi-coding-agent` `src/sdk.ts:552`, `src/config.ts:81`, `src/extensibility/plugins/manager.ts:300`, `src/extensibility/plugins/loader.ts:194`, `src/extensibility/plugins/installer.ts:71,108`, `src/extensibility/extensions/directory-resolution.ts:69`, `src/extensibility/extensions/types.ts:2033`, `src/discovery/helpers.ts:842`, `src/extensibility/plugins/legacy-pi-compat.ts:2724`. The two version outputs are pasted verbatim in the report.

## Known limits

- Runtime behaviour of the provider inside omp is unverified; verifying it requires an install, which this ticket forbids.
- The ~500 MB per process figure is the package author's number, not a measurement on this Mac.
- omp source quoted is from the installed 18.13.3 tree; the installed binary reports 18.14.0.

## Proof

- `node --version` → `v22.23.1`; `claude --version` → `2.1.323 (Claude Code)`.
- `git diff --stat` shows only `evidence/MO-182/` files.
- One read-only in-session review round (Claude Opus 5.5) ran against the branch diff; its findings are recorded in the PR body.
