# MO-162 · Personal repo audit for the fast pipeline

- Ticket: https://github.com/shyamsivakumar/mac-ops/issues/83 (Refs #83).
- Type: research (audit, read only). Builder route: `task/research` (pi router).
- Base: `origin/main` at `5590c3b`. Audit date: 2026-11-12 PT.
- Scope: every repo in `coordinator/config/tickets.json` (15 repos), read only.
- Nothing was installed, no repo checkout other than this mac-ops worktree was
  written, no `.env` file was read, no secret was printed. The only git writes
  were `git fetch` in the 15 audited checkouts (read of remote refs) and the
  normal commit and push of this file in the mac-ops worktree.

## Names translated from the pre-cutover issue

The issue text predates the 2026-11-12 cutover from Empryo to T3 Code. Every
Empryo-era name in it maps to today's setup as follows.

| Issue text (Empryo era) | Today's setup |
| --- | --- |
| `~/.empryo/tickets.json` repo list | `coordinator/config/tickets.json` in this repo (same `repos` map, same keys) |
| `empq`, `emp-hub`, "hub merge train" | `coordinator/bin/coordq` and `coordinator/bin/ticket`; the merge train and the Cockpit merge relay now live in `coordinator/mods/cockpit/hub.js` |
| "agent rounds", "Empryo worker" | T3 Code threads driven by the pi task router (`task/research` for this ticket) |
| Woodpecker on the M1 (`shyams-m1`) | Retired. MO-183 shut the server, agents, webhook proxy and launchd jobs down on 2026-11-11. See `evidence/MO-183/decisions.md`. |
| "the Mac check publisher posts `srw/agent-check` on ready PRs" | Still true, and still the only such publisher: `com.srw.agent-check` launchd job runs `~/Library/Application Support/srw-agent-check/publisher.mjs`, which posts the commit status context `srw/agent-check` |
| "Opus gate merges on PASS" | Unchanged. The Cockpit merge relay refuses unless the review ends with `VERDICT: PASS` and `CHECK: PASS <sha>`, or `srw/agent-check` succeeded on the exact head SHA. `coordinator/mods/cockpit/hub.js` and `llmwiki/source/docs/how-to/cockpit-merge-relay.md` |
| "CI is agent checks only" | Now also a repo rule in `AGENTS.md`: no GitHub Actions, no Woodpecker workflows, ever |

## What "the fast pipeline" means now

The target pipeline, in the order the merge train runs it:

1. A worker gets a ticket, works in a fresh worktree from fresh `origin/main`.
2. A local check runs in that worktree and is recorded (SRW: the Mac publisher
   posts the `srw/agent-check` commit status on the ready PR head).
3. The Opus gate reviews the diff and merges on PASS.
4. The whole thing must fit in about five minutes of wall clock per ticket.

Only step 2 is per-repo. Everything else already exists in mac-ops and the
Cockpit mod. So the audit question for each repo is: what does this repo's
check entry point run, how long does it take, does it need Docker, and does a
ready PR in that repo actually get a check status posted on it.

## Method

For each repo in `coordinator/config/tickets.json` I read, at `origin/main`:

- `git ls-tree -r --name-only origin/main` filtered for `.github/workflows/`,
  `.woodpecker/`, `Makefile`, `justfile`, `scripts/check*`, `.githooks/pre-push`.
- The check entry point file itself (`scripts/check.sh`, `Makefile`,
  `package.json` `scripts.check`).
- The repo's own README gate instructions.
- `git config core.hooksPath` in the local checkout (is a pre-push hook
  installed here) and the committed `.githooks/pre-push` body.
- `git rev-list --count HEAD..origin/main` (how far the local `main` is behind).
- `gh pr list` (open PRs) and `gh api .../commits/<sha>/status` and
  `.../check-runs` for every open ready PR head (does a ready PR get a status).

Runtime numbers come from three sources, and each row says which:

- **MEASURED** here, in this session.
- **MEASURED** by the coordinator's CI SLO collector
  (`coordinator/evidence/ci-slo-2026-11-11.json`, `...-2026-11-10.json`),
  which is historical Woodpecker data and does not describe the local checks.
- **REPORTED** in the repo's own open PR body (the builder's own timing).
- **ESTIMATED** by reading the script, when no run exists. Marked as such.

Durations are wall clock including the `heavy` queue wait unless stated.

## Summary table

