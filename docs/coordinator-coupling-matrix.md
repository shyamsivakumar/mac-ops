# Coordinator Slot Pool and Tick Lifecycle — Axiomatic Design Coupling Matrix

**Boundary:** Coordinator slot pool and tick lifecycle across `coordinator/bin/coordq`, `coordinator/pi/bin/coord-tick`, `coordinator/overnight/lane_driver.py`, `coordinator/overnight/overnight`, and `coordinator/overnight/turn_cap.py` (inspected at `origin/main` commit `1dab2c17`).

This report applies `/Users/shyamsivakumar/Code/llmwiki/runtime/codex/skills/axiomatic-design/SKILL.md` to test whether changes in one Coordinator responsibility stay local or force edits across unrelated parts. It is one structural test on one boundary and does not claim to cover or eliminate all tangled code elsewhere in the repository.

## 1. Functional Requirements (FRs)

| ID | Functional requirement (verb + object) | Primary entry points |
|---|---|---|
| **FR1** | Enqueue work and screen PR gates | `coordq` `cmd_start`, `cmd_gatekeep`, `cmd_drop` |
| **FR2** | Enforce slot cap and dispatch T3 threads | `coordq` `cmd_dispatch`, `drain`, `reconcile_reservations` |
| **FR3** | Refill idle slots from board backlog | `coordq` `safe_refill`, `refill` |
| **FR4** | Reclaim runaway turns and dead runs | `turn_cap.py` `one_pass`, `handle_thread`; `lane_driver.py` `recover_dead_runs` |
| **FR5** | Drive per-repo lane progression and merges | `lane_driver.py` `run_pass`, `act_on_pr`, `start_next`, `unstick`, `merge_passes` |
| **FR6** | Serialize and execute scheduled shift cycles | `overnight` `cmd_shift`, `cmd_act`, `shift_cycle` |
| **FR7** | Run bounded headless coordinator ticks | `coord-tick` `main`, `skip_reason`, `run_tick`, `deliver` |
| **FR8** | Monitor coordinator liveness and raise alarms | `lane_driver.py` `watchdog`; `coordq` `stop_dispatch`, scope refusal carding |
| **FR9** | Report read-only board state and actions | `overnight` `cmd_board` |

## 2. Design Parameters (DPs)

Every DP listed below is an existing mechanism on `origin/main` (`1dab2c17`).

| ID | Design parameter | Source path and lines |
|---|---|---|
| **DP1** | `queue.json` + `queue.lock` (`items`, `reserved`, `reservedThreads`, `actionKeys`, `gatedHeads`, `scopeHeads`, `scopeFetch`, `gatekeepSkips`, `failed`) | `coordinator/bin/coordq:243-266, 619-635, 3073-3088, 3581-3586` |
| **DP2** | `dispatch-receipts.json` (request-ID-to-thread and per-gate metadata map) | `coordinator/bin/coordq:1063-1081, 2291-2359` |
| **DP3** | `config.json`, `refill-state.json`, `dispatch.stopped`, `kill.switch`, `dispatch.last` | `coordinator/bin/coordq:201-241, 1814-1832, 2002-2017, 2065-2074` |
| **DP4** | `.turn_cap.json`, `caps.log`, `ticks.log` | `coordinator/overnight/turn_cap.py:13-15, 42-55, 117-168` |
| **DP5** | `lanes-ledger.json` + `lane_driver` module globals (`LANE_REPOS`, `CFG`, `SNAPSHOT`, `STALL_STATE`, `STALL_EVENTS`, `PASS_PRS`, `print`) | `coordinator/overnight/lane_driver.py:54-91, 3043-3098, 3152-3173` |
| **DP6** | `overnight-shift.lock`, `run/policy.json`, `.overnight/` stall state and cycle receipts | `coordinator/overnight/overnight:594, 1040, 1423-1463, 1465-1492, 1709-1726` |
| **DP7** | `coord-tick.lock` (inherited fd), `coord-tick.mark`, `tick.log`, 600s process-group timer | `coordinator/pi/bin/coord-tick:48-52, 91-104, 234-357` |
| **DP8** | Coordinator journal (`events-YYYY-MM.jsonl`) | `coordinator/bin/coordq:231, 950, 3077`; `coordinator/overnight/lane_driver.py:625-630, 2125-2143`; `coordinator/pi/bin/coord-tick:359-401` |
| **DP9** | Decisions board (`DECISIONS_PATH` alarm/decision cards) | `coordinator/bin/coordq:240, 3102`; `coordinator/overnight/lane_driver.py:62, 2433-2455` |

