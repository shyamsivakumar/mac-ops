# M1 dedicated CI box — two Linux lanes (MO-117)

Shyam's call (2026-11-02): no VPS and no hosted CI. The M1 is a dedicated
CI box. Linux CI stays on Colima as two Docker agents; the native macOS agent
keeps Xcode. Coordinate deploy labeling with SRW-349 (`role: deploy`).

Stack lives in `~/Code/woodpecker-ci` on the M1. Canonical copies of the
compose file, drain/reaper/backup scripts and LaunchAgent plists are versioned
here under [`scripts/woodpecker-ci/`](../scripts/woodpecker-ci/).

## Keep on the M1

- Woodpecker server, webhook proxy, `agent-linux`, `agent-deploy`, Colima
  profile `woodpecker` (LaunchAgents `com.shyamsivakumar.colima-woodpecker`
  and `…-watchdog`)
- Native agent `org.woodpecker.agent` (`shyams-macbook-pro-ios`, capacity 1)
- Tailscale, sshd, macOS system services
- Paper trader LaunchAgents: `com.alpha-trader`,
  `com.shyamsivakumar.strategy-paper`
- New: `com.shyamsivakumar.woodpecker-reaper`,
  `com.shyamsivakumar.woodpecker-backup-nightly`

Everything else that is not CI was quit and its user LaunchAgent archived to
`~/Library/LaunchAgents/_disabled-mo117-*` so it does not return after reboot.
TAL relaunch list is Finder-only. LogiOptionsPlus and Zoom agents under
`/Library/LaunchAgents` need sudo to disable permanently; they were killed
but may respawn until that is done by hand.

## Quit ledger (2026-11-02, RSS at quit)

| What | RSS (approx) | Action |
| --- | --- | --- |
| Arc (earlier pass) | ~2.2 GiB renderer + app | quit |
| ChatGPT / Codex UI (earlier) | ~hundreds of MiB | quit |
| Herdr / Activity Monitor / Safari / Messages | small | quit |
| FFT Auction LaunchAgent | 223 MiB; Chrome ~975 MiB | bootout, archive, kill |
| Fantasy-football cron LaunchAgents (8) | idle | bootout + archive |
| `com.shyam.*` scrapers (6) | idle | bootout + archive |
| reports-server | 8.7 MiB | bootout + archive |
| PostgreSQL@17 | 3.4 MiB | bootout + archive |
| Google Keystone / updater | idle | bootout + archive |
| pm2 `cli-proxy` | 2.7 MiB | deleted from pm2 |
| Codex app-server daemon | 44 MiB | killed |
| LogiOptionsPlus | 50–145 MiB | killed (may respawn from `/Library`) |

Full line log: `~/Library/Logs/woodpecker/mo117-quit.log` on the M1.

## Memory before / after

| When | Swap | Load (1/5/15) | Colima |
| --- | --- | --- | --- |
| Before cleanup (12:47 PT) | 9.5 / 10 GiB | ~7 / 11 / 18 | 6 GiB, 1 agent |
| After quit (12:57 PT) | 1.4 / 3 GiB | ~32 / 60 / 44 (iOS drain) | 6 GiB |
| After lanes (13:04 PT) | 1.3 / 3 GiB | ~4 / 19 / 29 | **10 GiB**, 2 agents |

## Agents

| Agent | Host / name | Backend | Capacity | Labels |
| --- | --- | --- | --- | --- |
| `ci-linux` | `agent-linux` (DB 17fcd710bf9a) | docker | **3** | linux/arm64 |
| `ci-deploy` | `agent-deploy` | docker | **1** | `!role=deploy,role=deploy` |
| macOS | `shyams-macbook-pro-ios` | local | **1** | platform darwin/arm64 |

`!role=deploy` means the deploy agent only takes workflows that set
`labels.role: deploy`. Unlabeled Linux checks go to `ci-linux` only.
SRW-349 must add `role: deploy` to `.woodpecker/deploy.yaml` so SRW deploys
use the exclusive lane.

Colima is sized at **10 GiB / 4 CPUs** so capacity 3 checks + 1 deploy fit on
the dedicated box. Native capacity stays 1. Do not raise native capacity on
this 16 GiB host without a dual-load proof.

## Drain before restart

Woodpecker cancels running workflows on agent shutdown. Always:

```sh
~/Code/woodpecker-ci/scripts/drain-agent.sh all   # or ci-linux / ci-deploy
```

The drain script refuses if an SRW `deploy` workflow is running. Never
`colima stop` / resize / `compose restart agent-*` during an SRW deploy.

Apply / resize helper: `scripts/apply-two-lanes.sh` (drains, sets Colima
memory, `compose up -d --remove-orphans`, installs reaper + nightly backup).

## Reaper

LaunchAgent `com.shyamsivakumar.woodpecker-reaper` every 5 minutes runs
`scripts/reaper.sh`: any pipeline still `running` with no `log_entries` for
10 minutes is marked `failure` (covers upstream #7063 stale-drop zombies).
Log: `~/Library/Logs/woodpecker/reaper.log`.

## Nightly SQLite backup

LaunchAgent `com.shyamsivakumar.woodpecker-backup-nightly` at 03:15 local runs
a hot `sqlite3 .backup` (agents stay up) and `scp`s to
`shyams-m4:~/Backups/woodpecker-ci/nightly-*` (14-day retention). Colima has
no host mounts, so the copy leaves the VM via `docker cp`.

Proof run 2026-11-02: `nightly-20261102T210502Z`, 5564 pipelines, ~1.5 GiB.

Cold restore still uses `scripts/backup.sh` / `restore.sh` (stops agents).

## Simulator

After each darwin/iOS job, shut down `CI-iPhone` so it does not sit Booted
(~1–1.5 GiB). Idle Booted sims are not CI.

```sh
xcrun simctl shutdown CI-iPhone
```

## Proof checklist (MO-117)

- [x] Swap/load before and after cleanup and lane split (tables above)
- [x] `agents` table: linux capacity 3, deploy capacity 1 with role labels,
      darwin capacity 1
- [x] Reaper + nightly backup LaunchAgents installed; backup landed on M4
- [x] Two Linux checks from different repos at once on `ci-linux` (2026-11-02
      13:11 PT): cairn pipeline 104 `ci` and SRW pipeline 2525 `verify`, both
      `running` on agent capacity 3 with two live `wp_*` containers
- [ ] SRW deploy overlapping those checks on `ci-deploy` — needs SRW-349
      `role: deploy` on deploy.yaml; until then unlabeled deploys share
      `ci-linux`. Agent 3 is registered and exclusive (`!role=deploy`).

## Do not

- Grow Colima above 10 GiB or `ci-linux` above 3 without a dual-load proof
- Restart Docker agents or Colima during an SRW deploy
- Re-enable archived non-CI LaunchAgents on the M1
- Put CI work on the M4
