import importlib.util
import json
import pathlib
import tempfile

spec = importlib.util.spec_from_file_location("fc", "scripts/mac_ops_fast_check.py")
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)
real = json.loads(pathlib.Path("scripts/finding_rules.json").read_text())
root = pathlib.Path(tempfile.mkdtemp())
(root / "fixture.py").write_text("for a, b in zip(x, y, " + "strict=True):\n    pass\n")
fc.ROOT = root
print("real rule:", fc.check_finding_rules(["fixture.py"], real))
good = {"id": "r", "paths": "*.py", "pattern": "x", "message": "m"}
for bad in (good, {**good, "check": "vibes"}):
    try:
        fc.check_finding_rules(["fixture.py"], [bad])
        print("bad rule accepted:", bad)
    except ValueError as e:
        print("bad rule refused:", e)