## 3. Current FR-by-DP Design Matrix

Dependency rule applied uniformly to every row: mark **`X`** when the FR writes, reads, calls into, or mutates the DP (including reads through accessors). Mark **`unknown`** when an unread out-of-boundary module could add a dependency we did not directly inspect.

| FR | DP1 (`queue.json` + `queue.lock`) | DP2 (`dispatch-receipts`) | DP3 (cap / stop / refill state) | DP4 (`.turn_cap` / logs) | DP5 (`lanes-ledger` + globals) | DP6 (`shift.lock` / `policy`) | DP7 (`coord-tick` lock/mark/log) | DP8 (journal) | DP9 (decisions board) |
|---|---|---|---|---|---|---|---|---|---|
| **FR1** Enqueue & gate-screen | **X** (W/R) | **X** (W/R) | **X** (R) | | | | | **X** (W) | **X** (W) |
| **FR2** Enforce cap & dispatch | **X** (W/R) | **X** (W/R) | **X** (W/R) | | | **X** (C) | | **X** (W) | **X** (W) |
| **FR3** Refill idle slots | **X** (W/R) | **X** (R) | **X** (W/R) | | | | | unknown | |
| **FR4** Reclaim turns & dead runs | **X** (R/C) | **X** (R) | | **X** (W/R) | **X** (W/R) | | | **X** (W) | |
| **FR5** Drive lane progression & merges | **X** (R/C) | **X** (R) | | | **X** (W/R) | | | **X** (W/R) | **X** (W) |
| **FR6** Serialize & run shift cycles | | | | **X** (C) | **X** (W/C) | **X** (W/R) | | unknown | |
| **FR7** Run bounded headless ticks | **X** (C via prompt) | | | | | | **X** (W/R) | **X** (R) | unknown |
| **FR8** Monitor liveness & raise alarms | **X** (R) | | **X** (W/R) | | **X** (R) | | **X** (R) | **X** (W) | **X** (W) |
| **FR9** Report read-only board state | **X** (R) | **X** (R) | | | **X** (R/C) | **X** (R) | | | |

Legend: `(W)` writes/mutates, `(R)` reads, `(C)` calls into / spawns. Every cell marked `X` is backed by a line citation below.

## 4. Cell-by-Cell Evidence (`origin/main` `1dab2c17`)

### FR1 — Enqueue work and screen PR gates
- **FR1 × DP1 (W/R):** `coordq:2108-2115` (`cmd_drop` locks `queue.lock` and rewrites `queue.json`); `coordq:3073-3076, 3084-3088` (`scopeHeads`, `scopeFetch` written under `Lock(True)`); `coordq:3581-3586` (`gatekeepSkips` read from `queue.json`).
- **FR1 × DP2 (W/R):** `coordq:2291-2295` (`load_receipts`); `coordq:2349-2358` (gatekeep backfills `ticket:<repo>#<issue>:a1` into `dispatch-receipts.json` under `Lock(True)`).
- **FR1 × DP3 (R):** `coordq:206-208` (`proofs_per_run` reads `config.json`).
- **FR1 × DP8 (W):** `coordq:3077, 3089` (`journal.emit("scope_checked", ...)`, `journal.emit("scope_read_failed", ...)`).
- **FR1 × DP9 (W):** `coordq:3096-3108` (scope refusal raises/clears `Coordinator` ask card on `DECISIONS_PATH` and records `carded` back into `queue.json`).

