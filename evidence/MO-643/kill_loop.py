import json, random, signal, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRITER = """
import sys
sys.path.insert(0, %r)
sys.path.insert(0, %r)
sys.path.insert(0, %r)
import coordinator.overnight.lane_driver as lane
lane.LEDGER = sys.argv[1]
import json
docs = [json.load(open(p)) for p in sys.argv[2:4]]
print("ready", flush=True)
i = 0
while True:
    lane.save_ledger(docs[i %% 2])
    i += 1
""" % (str(ROOT), str(ROOT / "coordinator/overnight"), str(ROOT / "coordinator/bin"))

with tempfile.TemporaryDirectory() as scratch:
    scratch = Path(scratch)
    docs = [{"gen": g, "rows": [g * 40] * 60000} for g in ("a", "b")]
    files = []
    for doc in docs:
        path = scratch / f"{doc['gen']}.json"
        path.write_text(json.dumps(doc, indent=1))
        files.append(str(path))
    ledger = scratch / "lanes-ledger.json"
    ledger.write_text(json.dumps(docs[0], indent=1))
    print(f"ledger size about {ledger.stat().st_size / 1e6:.1f} MB")
    seen = {"a": 0, "b": 0}
    for i in range(50):
        proc = subprocess.Popen([sys.executable, "-c", WRITER, str(ledger), *files], stdout=subprocess.PIPE, text=True)
        assert proc.stdout.readline().strip() == "ready", "writer did not start"
        time.sleep(random.uniform(0.01, 0.3))
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        content = json.loads(ledger.read_text())
        assert content in docs, f"run {i}: ledger is neither document"
        seen[content["gen"]] += 1
    leftover = [p.name for p in scratch.iterdir() if p.name.endswith(".tmp")]
    print(f"50 kills during back-to-back saves, ledger parsed and equalled one full document every time: {seen}")
    print(f"tmp files left by killed writers (pid-named, never read as the ledger): {len(leftover)}")