"Ready PR gets a check status" means: on an open, non-draft PR in that repo
today, does GitHub show a check run or a commit status on the head SHA that
came from a check, as opposed to nothing?

| Key | Repo | Local check entry point | Runtime | Docker | Ready PR gets a check status |
| --- | --- | --- | --- | --- | --- |
| SRW | strategy-replay-workbench | `scripts/check.sh` (`--push`, pr tier, `--full`) via `heavy` | MEASURED 106 s to 224 s per publisher run (pull lane 106 s to 129 s, main lane 220 s to 224 s) | Yes | Yes, `srw/agent-check` posted by the Mac publisher |
| MO | mac-ops | `python3 scripts/mac_ops_fast_check.py` via `heavy` | MEASURED 1.1 s plain, 7.5 s under `heavy` here. Historical CI p50 19 s run, 21 s total | No | No. The result is a `Builder check: PASS <sha>` line in the PR body, not a status |
| SCR | scrapers | `make check` to `bash scripts/check.sh` | UNKNOWN, no measurement | No | No |
| LMW | sams-llm-wiki | `python3 scripts/ci_acceptance.py` (and the other `scripts/verify_*.py`) | HISTORICAL CI p50 16 s to 18 s run, 20 s to 22 s total. No local measurement | No | No |
| STS | scripture-scroll | `npm run check` via `heavy` | UNKNOWN | No | No. No open PRs |
| JAR | CineJar | `npm run check` (lint, type-check, jest, smoke web) via `heavy npm ci && npm run check` | UNKNOWN | No | No. PR #20 shows only Woodpecker statuses from 2026-10-17, before the M1 shutdown |
| FFBT | fantasy-football-toolkit | `npm run check`, added by open PR #412 (not on main) | REPORTED 456.86 s including queue on one head, 237 s for the final clean-clone push | No | No. PR #412 shows only a Vercel check |
| OPN | openscan | `make check` to `./scripts/check.sh` | UNKNOWN | No | No. No open PRs |
| RCP | recoup | `make check` to `bash scripts/check.sh` | UNKNOWN | No | No. No open PRs |
| CTL | catalogue | `scripts/fast_check.py`, diff scoped, via `heavy` | UNKNOWN, but the script prints its own elapsed time and queue time | No | No. No open PRs |
| CRN | cairn | `pnpm check` to `bash scripts/check.sh` | UNKNOWN | **Yes.** `docker build` plus `docker run` in the check | No. No open PRs |
| TNR | tunerise | `make check`, added by open PR #20 (not on main) | REPORTED 44.65 s wall including heavy queue | No | No. PR #20 has no status |
| QBT | qabot | `make check`, added by open PR #80 (not on main) | REPORTED 9.652 s excluding heavy queue | No | No. PR #80 has no status |
| STR | strata | None. `lefthook.yml` pre-push only, ruff on changed Python files | UNKNOWN, but the pre-push scope is a few seconds | No | No. PR #3 has no status |
| NING | digitized/Concerning | None local. `.github/workflows/ci.yml` is the only CI, and it is live | MEASURED 2 min 9 s for the PR #59 head: 23:04:25 to 23:06:34 UTC | **Yes.** Postgres in a `docker run` container, plus a `docker build` | Yes, but by GitHub Actions, which the mac-ops rule forbids |

## Per repo detail

### SRW, strategy-replay-workbench

- Check: `scripts/check.sh`. Three tiers. `--push` is the cheap tier the
  pre-push hook runs (`.githooks/pre-push` ends with `exec scripts/check.sh
  --push`). No argument is the PR tier, a 60 second boot survive watch.
  `--full` is the 180 second watch the publisher runs on `main`.
- Runtime: MEASURED from the publisher's own log file timestamps under
  `~/Library/Logs/srw-agent-check`. Pull lane runs measured 106 s, 108 s, 117 s,
  129 s. Main lane (`--full`) runs measured 220 s, 224 s. The log body records
  per step elapsed seconds, so the split is visible.
- Docker: yes. The check builds the trader image, runs boot proofs, and runs
  the survive eval. The 180 second watch is nearly all of the main lane time.
- Ready PR status: yes. The publisher's pull lane posts the commit status
  context `srw/agent-check` on the exact head SHA of every open, non-draft
  PR. Verified: PR #922 head `2c232457` carries `srw/agent-check=success`.
  PR #929 head `5fb0a91` had no status at audit time, because the publisher
  runs one PR head per cycle and prefers `main`; the queue is short but not
  instant.