### FR2 — Enforce slot cap and dispatch T3 threads
- **FR2 × DP1 (W/R):** `coordq:2079-2083` (`cmd_dispatch` takes non-blocking `Lock(False)` on `queue.lock`); `coordq:935-980` (`drain` loads `queue.json`, drops over-attempt/undispatchable items, calls `reconcile_reservations`, compares `n + len(queue["reserved"]) >= cap()`, saves `queue.json`); `coordq:1038-1088` (updates `reservedThreads`, removes launched item, updates `actionKeys`, saves `queue.json`).
- **FR2 × DP2 (W/R):** `coordq:1062-1081` (reads and atomically rewrites `dispatch-receipts.json` with `request_id`, `base:<tid>`, `brief:<tid>`, `voters:<tid>`).
- **FR2 × DP3 (W/R):** `coordq:201-203` (`cap()` reads `config.json`); `coordq:225-240, 249-255` (corrupt `queue.json` writes `dispatch.stopped`); `coordq:2065-2073` (checks `kill.switch` and `dispatch.stopped`, writes `dispatch.last`).
- **FR2 × DP6 (C):** `coordq:1082-1083, 3568-3578` (`watch_gate` spawns `overnight act <ref> --after <thread_id>`, which acquires `overnight-shift.lock` and checks `run/policy.json` at `overnight:1495-1548`).
- **FR2 × DP8 (W):** `coordq:231, 950, 959, 1091` (`journal.emit` / `journal_item` for `queue_fallback`, `dropped`, `refused`, `launched`).
- **FR2 × DP9 (W):** `coordq:232-240` (`stop_dispatch` raises `factory-dispatch-stopped` on `DECISIONS_PATH`).

### FR3 — Refill idle slots from board backlog
- **FR3 × DP1 (W/R):** `coordq:2085` (`cmd_dispatch` runs `safe_refill` after releasing `queue.lock`; `refill` at `coordq:1877` reads queue/slot state and enqueues via `ticket start` / queue lock).
- **FR3 × DP2 (R):** `coordq:1567, 2291-2295` (receipt lookups check active/prior attempts).
- **FR3 × DP3 (W/R):** `coordq:1814-1832, 1995-1997` (`load_refill_state` / `save_refill_state` persist per-ticket refusal backoff in `refill-state.json`).
- **FR3 × DP8 (`unknown`):** `refill` invokes the `ticket` CLI (`coordinator/bin/ticket`, outside this 5-file boundary); whether `ticket start` emits journal rows during refill was not re-read for this matrix (`coordinator/bin/ticket`).

### FR4 — Reclaim runaway turns and dead runs
- **FR4 × DP1 (R/C):** `lane_driver.py:58, 2752` (`recover_dead_runs` inspects `QUEUE` / `coordq` to re-queue dead runs).
- **FR4 × DP2 (R):** `lane_driver.py:57, 447, 682` (reads `dispatch-receipts.json` directly without `queue.lock`).
- **FR4 × DP4 (W/R):** `turn_cap.py:13-15, 42-55, 117-168` (reads/writes `.turn_cap.json` pause clocks, `warned`, `handled`, `parked`; appends `caps.log` and `ticks.log`; calls `t3_thread_interrupt` at line 162 without consulting `queue.json` reservations or `lanes-ledger.json`).
- **FR4 × DP5 (W/R):** `lane_driver.py:2752, 3099` (`recover_dead_runs(ledger)` mutates `ledger`).
- **FR4 × DP8 (W):** `lane_driver.py:625-632` (`journal_verdict` emits `gate_verdict` and settles read gates).

### FR5 — Drive per-repo lane progression and merges
- **FR5 × DP1 (R/C):** `lane_driver.py:58, 2112-2120` (`start_next` runs `ticket start` which enqueues back into `coordq` / `queue.json`).
- **FR5 × DP2 (R):** `lane_driver.py:57, 319-329, 447, 682, 1876, 2161` (multiple uncoordinated direct `json.load(open(RECEIPTS))` reads without taking `queue.lock`).
- **FR5 × DP5 (W/R):** `lane_driver.py:54, 71-91, 3043-3173` (`run_pass` reads/mutates module globals `SNAPSHOT`, `STALL_STATE`, `STALL_EVENTS`, `PASS_PRS`, `PASS_WORKTREES` and persists `lanes-ledger.json`).
- **FR5 × DP8 (W/R):** `lane_driver.py:625-630` (writes `gate_verdict`); `lane_driver.py:2125-2143` (`ticket_started_at` scans `events-*.jsonl`).
- **FR5 × DP9 (W):** `lane_driver.py:62-68` (round-cap / escalation cards write to `DECISIONS_PATH`).

