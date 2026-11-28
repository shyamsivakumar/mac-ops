## Proof run: red e77cde7d4cd14a14e2f79f5fc229cf1cd2d1384e

```sh
python3 - <<'PY'
import pathlib, sys
import install_coordinator as i
gone = [p for p in ("coordinator/mods", "coordinator/herdr", "coordinator/rules", "tests/test_alarm_panel.py") if pathlib.Path(p).exists()]
if gone:
    print("FAIL still present", gone)
    sys.exit(1)
targets = i.plan(pathlib.Path(".").resolve(), pathlib.Path("/h"))
print("removed; installer plan still builds with", len(targets), "targets")
PY
```

```
FAIL still present ['coordinator/mods', 'coordinator/herdr', 'coordinator/rules', 'tests/test_alarm_panel.py']

```

{"state": "red", "exit": 1, "matched": true, "ref": "e77cde7d4cd14a14e2f79f5fc229cf1cd2d1384e"}
## Proof run: green 2042da5f3d8e5a507cc35a6b7439645d29cdb858

```sh
python3 - <<'PY'
import pathlib, sys
import install_coordinator as i
gone = [p for p in ("coordinator/mods", "coordinator/herdr", "coordinator/rules", "tests/test_alarm_panel.py") if pathlib.Path(p).exists()]
if gone:
    print("FAIL still present", gone)
    sys.exit(1)
targets = i.plan(pathlib.Path(".").resolve(), pathlib.Path("/h"))
print("removed; installer plan still builds with", len(targets), "targets")
PY
```

```
removed; installer plan still builds with 67 targets

```

{"state": "green", "exit": 0, "matched": null, "ref": "2042da5f3d8e5a507cc35a6b7439645d29cdb858"}
