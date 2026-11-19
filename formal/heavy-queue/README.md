# Heavy queue model

`HeavyQueue.tla` models the admission chart in `docs/state-charts/heavy.md` and the slot changes in `docs/state-charts/governor.md`, against `heavy.py` at commit `504c676`. It models one job of each role and checks deploy before review before ordinary when none have aged.

The model checks that admission counts both reservations and running jobs, and happens only below the current slot limit. Capacity may fall below the active count without killing jobs. It checks priority for unaged jobs, and a stale lock-file marker does not disable admission. A stale marker is not a live held lock: `flock` releases the lock when its owner exits. The model assumes a safe registry and does not cover a live holder, unsafe files, process identity failures, legacy draining, task locks, host telemetry, pauses, launch failure, queue aging or multiple deploy jobs.

The liveness check assumes the finite initial queue receives no new jobs, slots eventually remain positive, the job does not time out, and enabled admissions, starts and completions are weakly fair. It cannot establish starvation freedom under an endless stream of higher-priority jobs or intermittent capacity. Capacity is bounded to zero through two slots. Queued jobs can time out; running jobs can finish or be killed, which also covers termination for the wall-clock and no-progress limits (see Runtime limit in the state chart). The model abstracts the governor's reasons for capacity changes rather than checking its policy.

Run `heavy python3 scripts/mac_ops_fast_check.py`. The check requires Java 17 and the existing `~/Code/llmwiki/runtime/tla/tla2tools.jar`; `MAC_OPS_JAVA_BIN` and `MAC_OPS_TLA_JAR` override those paths. TLC scratch files use `TMPDIR` when set, otherwise the system temporary directory. Linux CI takes TLC 1.8.0 (revision 090e85c) from the checksum-pinned TLA+ VS Code extension 2026.10.301552 on Open VSX, because each rolling build replaces the GitHub v1.8.0 release asset.

