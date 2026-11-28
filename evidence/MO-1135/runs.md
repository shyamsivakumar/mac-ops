## Proof run: red 3da3cdbfbdbf536eaf3199bc7f48549b8b0a8151

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

{"state": "red", "exit": 1, "matched": true, "ref": "3da3cdbfbdbf536eaf3199bc7f48549b8b0a8151"}
## Proof run: green b685ec6a5660fcdb2cd502e0d9f267bbabcd96b1

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

{"state": "green", "exit": 0, "matched": null, "ref": "b685ec6a5660fcdb2cd502e0d9f267bbabcd96b1"}
