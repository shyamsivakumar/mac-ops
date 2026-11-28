## Proof run: red ccfc6b6db02c998fe6e8e727324ef92d22b4332c

```sh
test -f scripts/worktree-cleaner/scan.sh || { echo "MISSING scripts/worktree-cleaner/scan.sh"; exit 1; }
d=$(mktemp -d)
printf 'import sys\nprint("--no-report --prune --archive --delete" if "--help" in sys.argv else "{}")\n' > "$d/cleaner.py"
WORKTREE_PANEL_STATE="$d/panel" WORKTREE_CLEANER="$d/cleaner.py" WORKTREE_CLEANER_STATE="$d/state" sh scripts/worktree-cleaner/scan.sh scan start || exit 1
i=0
until grep -q '"state":"done"' "$d/panel/status.json" 2>/dev/null; do i=$((i+1)); [ "$i" -gt 100 ] && { echo "scan did not finish"; cat "$d/panel/status.json"; exit 1; }; sleep 0.1; done
python3 -c "import install_coordinator as i,pathlib;h=pathlib.Path('/h');c=pathlib.Path('.').resolve();t=[str(x[1]) for x in i.plan(c,h)];assert '/h/.local/bin/worktree-scan' in t,t;r={str(p):d for d,p in i.render_plists(c,h)};d=r['/h/Library/LaunchAgents/com.shyam.worktree-scan.plist'];assert b'herdr-app' not in d and b'/h/.local/bin/worktree-scan' in d;print('scan ok')"
```

```
MISSING scripts/worktree-cleaner/scan.sh

```

{"state": "red", "exit": 1, "matched": true, "ref": "ccfc6b6db02c998fe6e8e727324ef92d22b4332c"}
## Proof run: green 24464f93d28ce2d68d36d6deec6453286024d08e

```sh
test -f scripts/worktree-cleaner/scan.sh || { echo "MISSING scripts/worktree-cleaner/scan.sh"; exit 1; }
d=$(mktemp -d)
printf 'import sys\nprint("--no-report --prune --archive --delete" if "--help" in sys.argv else "{}")\n' > "$d/cleaner.py"
WORKTREE_PANEL_STATE="$d/panel" WORKTREE_CLEANER="$d/cleaner.py" WORKTREE_CLEANER_STATE="$d/state" sh scripts/worktree-cleaner/scan.sh scan start || exit 1
i=0
until grep -q '"state":"done"' "$d/panel/status.json" 2>/dev/null; do i=$((i+1)); [ "$i" -gt 100 ] && { echo "scan did not finish"; cat "$d/panel/status.json"; exit 1; }; sleep 0.1; done
python3 -c "import install_coordinator as i,pathlib;h=pathlib.Path('/h');c=pathlib.Path('.').resolve();t=[str(x[1]) for x in i.plan(c,h)];assert '/h/.local/bin/worktree-scan' in t,t;r={str(p):d for d,p in i.render_plists(c,h)};d=r['/h/Library/LaunchAgents/com.shyam.worktree-scan.plist'];assert b'herdr-app' not in d and b'/h/.local/bin/worktree-scan' in d;print('scan ok')"
```

```
started
scan ok

```

{"state": "green", "exit": 0, "matched": null, "ref": "24464f93d28ce2d68d36d6deec6453286024d08e"}

## Forwarder run (not the ticket proof): `sh <old path> scan` from a temp HOME, exec bits off, ends done

## Proof run: green 24464f93d28ce2d68d36d6deec6453286024d08e

```sh
test -f scripts/worktree-cleaner/scan.sh || { echo "MISSING scripts/worktree-cleaner/scan.sh"; exit 1; }
d=$(mktemp -d)
printf 'import sys\nprint("--no-report --prune --archive --delete" if "--help" in sys.argv else "{}")\n' > "$d/cleaner.py"
WORKTREE_PANEL_STATE="$d/panel" WORKTREE_CLEANER="$d/cleaner.py" WORKTREE_CLEANER_STATE="$d/state" sh scripts/worktree-cleaner/scan.sh scan start || exit 1
i=0
until grep -q '"state":"done"' "$d/panel/status.json" 2>/dev/null; do i=$((i+1)); [ "$i" -gt 100 ] && { echo "scan did not finish"; cat "$d/panel/status.json"; exit 1; }; sleep 0.1; done
python3 -c "import install_coordinator as i,pathlib;h=pathlib.Path('/h');c=pathlib.Path('.').resolve();t=[str(x[1]) for x in i.plan(c,h)];assert '/h/.local/bin/worktree-scan' in t,t;r={str(p):d for d,p in i.render_plists(c,h)};d=r['/h/Library/LaunchAgents/com.shyam.worktree-scan.plist'];assert b'herdr-app' not in d and b'/h/.local/bin/worktree-scan' in d;print('scan ok')"
h=$(mktemp -d)
python3 - "$h" <<'PY'
import install_coordinator as i, pathlib, shutil, sys
h = pathlib.Path(sys.argv[1])
plan = {str(t): (s, mode) for s, t, mode in i.plan(pathlib.Path(".").resolve(), h)}
old = h / ".config/herdr-app/mods/worktrees/scan.sh"
source, mode = plan[str(old)]
assert mode == 0o755, oct(mode)
old.parent.mkdir(parents=True)
shutil.copy(source, old)
old.chmod(0o644)
new = h / ".local/bin/worktree-scan"
new.parent.mkdir(parents=True)
shutil.copy("scripts/worktree-cleaner/scan.sh", new)
new.chmod(0o644)
PY
HOME="$h" WORKTREE_PANEL_STATE="$h/panel" WORKTREE_CLEANER="$d/cleaner.py" WORKTREE_CLEANER_STATE="$h/state" sh "$h/.config/herdr-app/mods/worktrees/scan.sh" scan || exit 1
i=0
until grep -q '"state":"done"' "$h/panel/status.json" 2>/dev/null; do i=$((i+1)); [ "$i" -gt 100 ] && { echo "forwarder scan did not finish"; cat "$h/panel/status.json"; exit 1; }; sleep 0.1; done
echo "forwarder ok"
```

```
started
scan ok
started
forwarder ok

```

{"state": "green", "exit": 0, "matched": null, "ref": "24464f93d28ce2d68d36d6deec6453286024d08e"}

## Selftest case scan-forwarder

```
PASS scan-forwarder
FAIL lines: 0
on origin/main the case does not exist, and the installer plan has no forwarder target (KeyError in the case)
```
