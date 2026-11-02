# M1 Woodpecker memory budget (MO-116)

The M1 (`ssh m1`, 16 GiB RAM) runs every personal-repo Woodpecker pipeline:
the Colima `woodpecker` VM (Docker agent, `platform: linux/arm64`) plus the
native macOS agent `shyams-macbook-pro-ios` (`platform: darwin/arm64`). Stack
details live in the llmwiki Woodpecker reference and `~/Code/woodpecker-ci` on
the M1.

## Budget

| Piece | Intended | Oversubscribe risk |
| --- | --- | --- |
| Colima VM | 6 GiB, 4 CPUs | 8 GiB leaves ~8 GiB for macOS, agent, sim |
| Docker agent | `capacity = 1` | One Linux workflow inside the VM |
| Native agent | `MAX_WORKFLOWS=1` | `=2` (MO-72): two jobs fight VM |
| `CI-iPhone` | Boot only for iOS jobs | Idle Booted sim: ~1–1.5 GiB |

Native capacity 2 plus the Docker agent oversubscribes RAM on this host. The
Docker agent's work sits inside the Colima reservation, so the dangerous
overlap is Colima memory plus one or two native Xcode/simulator jobs plus
ordinary desktop processes.

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

DB rows that stay `running` with no container (for example fantasy-football
pipeline 891 from 2026-09-04 and native workflow 4254 from 2026-10-30) are
stale queue artifacts; see [woodpecker-runner](state-charts/woodpecker-runner.md).
They did not block the Docker agent from taking new work after this fix.

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
