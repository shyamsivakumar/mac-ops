# MO-762 runs

Fixture adapted from the ticket: `time.monotonic()` starts near zero in a fresh process here, so `now-6.0` went negative; `now` is shifted by +1000. The sample also needs `free_percent`, both swap rates and `slot_limit=2`, otherwise admission returns `invalid-telemetry` before it reaches the age rule.

```
import heavy, time
now=time.monotonic()+1000.0
s=heavy.Sample(pressure_level=1,cpu_busy_pct=90.0,memory_used_pct=60.0,headroom_bytes=8*2**30,physical_bytes=36*2**30,load_per_core=2.9,captured_monotonic=now-6.0,free_percent=50.0,swap_growth_bytes_per_second=0.0,swapout_bytes_per_second=0.0,physical_cores=14)
print(heavy.admission_block_reason(s,now=now,active_count=0,task_already_active=False,slot_limit=2))
```

## Before (origin/main)

```
stale-telemetry
```

## After (branch)

```
None
```

## Retry then degraded path (fake clock, fake runner)

```
no last good: StaleSampleError host telemetry sample was stale on arrival
whole: False 2.86
degraded: True pressure 4 load_per_core 4.0 free 50.0
last good older than 15s: StaleSampleError
```

Pressure 4 is re-read from sysctl in the degraded sample, so critical pressure still blocks. The cached whole sample is used only while it is at most 15 seconds old (`SAMPLE_MAX_AGE_LOADED`); older than that, `sample_host` raises, so frozen memory fields are never older than the loaded age rule.

## Slot limit

heavy.py never raises the slot limit. `_effective_slot_limit` only reads `heavy_slots` from the capacity file and takes the minimum with cores and memory. The file is written by `board_governor.py` (lines 797 to 846), which is out of scope for this ticket and is where a `not sample.degraded` gate on growth belongs. A fake-clock slot-growth case cannot be run from heavy.py, so none is claimed here.