### FR6 — Serialize and execute scheduled shift cycles
- **FR6 × DP4 (C):** `overnight:8371` (`overnight turncap` imports and invokes `turn_cap.one_pass`).
- **FR6 × DP5 (W/C):** `overnight:1518-1548, 1684-1725` (`cmd_act` and `shift_cycle` directly overwrite `lane_driver.CFG`, `lane_driver.LANE_REPOS`, `lane_driver.print`, `lane_driver.SNAPSHOT`, `lane_driver.STALL_STATE`, then call `lane_driver.main()` / `lane_driver.act_on_pr` and read back `lane_driver.STALL_EVENTS` and `lane_driver.STALL_STATE`).
- **FR6 × DP6 (W/R):** `overnight:594, 1040, 1423-1492, 1725-1732` (takes `overnight-shift.lock`, reads `run/policy.json` and `run/STOP`, writes stall state, cycle receipts, and morning report).
- **FR6 × DP8 (`unknown`):** `overnight` health checks and receipt builders may call helper modules outside this 5-file boundary (`coordinator/bin/ticket`, `coordinator/bin/journal.py`) whose full call graph was not read.

### FR7 — Run bounded headless coordinator ticks
- **FR7 × DP1 (C via prompt):** `coord-tick:64-75, 270-293` (headless `pi` executes `loop/tick.md` instructions, calling `overnight board --json --action` and `coordq` subcommands under the 600s `TIMEOUT_S` process-group cap at `coord-tick:52, 297-302`).
- **FR7 × DP7 (W/R):** `coord-tick:48-52, 91-104, 128-166, 234-357, 421-459` (takes inherited-fd `coord-tick.lock`, checks `model_available()` with 60s timeout and runs `tick_selftest()` synchronously inside the lock, kills process group on 600s `TimeoutExpired`, writes `coord-tick.mark` and `tick.log`).
- **FR7 × DP8 (R):** `coord-tick:53-59, 359-419` (`events_quiet` tails the last 1 MiB of `events-YYYY-MM.jsonl` to decide `COORD_TICK_PRECHECK` skips).
- **FR7 × DP9 (`unknown`):** `coord-tick:41, 423-425` calls `tick_health.tick_alarm()` (`coordinator/bin/tick_health.py`, unread), which may read or update alarm state.

### FR8 — Monitor coordinator liveness and raise alarms
- **FR8 × DP1 (R):** `coordq:249-255, 3070-3108` (corrupt `queue.json` and `scopeHeads` refusals drive alarm cards).
- **FR8 × DP3 (W/R):** `coordq:229-240` (`stop_dispatch` creates `dispatch.stopped` and raises card).
- **FR8 × DP5 (R):** `lane_driver.py:3048` (`watchdog()` runs inside `lane_driver.run_pass`, sharing the shift cycle budget and `lanes.log`).
- **FR8 × DP7 (R):** `lane_driver.py:2241-2244, 2409-2428` (`WATCH` inspects `tick.log` age and `dev.coordinator.tick` launchd state alongside `gatekeep.log`, `dispatch.log`, and `lanes.log`).
- **FR8 × DP8 (W):** `coordq:231` (`queue_fallback` journal event).
- **FR8 × DP9 (W):** `coordq:240, 3102`; `lane_driver.py:2433-2455` (`factory-watchdog`, `factory-dispatch-stopped`, and scope cards all write to `DECISIONS_PATH`).

### FR9 — Report read-only board state and actions
- **FR9 × DP1 (R):** `overnight:3027-3036` (reads `queue.json` to see gated heads without mutating it).
- **FR9 × DP2 (R):** `overnight:3030-3033` (reads `dispatch-receipts.json` to map gate threads).
- **FR9 × DP5 (R/C):** `overnight:4263, 4304` (imports `lane_driver` and calls `lane_driver.pr_action`).
- **FR9 × DP6 (R):** `overnight:2536, 5869` (reads `run/policy.json` and board inputs for `cmd_board`).

## 5. Shape Classification

**Shape: Full (coupled).**

