# MO-183 — Retire Woodpecker

- Ticket: https://github.com/shyamsivakumar/mac-ops/issues/122 (Refs #122).
- Run id: `ticket:shyamsivakumar/mac-ops#122:a1`.
- Executed 2026-11-11 PT / 2026-11-12 UTC. Base: `origin/main`, merge base `b33dbf28bb08575a212a8c64db12bc8622152711`.
- Authority: Shyam's 2026-11-11 “No woodpecker no actions only agentic ci” and “Do as recommended”, quoted in the ticket.

## Cause and decisions

The M1 had a running server, two Docker agents, a webhook proxy and native agent; all four Docker containers had `unless-stopped` restart policies. Eight launchd jobs were loaded, and 15 personal repositories had active hooks pointing to the M1 `/api/hook`. Removing a YAML file alone would leave the server receiving events and posting statuses.

Removed the repository's workflows, Woodpecker scripts/plists/compose overlay, Woodpecker-only safe-restart tests and lifecycle model/proofs, obsolete lane/memory/state-chart docs, and the ops status bar's Woodpecker-only SSH poll and display. The ticket explicitly requests removal of Woodpecker-only code/tests; no retained test or check was edited or weakened. Retained general SLO guidance and the historical MO-122 disk/quit ledger, removing obsolete setup instructions and broken links. Added the exact requested policy to root `AGENTS.md`, without changing globally installed agent rules.

No emp-hub, empq, routing or installer code changed. The generic SRW image-prune tool remains unchanged (its Docker-context example is not a Woodpecker dependency). Historical evidence/audit records remain unchanged.

**The Colima VM is shared:** four unrelated `srw*-trader` containers were running. Left the VM running and did not touch those containers. Disabled the Woodpecker Colima launch job/watchdog, but did not issue `colima stop`. Remaining host processes named `colima-woodpecker` are VM infrastructure, not a Woodpecker server or agent.

## M1 shutdown — exact commands

SSH preflight succeeded: `ssh -o BatchMode=yes -o ConnectTimeout=10 m1 'printf "MO-183 SSH available\\n"'`.

Executed remotely via `ssh m1` (no environment files, OAuth secrets, tokens or volume contents were read/copied):

```sh
set -eu
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
domain=gui/$(id -u)
for label in \
  com.shyamsivakumar.colima-woodpecker-watchdog \
  com.shyamsivakumar.woodpecker-reaper \
  com.shyamsivakumar.woodpecker-backup-nightly \
  com.shyamsivakumar.woodpecker-ci-slo-daily \
  com.shyamsivakumar.woodpecker-cache-cleanup \
  com.shyamsivakumar.woodpecker-disk-hygiene \
  org.woodpecker.agent \
  com.shyamsivakumar.colima-woodpecker
do
  launchctl disable "$domain/$label"
  launchctl bootout "$domain/$label"
done
docker --context colima-woodpecker update --restart=no \
  woodpecker-ci-server-1 woodpecker-ci-agent-linux-1 \
  woodpecker-ci-agent-deploy-1 woodpecker-ci-webhook-proxy-1
docker --context colima-woodpecker stop --timeout 30 \
  woodpecker-ci-server-1 woodpecker-ci-agent-linux-1 \
  woodpecker-ci-agent-deploy-1 woodpecker-ci-webhook-proxy-1
```

All commands succeeded. No `down`, `rm`, prune, image removal or volume removal was performed. Plists, containers, VM, caches, stack directory and data remain in place.

## Removed GitHub hooks

Enumerated **35 personal repositories including private repos** using paginated `gh api 'user/repos?affiliation=owner&per_page=100'`, filtering owner `shyamsivakumar`. Inspected hooks in memory, printing only hook IDs, events and URL host/path (never secrets). Deleted only hooks matching host `shyams-m1.tail60eda9.ts.net`, path `/api/hook`, using `gh api --method DELETE repos/<owner>/<repo>/hooks/<id>`; each succeeded.

| Repository (owner shyamsivakumar) | Removed hook ID |
| --- | --- |
| alpha-agent | 655970164 |
| cairn | 664554703 |
| catalouge | 690536294 |
| CineJar | 690536168 |
| fantasy-football-toolkit | 673849071 |
| mac-ops | 704852899 |
| openscan | 706645926 |
| qabot | 698248349 |
| recoup | 698248319 |
| sams-llm-wiki | 698248329 |
| scrapers | 655651685 |
| scripture-scroll | 704929540 |
| strata | 667137540 |
| strategy-replay-workbench | 698248364 |
| tunerise | 706628437 |