- Smallest change to the five minute pipeline: none on the SRW side. The
  PR tier at about 110 s plus queue is already inside the budget. The change
  belongs in mac-ops: move this publisher onto a generic runner so the other
  fourteen repos can post the same kind of status.

### MO, mac-ops

- Check: `python3 scripts/mac_ops_fast_check.py`. `README.md` says to run it
  as `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` and to set the
  board's `check.command` to that exact command.
- Runtime: MEASURED here. 1.08 s plain, 7.48 s under `heavy` (the delta is
  heavy admission and the TLC model check in the script). The coordinator's
  CI SLO file records a historical p50 of 19 s run and 21 s total for the
  retired Woodpecker `fast-check` lane.
- Docker: no.
- Ready PR status: no. The last five merged mac-ops PRs (#136, #141, #142 and
  two others) carry no check runs and no commit statuses. The evidence is the
  `Builder check: PASS <sha>` line in the PR body. `AGENT-RULES.md` requires
  exactly that line for repos other than SRW.
- Smallest change: point the generic runner at mac-ops with
  `{repo: shyamsivakumar/mac-ops, check: python3 scripts/mac_ops_fast_check.py,
  status context: mo/agent-check}`. The check already exists and is already
  fast. The gap is only the status.

### SCR, scrapers

- Check: `make check` runs `bash scripts/check.sh`. That does `uv sync
  --locked`, a `./verify.sh` pass, mypy on three source files, then a second
  `uv sync --extra dev` and ruff, vulture, pytest and compileall inside
  `fantasy-football-data`.
- Runtime: UNKNOWN. No measurement exists in the repo, in the CI SLO files,
  or in the PR body. The script is dominated by two `uv sync` runs and a
  pytest suite, so the honest estimate is minutes rather than seconds, but
  that is an ESTIMATE from reading the script, not a measurement.
- Docker: no.
- Ready PR status: no. PR #34 is ready and its head `7361968` has no check
  runs and no commit statuses.
- Pre-push: installed here. `core.hooksPath=scripts/githooks`, and the
  committed hook validates each pushed SHA in a clean temporary clone.
- Smallest change: measure `heavy make check` once and record it. If it is
  under three minutes, the only missing piece is a status, which the generic
  runner supplies.

### LMW, sams-llm-wiki

- Check: `python3 scripts/ci_acceptance.py`, which runs link audit, skill
  audit, eval-spec check, executable allowlist and the pinned governor
  snapshot.
- Runtime: HISTORICAL CI p50 16 s to 18 s run and 20 s to 22 s total across the
  acceptance, docs-check and verify lanes in `ci-slo-2026-11-11.json`. Those
  are Woodpecker numbers from before the M1 shutdown, and the local command
  has not been measured.
- Docker: no.
- Ready PR status: no. No open PRs, and no publisher.
- CI still present on `origin/main`: yes. `.woodpecker/acceptance.yaml`,
  `.woodpecker/docs-check.yaml` and `.woodpecker/verify.yaml` are still
  committed. They are dead files. The Woodpecker server and its agents were
  shut down by MO-183 on 2026-11-11, so nothing runs them and no status will
  ever appear from them.
- Smallest change: delete the three `.woodpecker/` files from `origin/main`
  and add a generic runner entry. The check script already exists and is
  already fast.

### STS, scripture-scroll

- Check: `npm run check`, a chain of `tsx` review-proof scripts plus
  `python3 scripts/check.py`. The committed `.githooks/pre-push` runs
  `heavy npm run check`.
- Runtime: UNKNOWN. The `check.py` wrapper passes a 600 second timeout to
  `npm run check:steps`, which is the only upper bound in the repo.
- Docker: no.
- Ready PR status: no. No open PRs.
- Smallest change: measure once, then add a runner entry.

### JAR, CineJar

- Check: `npm run check`, which is `npm run lint && npm run type-check && npm
  test -- --maxWorkers=2 && node scripts/smoke-web.cjs`. The committed
  pre-push hook runs `heavy bash -c 'npm ci --no-audit --no-fund && npm run
  check'` in a clean worktree.
- Runtime: UNKNOWN.
- Docker: no.
- Ready PR status: no. PR #20 is ready and its head `a296e75` carries only
  `ci/woodpecker/push/linux` and `ci/woodpecker/pr/linux`, both created
  2026-10-17, before the M1 shutdown. They are stale, not a live check.
