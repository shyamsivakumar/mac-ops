# MO-725 runs

In-process run of watchdog_loop: fake clock (30s per sleep), limit 100s, registry reads raise after the first read, stub terminate, sleep stub that raises after 20 calls. Same script, two heavy.py files. Script source is below.

## origin/main (0dfc6efd)

```
iteration bound reached (20 sleeps), loop never returned
fake clock at end: 600s, limit 100s
terminate calls: []
```

## This branch

```
watchdog_loop returned 1
fake clock at end: 120s, limit 100s
terminate calls: ['watchdog-registry-failure-limit']
```

## Script

```python
import importlib.util, os, sys, tempfile
spec = importlib.util.spec_from_file_location("heavy_under_test", sys.argv[1])
h = importlib.util.module_from_spec(spec); sys.modules["heavy_under_test"] = h
spec.loader.exec_module(h)

NS = 1_000_000_000
now = [0]
calls = []
sleeps = [0]
reads = [0]
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "job1"))

class StopLoop(Exception):
    pass

class FakeRegistry:
    directory = __import__("pathlib").Path(tmp)
    def read_heartbeat(self, job_id):
        return now[0]

record = {
    "job_id": "job1", "task_key": "t", "uid": os.getuid(), "state": "running",
    "supervisor": {"boot_id": "boot", "pid": 1},
    "workload": {"uid": os.getuid(), "task_key": "t", "boot_id": "boot", "pgid": 99},
    "workload_started_ns": 1, "max_runtime_seconds": 100,
}

def fake_record(registry, job_id):
    reads[0] += 1
    if reads[0] > 1:
        raise OSError("registry unreadable")
    return dict(record)

def sleep(seconds):
    sleeps[0] += 1
    now[0] += 30 * NS
    if sleeps[0] >= 20:
        raise StopLoop()

def terminate(workload, **kw):
    calls.append(kw["reason"])
    return True

h._record = fake_record
try:
    rc = h.watchdog_loop("job1", FakeRegistry(), clock_ns=lambda: now[0], sleep=sleep,
        table_reader=lambda: {}, boot_reader=lambda: "boot", terminate=terminate)
    print("watchdog_loop returned", rc)
except StopLoop:
    print("iteration bound reached (20 sleeps), loop never returned")
print("fake clock at end: %ds, limit 100s" % (now[0] // NS))
print("terminate calls:", calls)
```
