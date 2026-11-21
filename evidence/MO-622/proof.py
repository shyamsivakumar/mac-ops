import dataclasses, json, os, sys, tempfile, threading, time
from pathlib import Path

sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parents[2]))
import heavy

work = Path(tempfile.mkdtemp(prefix="mo622-"))
state, log = work / "booted", work / "log"
stub = work / "bin" / "xcrun"
stub.parent.mkdir()
stub.write_text(f"""#!/bin/bash
S={state}; L={log}; touch $S
case "$2" in
  list) python3 -c "import json;print(json.dumps({{'devices':{{'iOS 18':[{{'udid':u.strip(),'state':'Booted'}} for u in open('$S') if u.strip()]}}}}))" ;;
  boot) echo "$3" >> $S ;;
  shutdown) grep -vx "$3" $S > $S.n; mv $S.n $S; echo "shutdown $3" >> $L ;;
  erase|delete) echo "FORBIDDEN $2" >> $L ;;
esac
""")
stub.chmod(0o755)
os.environ["PATH"] = f"{stub.parent}:{os.environ['PATH']}"

sample = heavy.Sample(
    pressure_level=1, cpu_busy_pct=10, memory_used_pct=20, headroom_bytes=32 * heavy.GIB,
    physical_bytes=48 * heavy.GIB, load_per_core=0.1, captured_monotonic=0, free_percent=70,
    swap_growth_bytes_per_second=0, swapout_bytes_per_second=0, physical_cores=8)
heavy._read_capacity_config = lambda *a, **k: {"heavy_slots": 2}
heavy._legacy_draining = lambda *a, **k: False
deps = heavy.SupervisorDeps(
    sample=lambda: dataclasses.replace(sample, captured_monotonic=heavy.monotonic()),
    legacy_slots=lambda table: 0)


def scenario(name, jobs):
    state.write_text("OLD\n")
    log.write_text("")
    reg = heavy.Registry(Path(tempfile.mkdtemp(dir=work)))
    reg.directory.chmod(0o700)
    threads = [threading.Thread(target=lambda a=a, i=i: heavy.run_supervisor(a, registry=reg, task_key=f"k{i}", task_id=f"t{i}", deps=deps)) for i, a in enumerate(jobs)]
    for t in threads:
        t.start()
        time.sleep(0.8)
    for t in threads:
        t.join()
    print(f"[{name}] still booted: {state.read_text().split()}  simctl shutdown calls: {log.read_text().split(chr(10))[:-1]}")
    events = (reg.directory / "events.jsonl").read_text().splitlines()
    print("  events:", [(e["event"], e.get("detail")) for e in map(json.loads, events) if e["event"].startswith("simulator")])


scenario("job boots NEW, OLD booted before", [["xcrun", "simctl", "boot", "NEW"]])
scenario("job boots NEW while another heavy job runs", [["sleep", "4"], ["xcrun", "simctl", "boot", "NEW"]])
scenario("job boots nothing", [["xcrun", "simctl", "list", "devices"]])
