"""Offline command proof with temporary HOME, queue and executable boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
evidence = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix="coord-watch-proof-") as scratch:
    home = Path(scratch)
    binaries = home / "bin"
    binaries.mkdir()
    queue = home / "queue"
    queue.mkdir()
    fixture = json.loads((evidence / "complete.json").read_text())
    for name, value in fixture["queue"].items():
        (queue / ("dispatch.log" if name == "log" else name)).write_text(value if name == "log" else json.dumps(value))
    stub = "#!" + sys.executable + "\n" + r"""import json, os, sys
from pathlib import Path
home = Path(os.environ['HOME'])
with open(home / 'calls', 'a') as stream:
    stream.write(Path(sys.argv[0]).name + ' ' + ' '.join(sys.argv[1:]) + '\n')
fixture = json.loads(Path(os.environ['FIXTURE']).read_text())
if Path(sys.argv[0]).name == 'gh':
    kind = 'pulls' if '/pulls?' in sys.argv[2] else 'issues'
    print(json.dumps(fixture['github']['example/project'][kind]))
else:
    print(json.dumps({'threads': fixture['threads']}))
"""
    for name in ("gh", "t3mcp"):
        path = binaries / name
        path.write_text(stub)
        path.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
           "COORDQ_DIR": str(queue), "FIXTURE": str(evidence / "complete.json"), "PYTHONDONTWRITEBYTECODE": "1"}
    argv = [sys.executable, str(root / "coordinator/bin/coord-watch"), "--once", "--config",
            str(evidence / "config.json"), "--state", str(home / "watch.json")]
    before = {p.name: p.read_bytes() for p in queue.iterdir()}
    results = [subprocess.check_output(argv, env=env, text=True, timeout=150).strip() for _ in range(2)]
    calls = (home / "calls").read_text().splitlines()
    if sum(line.startswith("gh ") for line in calls) != 2:
        raise RuntimeError("second cycle did not reuse GitHub cache")
    if before != {p.name: p.read_bytes() for p in queue.iterdir()}:
        raise RuntimeError("queue source changed")
    if results[0] != results[1] or not results[0].startswith("BOARD "):
        raise RuntimeError("snapshot unstable")
    print("PASS: two actual command cycles, two GitHub calls total, queue unchanged, stable BOARD output")
    print(results[0])
