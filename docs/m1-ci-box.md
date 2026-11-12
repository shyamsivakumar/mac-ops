# M1 CI box hygiene (MO-122)

Historical MO-122 disk, Spotlight and quit ledger from 2026-11-02.
Woodpecker and its maintenance jobs were disabled on 2026-11-11 (MO-183);
see [shutdown and rollback evidence](../evidence/MO-183/decisions.md).
The measurements and retained-data inventory below are historical, not current.

Reach the box with `ssh m1` (`Host m1` → `shyams-m1`).

## Before / after (2026-11-02 ~18:46 → 19:02 PT)

| Sample | Free | Cap | Swap | Load (1/5/15) | mds |
| --- | --- | --- | --- | --- | --- |
| Before 18:48 | 9.7 GiB | 98% | 1.3 GiB | 4.9 / 6.4 / 6.4 | ~0% |
| After 19:02 | **51 GiB** | 89% | 1.4 GiB | 13 / 12 / 9.5 | ~0% |

Target **≥25% free** (~115 GiB) is **not met yet**. Remaining space is
blocked on items that need Shyam (below). Daily hygiene will hold the
gain and alert below 15%.

Evidence on the M1:

- `~/Library/Logs/woodpecker/mo122-disk-before.txt`
- `~/Library/Logs/woodpecker/mo122-after.txt`
- `~/Library/Logs/woodpecker/mo122-deleted.tsv` (~72.8 GiB recorded)
- `~/Library/Logs/woodpecker/mo122-needs-shyam.tsv`
- `~/Library/Logs/woodpecker/mo122-apps-before-uninstall.tsv`
- `~/Library/Logs/woodpecker/mo122-quit.log`
- `~/Library/Logs/woodpecker/mo122-undo.txt`

## Retired disk hygiene

The Woodpecker disk-hygiene and cache-cleanup jobs are disabled (MO-183).
Their scripts and bootstrap instructions have been removed from this repo.

## What was deleted (rebuildable) — summary

Logged with path/bytes in `mo122-deleted.tsv`. High level:

| Kind | Approx freed | Notes |
| --- | --- | --- |
| Xcode DerivedData (>2d, 20 GiB cap) | ~55 GiB | Local only |
| App uninstalls (user-writable) | ~8 GiB | ChatGPT, Arc, Dia, Ollama, … |
| Package / tool caches | ~6–8 GiB | Homebrew, npm, bun, swiftpm, … |
| Unused simulator devices | ~0.2 GiB | Kept `CI-iPhone` + iOS 27 runtime |
| Docker dangling + build cache | ~0.3 GiB | Inside Colima; disk file ~69 GiB |
| Logs &gt;7 days, Trash | small | |

**Not deleted** (needs sudo or Shyam): Apple iMovie/GarageBand/Keynote/Pages/Numbers,
Microsoft Office suite, Chrome, WhatsApp, Slack, Logi Options+, Zoom.app,
and other root-owned `/Applications` entries listed in
`mo122-apps-before-uninstall.tsv`.

## Needs Shyam (top space + data)

Do **not** delete without an explicit OK. Top items by size after cleanup:

| Path | Size | Why held |
| --- | --- | --- |
| `~/.colima` | 69 GiB | Live Colima VM (80 GiB alloc) |
| `~/.local/state/alpha-trader` | 48 GiB | Paper trader state; agent disabled |
| `~/_archive-mo122-20261102/ios-studio-migration-20261018` | 12 GiB | Confirm |
| `~/Applications/Xcode.app` | 8.5 GiB | **Keep** (CI). |
| `~/Library/Developer/CoreSimulator` | 4.2 GiB | `CI-iPhone`; **keep** |
| `~/Code/woodpecker-ci` | 3.8 GiB | Live, dirty; **keep** |
| `/Applications/iMovie.app` (+ others) | ~20 GiB | Needs `sudo rm` |
| `~/Code/CineJar`, `catalogue`, `fantasy-football-toolkit` | ~1 GiB | Keep |
| `Documents` / `Desktop` / `Downloads` | unknown | TCC blocks `du`; untouched |
| `~/.local/state/strategy-paper{,-deployments}` | ~0.9 GiB | Paper history |

To cross **25% free**, the usual path is: delete `alpha-trader` state
(+ optional archive + sudo app removals) in a non-deploy window.

## Spotlight

`mdutil -i off /System/Volumes/Data` requires root (failed without sudo).
Exclusions placed via `.metadata_never_index` on:

- `~/Code`, `~/.colima`, `~/Library/Logs/woodpecker`
- `~/Library/Developer/Xcode/DerivedData`
- `~/Library/Developer/CoreSimulator`
- `/var/lib/woodpecker-cache` (when present)

**mds CPU:** before pass ~0% (idle sample; earlier ticket sample 106%);
during exclusions `spotlightknowledged.updater` peaked ~89%; after ~0%.

One-line enable-off (Shyam, on the M1):

```sh
sudo mdutil -i off /System/Volumes/Data
# undo: sudo mdutil -i on /System/Volumes/Data
```

