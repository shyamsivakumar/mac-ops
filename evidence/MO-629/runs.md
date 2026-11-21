# MO-629 runs

## Failing command, found on the M1 (2026-11-20 17:00-17:29)

Every sampling command in `sample_host` run under `python3 -I` with PATH
`/usr/bin:/bin:/usr/sbin:/sbin` succeeds on the M1 (about 20 loops of all
eight, 150 `sample_host` calls at load 17 to 28, 105 sample/ps/boot calls with
80 spinner processes at load 99). The M1 controller journal
(`~/.local/state/mac-ops/controller.jsonl`) held 83 `native telemetry command
failed` records today (`reap_error` and `heavy_error`), including at 17:02 and
17:18 while the spinners ran. The slowest command under load is not the sample
set (steady 1.02-1.08 s, iostat floor) but `/bin/ps -axo ...lstart=`, the
process census behind reap and admission: 0.04 s idle, 2.3 s at load 99, close
to the 2.5 s NATIVE_TIMEOUT. A timeout there raised TelemetryError, the caller
lost its reading, and the load-average stand-in refused the job.

## Before and after, ps starved past 2.5 s (first ps call sleeps 2.7 s then times out), on the M1

    main:   process_table FAIL: native telemetry command failed
    branch: process_table ok rows 832

## Real run on the M1 with the branch heavy.py, load 2.55 per core, CPU low

    cpu 9.0 load_per_core 2.55 critical_pressure False
    heavy: queued role=ordinary position=1 ... job /usr/bin/true ran

## Test case

    python3 -m unittest tests.test_heavy_host_headroom.HostHeadroomTests.test_a_slow_native_command_gets_one_longer_retry
    origin/main: FAILED (errors=1)    branch: OK
