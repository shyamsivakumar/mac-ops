# M1 dedicated CI box — two Linux lanes (MO-117)

Shyam's call (2026-11-02): no VPS and no hosted CI. The M1 is a dedicated
CI box. Keep only Woodpecker CI (and access), until the coordinator confirms
anything else. Linux CI stays on Colima as two Docker agents; the native
macOS agent keeps Xcode while jobs run. Coordinate deploy labeling with
SRW-349 (`role: deploy`).

Stack lives in `~/Code/woodpecker-ci` on the M1. Canonical copies of the
compose file, drain/reaper/backup scripts and LaunchAgent plists are versioned
here under [`scripts/woodpecker-ci/`](../scripts/woodpecker-ci/).

## Install / sync (canonical → M1)

From a checkout of this repo (SSH `Host m1` → `shyams-m1`):

```sh
chmod +x scripts/woodpecker-ci/*.sh
./scripts/woodpecker-ci/install-to-m1.sh
```

That copies `*.sh` → `~/Code/woodpecker-ci/scripts/` (mode `755`), and
`compose.yaml` + reaper/backup plists → `~/Code/woodpecker-ci/` (mode `644`).
`common.sh` must sit next to the other scripts; running a drained script
without it fails immediately. After sync, reaper/backup LaunchAgents already
point at those paths — `kickstart` them only if the plist contents changed.

## Keep (Woodpecker CI + reachability)

- Woodpecker server, **webhook-proxy** (`127.0.0.1:8001`, GitHub hooks),
  `agent-linux`, `agent-deploy`, Colima profile `woodpecker`
  (LaunchAgents `com.shyamsivakumar.colima-woodpecker`, `…-watchdog`)
- Native agent `org.woodpecker.agent` (`shyams-macbook-pro-ios`, capacity 1)
- Xcode / `CI-iPhone` simulator **only while a darwin job runs**; shut down after
- Tailscale, sshd, core macOS system services (Finder, WindowServer, mds, …)
- Reaper + nightly backup: `com.shyamsivakumar.woodpecker-reaper`,
  `com.shyamsivakumar.woodpecker-backup-nightly`

## Held for coordinator confirmation

Do **not** delete these until the coordinator says so. They are not Woodpecker
CI, but may serve other machines or the SRW paper path.

| Item | Why it might matter | Status now | Undo if removed later |
| --- | --- | --- | --- |
| `com.alpha-trader` | Paper-trader host | **kept**, idle | already loaded |
| `…strategy-paper` | Paper :8788 | **kept**, unloaded | `launchctl bootstrap` |
| webhook-proxy | GitHub → CI | **kept**, running | `docker compose up -d` |
| Heavy job queue on M1 | Not found listening | n/a | — |

No M1 listener looked like a shared heavy-queue endpoint. SRW live paper runs
on Railway; the local paper LaunchAgents are held only as a break-glass.

## Quit ledger (with one-line undo)

Archives on the M1:

- Pass 1: `~/Library/LaunchAgents/_disabled-mo117-20261102T205559Z/`
- Pass 2 (strict): `~/Library/LaunchAgents/_disabled-mo117-20261102T211321Z-strict/`

Line logs: `~/Library/Logs/woodpecker/mo117-quit.log` and
`mo117-quit-strict.log`. Login-item snapshot:
`~/Library/Preferences/ByHost/*.before-mo117` (TAL).

Domain: `gui/$(id -u)`. Restore helper for an archived plist `NAME.plist`:

```sh
A=~/Library/LaunchAgents/_disabled-mo117-20261102T205559Z
mv "$A/NAME.plist" ~/Library/LaunchAgents/ && \
  launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/NAME.plist
```

### Pass 1 — free memory for two lanes (≈12:50 PT)

| What | RSS (approx) | Action | Undo |
| --- | --- | --- | --- |
| Arc | ~2.2 GiB | quit | `open -a Arc` |
| ChatGPT / Codex UI | hundreds of MiB | quit | `open -a ChatGPT` |
| Herdr, Activity Monitor, Safari, Messages | small | quit | `open -a <App>` |
| FFT steel | 223 + 975 MiB | bootout, archive, kill | restore (helper) |
| FFT collector | idle | bootout + archive | restore (helper) |
| Fantasy cron agents (8) | idle | bootout + archive | restore (helper) |
| `com.shyam.*` scrapers (6) | idle | bootout + archive | restore (helper) |
| reports-server | 8.7 MiB | bootout + archive | restore (helper) |
| PostgreSQL@17 agent | 3.4 MiB | bootout + archive | restore (helper) |
| Google Keystone / updater | idle | bootout + archive | restore (helper) |
| pm2 `cli-proxy` | 2.7 MiB | `pm2 delete` | `pm2 resurrect`, or re-add |
| Codex app-server daemon | 44 MiB | kill | relaunch Codex.app |
| TAL relaunch list | — | Finder-only | restore `*.before-mo117` |

