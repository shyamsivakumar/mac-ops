## MO-211 · Overnight T4: the policy snapshot the shift reads on every cycle

Refs #179

### What this changes

Overnight runner spec part T4, as spec revision 3 changed it (Shyam, 2026-11-13: "don't use the tick then. just run the shift 24x7"). Revision 3 removes the night window, the deadline and the arm: the shift runs 24x7 and is never unarmed. What is left of T4 is the policy snapshot the shift reads on every cycle.

- `coordinator/overnight/overnight`: a new `policy` subcommand in the same module as `intake`, `filter`, `order`, `report`, `shift` and `attend`.
  - It writes `run/policy.json` in the folder the shift keeps its records in (the runtime folder, or `--root` for a rehearsal).
  - The snapshot holds the allow list (the board config's repositories), the queue's slot cap (read only, from the coordq config, never raised), the stall cap, the retry cap and the verify level.
  - It has no item cap and no allowance stop: the whole backlog is in scope and model use is never a stop condition.
  - It writes no `run/armed` and no `run/deadline`, and it never writes the queue's config. Writing it again replaces it with the same contract, so it can run on every boot.
- The shift reads the snapshot on every cycle.
  - The cycle works under the snapshot's allow list, so the board is read under the contract and not under a second list of its own.
  - A cycle that would work the board and finds no snapshot refuses and says so. A dry run reads the board without one and says that it did.
  - `run/STOP` stops the next working cycle. The morning report still runs: it is the record of the night, and it says that the night ended with STOP.
  - The shift never reads `run/armed` and never reads `run/deadline`.
- The attended first night (T13, #192) writes its snapshot through the same writer, so there is one shape of snapshot in the module. It keeps its own `run/armed` and `run/deadline` because it is a rehearsal with a human in it; the shift itself has neither.
- `coordinator/overnight/README.md`: the contract names the new command, the fields of the snapshot, what the shift reads on every cycle, and that there is no item cap and no allowance stop.
- `evidence/MO-211/`: the proof runs, the decisions and the reviewer round.

Not touched: the merge, push and slot-cap rules, the Ascend rules, the coordq queue, the launchd job and its hours (the schedule is MO-240), the pi tick, and every existing test or check. No existing test or check was weakened, and no new test file was added: the ticket says to prove by running the real command.

### Proof

- `python3 coordinator/overnight/overnight policy` was run twice against the live runtime folder and wrote the same contract both times (`evidence/MO-211/policy-run-1.log`, `evidence/MO-211/policy-run-2.log`). The snapshot is `evidence/MO-211/policy.json`:

```json
{
  "allow": [
    "digitized/Concerning",
    "shyamsivakumar/CineJar",
    "shyamsivakumar/cairn",
    "shyamsivakumar/catalouge",
    "shyamsivakumar/fantasy-football-toolkit",
    "shyamsivakumar/mac-ops",
    "shyamsivakumar/openscan",
    "shyamsivakumar/qabot",
    "shyamsivakumar/recoup",
    "shyamsivakumar/sams-llm-wiki",
    "shyamsivakumar/scrapers",
    "shyamsivakumar/scripture-scroll",
    "shyamsivakumar/strata",
    "shyamsivakumar/strategy-replay-workbench",
    "shyamsivakumar/tunerise"
  ],
  "slot_cap": 6,
  "stall_cap": 3,
  "retry_cap": 2,
  "verify_level": "balanced",
  "written_at": "2026-11-13 17:14 PST"
}
```

- A shift cycle against the same folder read the snapshot and worked under its allow list (`evidence/MO-211/shift-cycle.log`): "shift cycle under /Users/shyamsivakumar/Code/coordinator/.overnight/run/policy.json", then the intake under the snapshot's 15 repositories.
- The refusals and the STOP are in `evidence/MO-211/policy-proof.log`: a cycle with no snapshot exits 1 with the path it looked for, a dry cycle without one says so and reads the board, `run/STOP` stops the next working cycle, and the report still writes its file with STOP in place.
- No secret was read or written: the snapshot holds repository names, the queue's cap and three numbers.

### Checks

```
$ python3 scripts/mac_ops_fast_check.py
fast-check: passed; selected checks are not the full suite

$ ~/.local/bin/heavy python3 -m unittest discover -s tests -t .
Ran 190 tests in 3.213s

OK
```

Builder check: PASS 829b36fd80fd4863ede2f534b0da4f5ba3ef4689