Per step 5 of `axiomatic-design/SKILL.md`, this matrix is **full** for two independent reasons (even before resolving the three `unknown` cells, so those `unknown` cells cannot downgrade the classification):

1. **Five shared-writer DPs** (multiple FRs mutate the same DP):
   - **DP1 (`queue.json` + `queue.lock`)** is written by **FR1** (gate screening, scope cache, drop) and **FR2** (slot reservations, launch drain, failure drops) and **FR3** (refill enqueue). A slow or stuck `drain()` holds `queue.lock` against gatekeep/enqueue; corrupt gatekeep metadata trips `dispatch.stopped` and halts all dispatching.
   - **DP2 (`dispatch-receipts.json`)** is written by **FR2** (dispatch launch) and **FR1** (gatekeep builder-thread backfill), while **FR4, FR5, FR9** read it directly without `queue.lock`.
   - **DP5 (`lane_driver` module globals)** is mutated by **FR5** (`run_pass`) and **FR6** (`overnight` monkey-patching `LANE_REPOS`, `CFG`, `print`, `SNAPSHOT`, `STALL_STATE`). Any change to `lane_driver`'s pass state forces coordinated edits in `overnight`.
   - **DP8 (`events-YYYY-MM.jsonl`)** is written by **FR1, FR2, FR5, FR8** and tailed by **FR5** and **FR7** (precheck skip logic depends on event-name conventions emitted by `coordq` and `lane_driver`).
   - **DP9 (`DECISIONS_PATH`)** is written directly by **FR1**, **FR2**, and **FR8**.

2. **Cross-subsystem runtime cycle between dispatch (FR2) and shift/lanes (FR5/FR6):**
   - `coordq` `drain()` (FR2) spawns `overnight act <ref> --after <tid>` (FR6 -> FR5) at `coordq:1082-1083, 3568-3578`.
   - `lane_driver` `start_next` / `unstick` (FR5) runs `ticket start`, which enqueues back into `coordq` (FR1 -> DP1 -> FR2) at `lane_driver.py:2112-2120`, and `lane_driver.watchdog()` (FR8, executed inside `run_pass`) monitors `coordq` and `coord-tick` logs (`lane_driver.py:2241-2244`).
   - `coord-tick` (FR7) executes `tick_selftest()` and `model_available()` synchronously inside `coord-tick.lock` before invoking the 600s-bounded LLM tick, which itself calls `overnight board` (FR9) and `coordq` (FR1/FR2). Any slow external command in `overnight`/`coordq` pushes `coord-tick` past `TIMEOUT_S=600` (`coord-tick:297-302`), triggering SIGTERM/SIGKILL kills.

## 6. Ordered Refactor Path (Toward Lower-Triangular)

Goal: **lower-triangular** (stop once shared-writer DPs are split, module-global patching is removed, and the dispatch ↔ shift cycle is broken). Every step below is behavior-preserving and sized to be cut into independent tickets via `factory-cut`.

### Step 1 — Split shared DP1 (`queue.json`): separate gatekeep metadata from live slot queue
- **Action:** Move `gatedHeads`, `scopeHeads`, `scopeFetch`, and `gatekeepSkips` out of `queue.json` into a gatekeep-owned state file (`gatekeep-state.json` with its own lock), leaving `queue.json` + `queue.lock` owned solely by slot-pool queue operations (`items`, `reserved`, `reservedThreads`, `actionKeys`, `failed`).
- **Why first:** Eliminates the highest-blast-radius shared writer (gatekeep I/O and scope cache writes can no longer stall `drain()` or trip `dispatch.stopped`).
- **Behavior check:** `python3 coordinator/overnight/selftest.py` (`gate-pipeline`, `gate-settle`, `send-integrity`, `lane-one-active`) plus `tests/test_close_check.py`.