### Pass 2 — Woodpecker-only strict (≈13:13 PT)

| What | RSS (approx) | Action | Undo |
| --- | --- | --- | --- |
| Raycast | 29.3 MiB | quit | `open -a Raycast` |
| Ice | 19.8 MiB | quit | `open -a Ice` |
| Amphetamine | 23.8 MiB | quit | `open -a Amphetamine` |
| Rectangle | 21.8 MiB | quit | `open -a Rectangle` |
| Fleetsmith UI | 48–282 MiB | quit (MDM may relaunch) | `open -a Fleetsmith` |
| Notes/News/Stocks/Safari/Msgs/Term/Siri | 13–99 MiB | quit | `open -a <App>` |
| LogiOptionsPlus | 116–165 MiB | kill (sudo to disable) | reopen Logi app |
| ARDAgent | 6 MiB | kill (respawns) | `kickstart -activate` (sudo) |
| PM2 + modules | 63 MiB | `pm2 kill`; alpha-trader held | `kickstart` it |
| `com.ollama.ollama` | 5.2 MiB | bootout (plist kept) | `launchctl bootstrap` |
| Stale FFT/fantasy plists | — | archived `*-strict` | restore (helper) |
| Spotlight: Code, .colima, logs | — | `.metadata_never_index` | `rm` markers |

Jamf Protect and other MDM agents were left alone (device management).

## Memory before / after

| When | Swap | Load (1/5/15) | Colima |
| --- | --- | --- | --- |
| Before cleanup (12:47 PT) | 9.5 / 10 GiB | ~7 / 11 / 18 | 6 GiB, 1 agent |
| After quit (12:57 PT) | 1.4 / 3 GiB | ~32 / 60 / 44 (iOS drain) | 6 GiB |
| After lanes (13:04 PT) | 1.3 / 3 GiB | ~4 / 19 / 29 | **10 GiB**, 2 agents |
| After strict (13:13 PT) | 1.0 / 2 GiB | ~18 / 9 / 18 | 10 GiB; CI live |

## Agents

| Agent | Host / name | Backend | Capacity | Labels |
| --- | --- | --- | --- | --- |
| `ci-linux` | `agent-linux` (`17fcd710bf9a`) | docker | **3** | linux/arm64 |
| `ci-deploy` | `agent-deploy` | docker | **1** | `!role=deploy,role=deploy` |
| macOS | `shyams-macbook-pro-ios` | local | **1** | darwin/arm64 |

`!role=deploy` means the deploy agent only takes workflows that set
`labels.role: deploy`. Unlabeled Linux checks go to `ci-linux` only.
SRW-349 must add `role: deploy` to `.woodpecker/deploy.yaml`.

Colima: **10 GiB / 4 CPUs**. Native capacity stays 1.

## Drain before restart

```sh
~/Code/woodpecker-ci/scripts/drain-agent.sh all   # or ci-linux / ci-deploy / native
# … restart window …
~/Code/woodpecker-ci/scripts/drain-agent.sh --resume
```

Sets `agents.no_schedule=1` before waiting so nothing new (especially an SRW
deploy) starts mid-drain. Refuses if an SRW `deploy` workflow is running.
Never `colima stop` / resize / `compose restart agent-*` during an SRW deploy.
`apply-two-lanes.sh` drains with no_schedule, does **not** restart the native
agent, then `--resume`s after the new Docker agents are up.

## Reaper

`com.shyamsivakumar.woodpecker-reaper` every 5 minutes: pipelines still
`running` with no log for 10 minutes **and** no executor evidence (no queue
task, no `wp_*` containers / native children as applicable) → `failure` after
a re-check; also clears orphan workflows under terminal pipelines. Silence
alone is not enough. Log: `~/Library/Logs/woodpecker/reaper.log`.

## Nightly SQLite backup

`com.shyamsivakumar.woodpecker-backup-nightly` at 03:15 → hot
`sqlite3 .backup`, then `scp` to
`shyams-m4:~/Backups/woodpecker-ci/nightly-*` (14-day retention).

## Simulator

```sh
xcrun simctl shutdown CI-iPhone   # after each iOS job
```

## Proof checklist

- [x] Swap/load before and after cleanup and lane split
- [x] `agents`: linux cap 3, deploy cap 1 + role labels, darwin cap 1
- [x] Reaper + nightly backup; backup on M4
- [x] Two Linux checks concurrent on `ci-linux` (cairn 104 + SRW verify 2525)
- [ ] SRW deploy on `ci-deploy` overlapping checks — needs SRW-349 `role: deploy`

## Do not

- Grow Colima above 10 GiB or `ci-linux` above 3 without dual-load proof
- Restart Docker agents / Colima during an SRW deploy
- Re-enable archived non-CI LaunchAgents without coordinator OK
- Remove held paper-trader LaunchAgents without coordinator OK
- Put CI on the M4