- Smallest change: measure once, then add a runner entry.

### FFBT, fantasy-football-toolkit

- Check: `npm run check` does not exist on `origin/main`. Open PR #412 adds
  it: lint, tsgo and tsc typechecks, Knip, Vitest, the golden acceptance
  suite, the Python projection tests, a production build and a Woodpecker
  config lint.
- Runtime: REPORTED in PR #412's body. One local check on head `af83888a` took
  456.86 s including queue. The final clean-clone push including dependency
  install and queue took 237 s. So the check is roughly four to eight minutes.
  That does not fit the five minute pipeline.
- Docker: no.
- Ready PR status: no. PR #412's head `6bd621d` shows only
  `Vercel Preview Comments`.
- CI still present on `origin/main`: yes. Four `.woodpecker/` files, including
  `deploy-convex.yaml` which deploys production on `main`. Those are dead
  files now that the server is off.
- Smallest change: split the check. `npm run lint && npm run typecheck &&
  npm run test:run` is the bulk of the value and the bulk of the time; the
  production build and the Python suite can move to a nightly or main-only
  tier. Then add a runner entry. PR #412 also needs Shyam's explicit
  acceptance of losing the server-side verification gate, which its own body
  says is still outstanding.

### OPN, openscan

- Check: `make check` runs `./scripts/check.sh`: shell and Swift syntax
  parsing, required-file assertions, a debug `swift build`, and a release
  build plus real CLI acceptance through `scripts/ci-acceptance.sh` with a
  600 second timeout.
- Runtime: UNKNOWN. Swift release build and PDF acceptance are the slow part.
- Docker: no.
- Ready PR status: no. No open PRs.
- Smallest change: measure once, then add a runner entry. The Swift release
  build is the part most likely to blow the budget.

### RCP, recoup

- Check: `make check` runs `bash scripts/check.sh`: flow-doc lint, a locked
  `npm ci` in `convex`, Convex typecheck, Convex tests, and an iOS device
  compile with `xcodebuild` for the generic iOS destination. `make check-ios`
  is the simulator acceptance and is explicitly nightly, not a merge gate.
- Runtime: UNKNOWN. The `npm ci` and the iOS compile are the slow parts.
- Docker: no.
- Ready PR status: no. No open PRs.
- Pre-push: the README documents `bash scripts/install-hooks.sh` per worktree,
  but `core.hooksPath` is unset in this checkout, so no hook is active here.
- Smallest change: install the hook in every worktree, measure once, add a
  runner entry.

### CTL, catalogue

- Check: `scripts/fast_check.py`. It is already diff scoped: it computes the
  merge base against `origin/main`, classifies the change set (a docs-only
  path takes a fast route), then runs the selected steps through `heavy` and
  prints per-step elapsed time and queue time. It prints
  "Fast check passed in Ns. This is not the full suite."
- Runtime: UNKNOWN, but the script measures itself, so one run gives the
  number.
- Docker: no.
- Ready PR status: no. No open PRs.
- Pre-push: the committed `.githooks/pre-push` only runs `npm run typecheck`
  for touched Convex files. It is explicitly a cheap gate, not the check.
- Smallest change: this repo already has the most pipeline-shaped check of the
  fifteen. Run it once for a number, then add a runner entry.

### CRN, cairn

- Check: `pnpm check` runs `bash scripts/check.sh`. It refuses a dirty
  checkout, installs with `pnpm install --frozen-lockfile` into a temporary
  git dir, then runs turbo lint, typecheck, test and build, `node
  scripts/acceptance.mjs`, a web preview capture, the API integration tests,
  the Python worker lint and tests, and a Docker image build plus a
  Docker-based integration test, and finally a credential-name grep over
  `railway.toml` and `Dockerfile`.
- Runtime: UNKNOWN. This is the heaviest check of the fifteen.
- Docker: yes, unavoidably. `docker build` for the attempt runtime image and
  `docker run` for the integration test.
- Ready PR status: no. No open PRs.
- Smallest change: the Docker steps are the tail of the script and are the
  natural candidate for a separate tier. A PR tier of lint, typecheck, test,
  build and the Python worker checks, with the Docker image and integration
  test moved to a main-only run, is the change that makes this repo fit.

### TNR, tunerise