Repeated hook enumeration across all 35 repositories: **zero hooks remain**. `gh api repos/shyamsivakumar/mac-ops/hooks` printed `[]`. Organization repos were not touched. Existing historical commit statuses were not rewritten.

## Proof

- Before shutdown: native agent PID 40488, four running Woodpecker containers, eight loaded launchd jobs, and the above 15 active hooks established the failure mechanism.
- After shutdown: `pgrep -x woodpecker-agent`, `pgrep -x woodpecker-server`, and `pgrep -f 'woodpecker-local-[0-9]+/workspace'` returned no matches. `launchctl list` contained no Woodpecker jobs. `launchctl print-disabled gui/$(id -u)` showed all eight labels disabled.
- Targeted `docker inspect` of the four containers showed `running=false restart=no` for each. All exited 0. Unrelated trader containers stayed up with their original uptime.
- All six Woodpecker named volumes remain: `woodpecker-ci-agent-config`, `woodpecker-ci-agent-deploy-config`, `woodpecker-ci-agent-linux-config`, `woodpecker-ci-agent-secret-data`, `woodpecker-ci-server-data`, `woodpecker-ci-server-secret-data`. Contents were not inspected.
- Local images unchanged: agent `12d5d663f213`, server `01e0c803abc9`, webhook proxy `72ddd6501911`.
- `ls .woodpecker scripts/woodpecker-ci`: exit 1, both paths “No such file or directory” (expected).
- `python3 -m unittest tests.test_hub_install`: **26 tests, OK**, 6.426s.
- `python3 -m unittest tests.test_hub_install verification.check_hub_auto_merge verification.check_hub_merge_evidence verification.check_hub_single_instance verification.check_hub_turn_budget`: **74 tests, OK**, 26.836s. These existing proofs use disposable homes/fakes, not the production hub. Retained hub test/proof files are unchanged.
- `node --check empryo/mods/ops/main.js`: exit 0. `git diff --check`: exit 0. No repository-wide check or heavy job ran.
- Toolchain autodetection found no test command; ran the existing Python unittest proofs directly instead.
- One diff-only `code-reviewer` round is required because this CI removal exceeds 200 changed lines. Requested reviewer: Claude Opus 5.5. Its verdict and reviewed head SHA are reported with the PR/final report; it must not execute proofs or contact production services.

## Rollback (only if separately authorized)

Revert the PR to restore repository files. On the M1, execute:

```sh
set -eu
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
domain=gui/$(id -u)
# Original plist locations; all retained in place.
for label in \
  com.shyamsivakumar.colima-woodpecker \
  org.woodpecker.agent \
  com.shyamsivakumar.woodpecker-reaper \
  com.shyamsivakumar.woodpecker-backup-nightly \
  com.shyamsivakumar.woodpecker-ci-slo-daily \
  com.shyamsivakumar.woodpecker-cache-cleanup \
  com.shyamsivakumar.woodpecker-disk-hygiene \
  com.shyamsivakumar.colima-woodpecker-watchdog
do
  case "$label" in
    com.shyamsivakumar.woodpecker-ci-slo-daily|com.shyamsivakumar.woodpecker-cache-cleanup|com.shyamsivakumar.woodpecker-disk-hygiene)
      plist="$HOME/Code/woodpecker-ci/$label.plist" ;;
    *) plist="$HOME/Library/LaunchAgents/$label.plist" ;;
  esac
  launchctl enable "$domain/$label"
  launchctl bootstrap "$domain" "$plist"
done
# If the VM has since stopped, wait for its Docker daemon before proceeding.
docker --context colima-woodpecker update --restart=unless-stopped \
  woodpecker-ci-server-1 woodpecker-ci-agent-linux-1 \
  woodpecker-ci-agent-deploy-1 woodpecker-ci-webhook-proxy-1
docker --context colima-woodpecker start \
  woodpecker-ci-server-1 woodpecker-ci-agent-linux-1 \
  woodpecker-ci-agent-deploy-1 woodpecker-ci-webhook-proxy-1
```

The ticket suggests re-running `scripts/woodpecker-ci/install-to-m1.sh` to restore hooks. Inspection showed that script **only copies the overlay**, and does not register GitHub hooks. After restoring repository files, it can restore the overlay, but hook restoration requires Woodpecker's authenticated repository repair/reactivation flow for each of the 15 repositories above. Reuse retained server configuration through its authorized UI; do not extract OAuth or webhook secrets. New hooks get new IDs. Hook configuration before deletion: active, events `deployment`, `pull_request`, `pull_request_review`, `push`, M1 endpoint `/api/hook` (ticket server URL `https://shyams-m1.tail60eda9.ts.net:8443`). Do not recreate secretless hooks manually.

No rollback has been executed. PR merge and external gate completion remain coordinator-owned.