### Step 2 — Split shared DP2 (`dispatch-receipts.json`) ownership: single writer + read accessor
- **Action:** Route all writes to `dispatch-receipts.json` through one atomic `coordq` receipt writer (removing gatekeep's inline backfill write or delegating it through a single helper), and replace the five raw `json.load(open(RECEIPTS))` calls in `lane_driver.py` (`325, 447, 682, 1876, 2161`) and `overnight` (`3033`) with one shared read-only helper that tolerates missing/partial files.
- **Why second:** Removes the second shared-writer DP and prevents unguarded reader crashes during concurrent receipt updates.
- **Behavior check:** `python3 coordinator/overnight/selftest.py` (`builder-receipt`, `stall`, `gate-pipeline`) plus `tests/test_reviewer_vendor_split.py`.

### Step 3 — Replace DP5 module-global monkey-patching between `overnight` (FR6) and `lane_driver` (FR5)
- **Action:** Pass an explicit `ShiftContext(repos, cfg, emit, stall_state, merge_allowed)` parameter into `lane_driver.run_pass()` and `lane_driver.act_on_pr()` and return `(result, stall_events, updated_stall_state)` instead of mutating `lane_driver.LANE_REPOS`, `lane_driver.CFG`, `lane_driver.print`, `lane_driver.STALL_STATE`, and `lane_driver.SNAPSHOT` at `overnight:1538-1548, 1694-1725`.
- **Why third:** Gives FR5 sole ownership of `lanes-ledger.json` and pass execution while FR6 owns only `overnight-shift.lock`, `run/policy.json`, and stall persistence.
- **Behavior check:** `python3 coordinator/overnight/selftest.py` (`stall`, `held-merge`, `stop-rules`, `merge-pass`) plus `tests/test_overnight_board.py`.

### Step 4 — Decouple liveness monitoring (FR8) and turn-cap reclamation (FR4) from shift and tick loops
- **Action:**
  1. Extract `lane_driver.watchdog()` (`lane_driver.py:2409`) out of `run_pass()` into a standalone read-only health pass (or `overnight` pre-step that cannot block lane merges), and route all alarm card writes (`DECISIONS_PATH`) through a single alarm owner so FR1/FR2 emit journal events and FR8 publishes cards.
  2. Have `turn_cap.py` emit a structured journal event on interrupt/park (`turn_cap_interrupted`) so `coordq` reservation reconciliation (FR2) and `lane_driver.recover_dead_runs` (FR4/FR5) read one truth instead of discovering interrupted runs independently.
- **Why fourth:** Removes DP9 as a multi-writer surface and aligns `turn_cap.py` with slot reservations.
- **Behavior check:** `python3 coordinator/overnight/selftest.py` (`watchdog`, `turncap`, `dead-run-recovery`, `alarm-mute`).

### Step 5 — Break the FR2 (`coordq`) ↔ FR6 (`overnight`) and FR7 (`coord-tick`) lifecycle cycles
- **Action:**
  1. Replace `coordq`'s direct `subprocess.Popen([GATE_ACT, "act", ...])` (`coordq:3575`) with a journal/event trigger or let `overnight shift` consume completed gate events from `DP8` (one-way data flow: FR2 writes receipts/journal -> FR6/FR5 reads them).
  2. Move `tick_selftest()` (`coord-tick:441`) out of `coord-tick`'s 600s tick lock into its own scheduled job (or run it only outside the LLM tick budget) so a slow selftest or `model_available()` probe never starves a tick into a 600s kill.
- **Why last:** Per Step 6.3 of `axiomatic-design/SKILL.md`, cycles are broken last after shared DPs and state ownership are clean.
- **Behavior check:** `python3 coordinator/overnight/selftest.py` (`gate-pipeline`, `cycle-health`) plus `tests/test_coord_tick.py` (if present; verify with `scripts/mac_ops_fast_check.py`).

## 7. Target Matrix After Steps 1–5 (Lower-Triangular, Accepted Journal Sink)

Splitting existing multi-writer DPs strictly along their current file/key uses in source:
- `DP1a`: `queue.json` live queue keys (`items`, `reserved`, `reservedThreads`, `actionKeys`, `failed`) + `queue.lock` (single writer: **FR2**).
- `DP1b`: `queue.json` gatekeep keys (`gatedHeads`, `scopeHeads`, `scopeFetch`, `gatekeepSkips`) extracted to their own file + lock (single writer: **FR1**).
- `DP2`: `dispatch-receipts.json` (single writer: **FR2**, read-only helper for all other FRs).
- `DP3a`: `config.json`, `dispatch.stopped`, `kill.switch`, `dispatch.last` (single writer: **FR2**).
- `DP3b`: `refill-state.json` (single writer: **FR3**).
- `DP5`: `lanes-ledger.json` with explicit `ShiftContext` argument (single writer: **FR5**).
- `DP8`: append-only `events-YYYY-MM.jsonl` journal — explicitly retained as an **accepted multi-writer append-only event log** (per step 6.4 of `axiomatic-design/SKILL.md`: stop where the remaining coupling is a low-cost trade-off you accept).

| FR (ordered) | DP1a (slot queue) | DP2 (receipts) | DP3a (cap/stop) | DP3b (`refill-state`) | DP4 (`.turn_cap`) | DP1b (gatekeep keys) | DP5 (`lanes-ledger`) | DP6 (`shift.lock`/`policy`) | DP7 (`coord-tick`) | DP9 (decisions board) | DP8 (append-only journal*) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **FR2** Enforce cap & dispatch | **X** (W) | **X** (W) | **X** (W/R) | | | | | | | | **X** (W*) |
| **FR3** Refill idle slots | **X** (R/C) | **X** (R) | **X** (R) | **X** (W/R) | | | | | | | |
| **FR4** Reclaim turns & dead runs | **X** (R) | **X** (R) | | | **X** (W) | | | | | | **X** (W*) |
| **FR1** Gate-screen & enqueue | **X** (C) | **X** (R) | **X** (R) | | | **X** (W) | | | | | **X** (W*) |
| **FR5** Drive lane progression | **X** (C) | **X** (R) | | | | **X** (R) | **X** (W) | | | | **X** (W*/R) |
| **FR6** Serialize shift cycles | | | | | **X** (C) | | **X** (C) | **X** (W) | | | **X** (R) |
| **FR7** Run bounded ticks | **X** (C) | | | | | | | | **X** (W) | | **X** (R) |
| **FR8** Monitor liveness & alarms | **X** (R) | | **X** (R) | | | **X** (R) | | | **X** (R) | **X** (W) | **X** (R) |
| **FR9** Report read-only board | **X** (R) | **X** (R) | | | | **X** (R) | **X** (R) | **X** (R) | | | |

Excluding the accepted append-only journal sink (`DP8*`), every mutable state DP has a single writer FR, every off-diagonal mark sits strictly to the left of (depends only on) earlier rows, and **FR9** (read-only) sits last with zero writes — yielding a **lower-triangular (decoupled)** shape.

## 8. Omitted and Out-of-Scope Couplings

The following files were outside the 5-file boundary for this matrix and were not read in full; any future refactor ticket touching them should inspect them directly:

- `coordinator/bin/ticket` — called by `coordq` (`refill`) and `lane_driver.py` (`start_next`) to validate tickets, render briefs, and enqueue `coordq` items (source of the `FR3 × DP8` `unknown` cell).
- `coordinator/bin/tick_health.py` and `coordinator/bin/hourly_selftest.py` — imported by `coord-tick:41-42` (`tick_alarm`, `tick_selftest`; source of the `FR7 × DP9` `unknown` cell).
- `coordinator/bin/alarms.py` — shared board lock and compare-and-swap writer behind `DECISIONS_PATH` (`DP9`).
- `coordinator/bin/gh_gateway.py` — shared GitHub API budget floor (`API_FLOOR`, `lane_driver.py:83`) and ETag cache shared across `coordq`, `lane_driver.py`, and `overnight`.
- `coordinator/bin/journal.py` — append-only writer behind `events-YYYY-MM.jsonl` (`DP8`).
- `coordinator/bin/models.py` and `coordinator/models.json` — model catalog and `providers-blocked.json` shared by `coordq`, `ticket`, and `lane_driver.py`.
- `coordinator/launchd/*.plist` — launchd firing cadences (`dev.coordinator.tick`, `dev.coordinator.dispatch`, `dev.coordinator.gatekeep`, `dev.coordinator.lanes`) that determine real-world lock contention windows.
- `coordinator/pi/extensions/coordinator.ts` and `~/Code/coordinator/loop/tick.md` — interactive coordinator wake/mirror extension and the live tick prompt executed inside `coord-tick`.