- Check: no `Makefile` on `origin/main`. Open PR #20 adds `make check`, which
  runs `heavy env TUNERISE_CHECK_SUPERVISED=1 ./scripts/check.sh`: script and
  Python syntax, fixture and docs assertions, Swift front-end parse of every
  file, `xcodegen`, an iOS simulator build, and the unit tests on a shared
  `CI-iPhone` simulator.
- Runtime: REPORTED 44.65 s wall including the heavy queue, 42 unit tests
  passing.
- Docker: no.
- Ready PR status: no. PR #20's head `8212bef` has no check runs and no
  commit statuses.
- CI still present on `origin/main`: yes, `.woodpecker/ios.yml` and
  `.woodpecker/linux.yml`. Dead files since the M1 shutdown.
- Smallest change: merge PR #20, then add a runner entry. The shared
  simulator is the constraint: the check needs `CI-iPhone` booted, so it is
  not parallel-safe the way a plain process check is.

### QBT, qabot

- Check: no `Makefile` on `origin/main`. Open PR #80 adds `make check` to
  `sh scripts/check.sh`: Ruff, mypy against a baseline of 43 pre-existing
  diagnostics, a locked sync, a CLI help check, and an isolated-home doctor
  run.
- Runtime: REPORTED 9.652 s excluding the heavy queue. This is the fastest
  check in the audit.
- Docker: no.
- Ready PR status: no. PR #80's head `49daa75` has no check runs and no
  commit statuses.
- CI still present on `origin/main`: yes, `.woodpecker/docs-check.yaml` and
  `.woodpecker/verify.yaml`. Dead files.
- Smallest change: merge PR #80, then add a runner entry. At ten seconds this
  repo is already inside the budget.

### STR, strata

- Check: none. `origin/main` has no `Makefile`, no `scripts/check.sh`, and no
  CI file. The only gate is `lefthook.yml`, a pre-push hook that runs Ruff
  check, Ruff format check and `compileall` on the changed Python files only.
  `package.json` has `test` (vitest), `lint` and `build` but no `check`.
- Runtime: UNKNOWN, but the lefthook scope is a few seconds of Ruff on
  changed files.
- Docker: no.
- Ready PR status: no. PR #3's head `4680ee6` has no check runs and no commit
  statuses.
- Smallest change: this repo needs a check script written, not wired. A
  `make check` that runs the lefthook steps plus vitest and the Python entry
  points is the missing piece, and then a runner entry.

### NING, digitized/Concerning

- Check: none local. `.github/workflows/ci.yml` is the only CI and it is
  live: scope classifier, workflow lint, docs fast path, acceptance, brain
  pytest, api vitest plus integration, web typecheck plus build, a ci gate,
  three deploy jobs and a post-deploy smoke job.
- Runtime: MEASURED from the check run timestamps on PR #59's head. The run
  starts at 23:04:25 UTC and the last successful job completes at 23:06:34
  UTC, so 2 min 9 s. That is inside the budget, but it is GitHub Actions, and
  it also deploys production from the same workflow.
- Docker: yes. Postgres runs in a `docker run` container with a pull and
  retry, and there is a `docker build` in the workflow.
- Ready PR status: yes, by GitHub Actions. PRs #54 through #59 show the full
  check run set with successes and skips.
- CI still present on `origin/main`: yes, and it is the one live violation of
  the "CI is agent checks only" rule in this audit. This repo is also the one
  whose origin is `digitized`, not `shyamsivakumar`.
- Smallest change: this is the repo where the rule bites hardest. Moving it
  to a local agent check removes the GitHub Actions dependency and the
  production deploy from the PR path at the same time, and its two minute
  measured runtime says the local check would fit the budget. Treat it as its
  own ticket with its own rollout, not as a line item.

## Cross cutting findings

1. **No repo outside SRW posts a check status on a ready PR.** Of the fifteen,
   one (SRW) has a publisher, one (NING) has live GitHub Actions, and the
   other thirteen have nothing. mac-ops records its result as a PR body line
   instead. This is the single largest gap against the fast pipeline.
2. **Four repos still carry eleven `.woodpecker/` files on `origin/main`:**
   LMW (3), FFBT (4), TNR (2), QBT (2). They are dead since the MO-183
   shutdown and will never produce a status. Deleting them is bookkeeping,
   not risk, but leaving them invites a false belief that CI is running.
