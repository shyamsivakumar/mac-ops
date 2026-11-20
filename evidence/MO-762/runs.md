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

## Retry then degraded path (slow fake clock, fake runner)

```
no last good: StaleSampleError host telemetry sample was stale on arrival
whole: False 2.86
degraded: True pressure 4 load_per_core 4.0 free 50.0
```

Pressure level 4 is re-read from sysctl in the degraded sample, so critical pressure still blocks.