## Non-CI agents quit / disabled

### Trading (Shyam: unused on M1 — disabled 2026-11-02)

Archive:
`~/Library/LaunchAgents/_disabled-mo122-20261103T025356Z/`

- `com.alpha-trader`: ran `pm2 resurrect` (RunAtLoad). Exited 0, absent after.
  Last log: pm2 footer in `~/.pm2/launchd-out.log`. Undo:

  ```sh
  D=~/Library/LaunchAgents; A=$D/_disabled-mo122-20261103T025356Z; L=com.alpha-trader
  mv $A/$L.plist $D/ && launchctl enable gui/$(id -u)/$L
  launchctl bootstrap gui/$(id -u) $D/$L.plist
  ```

- `com.shyamsivakumar.strategy-paper`: KeepAlive wrapper on `:8788`. Not
  loaded, absent after. Last log: `shutting_down:SIGTERM` in
  `~/.local/state/strategy-paper/launch-stdout.log`. Undo:

  ```sh
  D=~/Library/LaunchAgents; A=$D/_disabled-mo122-20261103T025356Z
  L=com.shyamsivakumar.strategy-paper
  mv $A/$L.plist $D/ && launchctl enable gui/$(id -u)/$L
  launchctl bootstrap gui/$(id -u) $D/$L.plist
  ```

Confirm: `launchctl list | grep -Ei 'alpha-trader|strategy-paper'` → empty;
no matching processes.

### Logitech / Zoom / Apple Intelligence

Domain for user agents: `gui/$(id -u)`. Archive (if a plist was moved):
`~/Library/LaunchAgents/_disabled-mo122-20261103T025356Z/`.

Domain `D=gui/$(id -u)`. After any `bootout`, `enable` alone is not enough —
the job definition is gone until `bootstrap` from a plist path.

User-domain undo pattern (bootout + disable):

```sh
D=gui/$(id -u)
A=~/Library/LaunchAgents/_disabled-mo122-20261103T025356Z
P=~/Library/LaunchAgents
# 1) Prefer an archived user copy — move it back (must succeed).
if [ -f "$A/LABEL.plist" ]; then
  mv "$A/LABEL.plist" "$P/LABEL.plist"
  PLIST=$P/LABEL.plist
# 2) Else bootstrap directly from the vendor/system plist (do not mv).
elif [ -f /Library/LaunchAgents/LABEL.plist ]; then
  PLIST=/Library/LaunchAgents/LABEL.plist
elif [ -f "$P/LABEL.plist" ]; then
  PLIST=$P/LABEL.plist
else
  echo "no plist for LABEL" >&2; exit 1
fi
launchctl enable "$D/LABEL"
launchctl bootstrap "$D" "$PLIST"   # required after bootout; use $PLIST as-is
```

| Label | What we did | Plist to bootstrap |
| --- | --- | --- |
| `com.logitech.LogiRightSight.Agent` | bootout+disable | archive/vendor plist |
| `com.logi.cp-dev-mgr` | bootout+disable | archive/vendor plist |
| `us.zoom.updater` | bootout+disable | archive/vendor plist |
| `us.zoom.updater.login.check` | bootout+disable | archive/vendor plist |
| `com.apple.intelligence*` | **disable only** | `enable` + `kickstart` |

Apple labels (disable only): `intelligenceplatformd`, `intelligencetasksd`,
`callintelligenced`, `intelligenceflowd`, `intelligencecontextd`,
`visualintelligenced`. Undo: `launchctl enable D/LABEL && launchctl kickstart D/LABEL`.

Reopening an app alone does **not** reverse `bootout` or `disable`.

System LaunchAgents/Daemons (still need sudo; not fully disabled yet):

- `/Library/LaunchAgents/com.logi.optionsplus.plist`
- `/Library/LaunchAgents/com.logitech.LogiRightSight.Agent.plist`
- `/Library/LaunchDaemons/com.logi.optionsplus.updater.plist`
- `/Library/LaunchAgents/us.zoom.updater.plist`
- `/Library/LaunchAgents/us.zoom.updater.login.check.plist`

```sh
# disable (Shyam):
sudo launchctl bootout system/com.logi.optionsplus.updater
sudo launchctl disable system/com.logi.optionsplus.updater
# undo:
sudo launchctl enable system/com.logi.optionsplus.updater
sudo launchctl bootstrap system /Library/LaunchDaemons/com.logi.optionsplus.updater.plist
```

## Archived leftovers (same disk)

`~/_archive-mo122-20261102/`:

- `ios-studio-migration-20261018` (12 GiB) — confirm delete to free space
- `scrapers.stale-20260626`
- `.strategy-paper-stage-direct-20261019T051500Z`

## Do not

- Restart Colima / Docker agents / native agent during an SRW `deploy`
- Delete `/var/lib/woodpecker-cache` or `woodpecker-ci-*` volumes
- Delete `CI-iPhone` or its iOS runtime
- Touch `Documents` / `Desktop` / `Downloads` or clones with unpushed work
- Re-enable archived trading LaunchAgents without coordinator OK
