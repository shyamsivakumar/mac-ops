# M1 Woodpecker memory budget (MO-116 → MO-117)

The M1 (`ssh m1`, 16 GiB RAM) is the dedicated CI box (MO-117): Colima
`woodpecker` with two Docker agents (`ci-linux` capacity 4, `ci-deploy`
capacity 1) plus the native macOS agent `shyams-macbook-pro-ios`
(`platform: darwin/arm64`, capacity 1). Current topology and quit ledger:
[m1-ci-lanes.md](m1-ci-lanes.md). Disk / Spotlight / non-CI agents (MO-122):
[m1-ci-box.md](m1-ci-box.md). Stack details live in the llmwiki Woodpecker
reference and `~/Code/woodpecker-ci` on the M1.

## Budget (MO-117)

| Piece | Intended | Oversubscribe risk |
| --- | --- | --- |
| Colima VM | 10 GiB, 4 CPUs | Above 10 GiB starves macOS + Xcode |
| `ci-linux` | `capacity = 4` | Raise only after dual-load proof |
| `ci-deploy` | `capacity = 1`, `role=deploy` | Never share with checks |
| Native agent | `MAX_WORKFLOWS=1` | `=2` (MO-72): two jobs fight VM |
| `CI-iPhone` | Boot only for iOS jobs | Idle Booted sim: ~1–1.5 GiB |

Native capacity 2 plus Colima oversubscribes RAM on this host. Desktop apps
and non-CI LaunchAgents were removed in MO-117 so the 10 GiB VM fits.

## MO-116 incident (2026-11-02)

Measured over `ssh m1` around 12:05–12:10 PT while CI was pending across SRW,
mac-ops, cairn, and catalogue:

| Sample | Swap used | Load averages | Notes |
| --- | --- | --- | --- |
| Before 12:05 | 9.7–9.9 of ~11 | ~11/8/7 (peak 19) | Colima 8G; max 2; sim on |
| Sim off, cap 1 12:07 | 9.58 | ~14.5/10.9/8.3 | Sim ~29M; `workflows: 1` |
| Colima 6G 12:09 | 9.02 of 10 | ~6.5/9.2/8.0 | `colima list` 6 GiB; agents up |
| Drain 12:10 | 9.02 | ~6/8.8/7.9 | 0 pipelines, 0 `wp_*`; `verify.sh` OK |

Largest host RSS before the fix was the Virtualization.framework VM process
for Colima. Stale (not live CI, not the paper-trader LaunchAgent): the Booted
`CI-iPhone` left after earlier iOS work. A fantasy-football Playwright cron was
left alone. No reboot, no Railway change, no paper-trader touch. Colima was
resized only after live Docker workflows and any deploy workflow were idle.

A `running` SQLite workflow is not stale just because there is no `wp_*`
container. Docker-agent jobs create those containers; native darwin jobs do
not. Treat a row as stale only with agent and process evidence: for Docker,
no matching `wp_*` container and the Docker agent idle on that workflow; for
native, the `org.woodpecker.agent` process has no children for that workflow
(and usually a lease/`task not found` history). Examples from this incident:
fantasy-football pipeline 891 (Docker, 2026-09-04) and native workflow 4254
(2026-10-30). See [woodpecker-runner](state-charts/woodpecker-runner.md).
Those rows did not block the Docker agent from taking new work after this fix.

## Applied controls

1. `xcrun simctl shutdown` on `CI-iPhone` when the native agent has no children.
2. Restore native capacity 1 from
   `~/Library/LaunchAgents/org.woodpecker.agent.plist.before-max2`, then
   `launchctl bootout` / `bootstrap` of `org.woodpecker.agent`. Confirm the
   agent log shows `parallel workflows: 1` and the SQLite `agents` row shows
   `capacity = 1`.
3. Set `memory: 6` in `~/.colima/woodpecker/colima.yaml` (stack README value;
   live had drifted to 8), `colima stop woodpecker`, then
   `launchctl kickstart -k gui/$(id -u)/com.shyamsivakumar.colima-woodpecker`.
   Restart the Docker agent and kickstart the native agent; run
   `~/Code/woodpecker-ci/scripts/verify.sh`.

Backups on the M1 from this change:
`org.woodpecker.agent.plist.before-mo116` and
`~/.colima/woodpecker/colima.yaml.before-mo116`.

## Do not

- Raise native `WOODPECKER_MAX_WORKFLOWS` above 1 on this 16 GiB host without
  also cutting Colima memory further and proving free memory under dual load.
- Grow the Colima VM above 6 GiB without the same proof.
- Leave `CI-iPhone` Booted after an iOS pipeline finishes.
- `colima stop` / resize while a live `wp_*` container or a deploy workflow is
  running.
- Reboot the M1 or change Railway to relieve swap.
