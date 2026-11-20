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

## Slot limit growth (board_governor.py)

`_adaptive_capacity_decision` holds the current target when `sample.degraded` is true and records `reason="degraded_telemetry"`. It still shrinks on pressure and capacity through the earlier branches. The case calls the function directly with fake inputs, current slots 2, same values in both samples:

```
import dataclasses, heavy, board_governor as g
now=1000.0
base=heavy.Sample(pressure_level=1,cpu_busy_pct=10.0,memory_used_pct=40.0,headroom_bytes=30*2**30,physical_bytes=36*2**30,load_per_core=0.5,captured_monotonic=now,free_percent=60.0,swap_growth_bytes_per_second=0.0,swapout_bytes_per_second=0.0,physical_cores=14)
census={"active":1,"registry_active":1,"legacy_active":0,"job_rss_bytes":[2**30]}
comp={"compressor_bytes":1000,"sampled_monotonic":now}
previous={"boot_id":"b","machine":[14,36*2**30],"compressor_bytes":1000,"compressor_sampled_monotonic":now-2.0,"last_sample_monotonic":now-2.0,"healthy_since_monotonic":now-10000.0,"heavy_memory_cost_bytes":2**30*3}
for label,s in (("fresh",base),("degraded",dataclasses.replace(base,degraded=True))):
    _,d=g._adaptive_capacity_decision(heavy,s,census,comp,previous,2,"b",now)
    print(label,"current 2 -> target",d["target"],d["reason"])
```

Output:

```
fresh current 2 -> target 3 healthy_growth
degraded current 2 -> target 2 degraded_telemetry
```