3. **Two repos are one merge away from a usable check:** TNR through PR #20
   and QBT through PR #80. FFBT through PR #412, but that check is too slow
   as written.
4. **Two repos need a check written, not wired:** STR and NING.
5. **Docker is required by two repos only:** CRN (build plus run) and NING
   (Postgres). SRW builds images but its five minute tier is already sized
   around that.
6. **Local `main` is behind `origin/main` in twelve of fifteen checkouts.**
   Measured behind counts: STR 180, SRW 858, NING 66, JAR 61, FFBT 64, CRN 55,
   CTL 31, STS 28, SCR 26, OPN 11, TNR 6, RCP 3. Current in LMW and QBT, and
   in mac-ops itself. A local check that diffs against `origin/main` will
   misjudge the change set in the stale checkouts until they are fast
   forwarded.
7. **Runtime is unknown for nine of the fifteen checks.** No repo records its
   own check duration, and the coordinator's CI SLO files only cover the
   retired Woodpecker lanes for mac-ops, LMW and SRW. The single highest
   value next action is to measure the nine.

## Recommendation for the generic runner

Owner: mac-ops. The issue expects this and the design fits, because mac-ops
already owns the cross repo tooling and the ticket list.

Shape:

- One config file in mac-ops, `coordinator/config/repo_checks.json`, one entry
  per repo: `{repo, key, check, full, status_context, needs_docker}`.
  `check` is the PR tier command, `full` is the main tier command, `full`
  optional when the same command serves both. `status_context` defaults to
  `<key>/agent-check`, which keeps SRW's existing `srw/agent-check` unchanged.
- One runner, `scripts/agent_check_runner.py`, mirroring the SRW publisher's
  proven shape: a launchd job, a per SHA lock, a worktree per SHA, a journal
  file, `heavy --review` for the PR tier and `heavy --deploy` for the main
  tier, and a GitHub commit status on the exact head SHA. It reads the config
  and iterates repos.
- SRW's publisher moves onto this runner. The SRW specifics that must survive
  the move: the `--full` versus PR tier split, the 60 second versus 180
  second survive watch, the exact SHA verification, and the refusal to
  overwrite a status that changed while the check ran.
- The status is what the Cockpit merge relay needs. The relay already accepts
  `srw/agent-check` success on the exact head as an alternative to a completed
  Opus review, and refuses Ascend repos. Generalising the context from
  `srw/agent-check` to `<key>/agent-check` and teaching the relay the same
  rule for the other repos is a small, contained change to
  `coordinator/mods/cockpit/hub.js`.

Order of work, smallest first:

1. QBT and TNR: merge the open PRs, measure, add a config entry. Both are
   already inside five minutes.
2. LMW, STS, JAR, OPN, RCP, CTL, SCR: measure the existing check, add a
   config entry, delete the dead `.woodpecker/` files where present.
3. MO: add a config entry only. The check exists and is fast.
4. FFBT: split the check into PR tier and full tier first, then wire it.
5. CRN: split the Docker tail off, then wire it.
6. STR: write the check, then wire it.
7. NING: its own ticket. Moving off GitHub Actions is a policy change with a
   production deploy attached.

## Uncertainty

- Every runtime that is not marked MEASURED or REPORTED is unknown. The nine
  unknown numbers are the biggest hole in this audit, and the table says so
  rather than guessing.
- The SRW runtimes are wall clock from the publisher's log file timestamps,
  not from the check's own step timer. They include heavy queue wait. The
  publisher processes one PR head per cycle and prefers `main`, so a ready PR
  can wait several cycles for its status. That queue behaviour is measured
  only for the two lanes observed.
- The historical CI SLO numbers come from Woodpecker on the M1 and describe
  the retired lanes, not the local checks. They are useful as an order of
  magnitude and are not a baseline for the new pipeline.
- The publisher error log shows one recorded `github_api_failed` at
  2026-11-12 01:03. The publisher was healthy at audit time (launchd job
  `com.srw.agent-check` running, main lane posting successes), so the cause of
  that single failure is not known here.
- I did not run any repo's check. Running them is the measurement this audit
  recommends and is not free: heavy serialises one workload at a time and the
  turn budget was ten minutes.
- `core.hooksPath` reflects the local checkout on this Mac only. A repo can
  have a committed hook that is not installed in a given worktree.
- For FFBT and the other repos with open PRs, the described check is the PR's
  version, not what is on `origin/main` today.
