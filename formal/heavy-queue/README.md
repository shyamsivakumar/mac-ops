# Heavy queue model

`HeavyQueue.tla` models the admission chart in `docs/state-charts/heavy.md` and the slot changes in `docs/state-charts/governor.md`, against `heavy.py` at commit `17015cf414676c4cc11725d2647b3acf8c1381fc`. It models one reviewer and two ordinary jobs, including an ordinary job named `deploy` to make the future priority property observable. That name is not a current heavy role. The two ordinary jobs have fixed FIFO order.

The model checks that admission counts both reservations and running jobs, and happens only below the current slot limit. Capacity may fall below the active count without killing jobs. It checks reviewer priority, and a stale lock-file marker does not disable admission. A stale marker is not a live held lock: `flock` releases the lock when its owner exits. The model assumes a safe registry and does not cover a live holder, unsafe files, process identity failures, legacy draining, task locks, host telemetry, pauses or launch failure.

The liveness check assumes the finite initial queue receives no new jobs, slots eventually remain positive, the job does not time out, and enabled admissions, starts and completions are weakly fair. It cannot establish starvation freedom under an endless stream of reviewers or intermittent capacity. Capacity is bounded to zero through two slots. Queued jobs can time out; running jobs can finish or be explicitly killed. The model abstracts the governor's reasons for capacity changes rather than checking its policy.

Run `heavy python3 scripts/mac_ops_fast_check.py`. The check requires Java 17 and the existing `~/Code/llmwiki/runtime/tla/tla2tools.jar`; `MAC_OPS_JAVA_BIN` and `MAC_OPS_TLA_JAR` override those paths. TLC scratch files stay under `TMPDIR`.

`DeployPriority.cfg` is separate and is not part of the fast check. It currently exposes the missing deploy priority: heavy accepts only ordinary and review roles. It omits today's reviewer-priority invariant because that invariant would conflict with deploy priority. When MO-39 merges, update the model and add a reviewer-before-ordinary invariant, then enable the future policy in the fast check.
