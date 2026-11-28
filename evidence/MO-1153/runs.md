## Proof run: red 7440faf334d72b5de35399a86957a40def69a873

```sh
python3 - <<'PY'
import pathlib, sys
import install_coordinator as i
home = pathlib.Path("/h")
targets = [str(t) for _, t, _ in i.plan(pathlib.Path(".").resolve(), home)]
bad = [t for t in targets if ".config/herdr-app" in t or t.endswith(".coordinator/answers.js")]
if bad:
    print("FAIL targets", len(bad), bad[:3])
    sys.exit(1)
assert "/h/.local/bin/worktree-scan" in targets
print("installer plan has", len(targets), "targets, none under herdr-app")
PY
```

```
FAIL targets 79 ['/h/.coordinator/answers.js', '/h/.config/herdr-app/mods/coordinator/answers.js', '/h/.config/herdr-app/keys.json']

```

{"state": "red", "exit": 1, "matched": true, "ref": "7440faf334d72b5de35399a86957a40def69a873"}
## Proof run: green fb6d91aa65778f56e170ac7ece15879ecca19070

```sh
python3 - <<'PY'
import pathlib, sys
import install_coordinator as i
home = pathlib.Path("/h")
targets = [str(t) for _, t, _ in i.plan(pathlib.Path(".").resolve(), home)]
bad = [t for t in targets if ".config/herdr-app" in t or t.endswith(".coordinator/answers.js")]
if bad:
    print("FAIL targets", len(bad), bad[:3])
    sys.exit(1)
assert "/h/.local/bin/worktree-scan" in targets
print("installer plan has", len(targets), "targets, none under herdr-app")
PY
```

```
installer plan has 67 targets, none under herdr-app

```

{"state": "green", "exit": 0, "matched": null, "ref": "fb6d91aa65778f56e170ac7ece15879ecca19070"}

## Installer status against the live home (read only), this head

```
{'in_sync': False, 'differs': ['/Users/shyamsivakumar/.local/bin/hourly_selftest.py', '/Users/shyamsivakumar/.local/bin/selftest.py']}
```

The two differing files are the live selftest copies, which still carry the removed scan-forwarder case until the installer runs after the merge.
