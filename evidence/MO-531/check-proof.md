# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `5ecc9ad2c5801183f1aef09bfe634978acda90df`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: coordinator/bin/builders.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/builders.py` | passed |  |
| python syntax: coordinator/bin/provider_health.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/provider_health.py` | passed |  |
| python syntax: coordinator/overnight/lane_driver.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/lane_driver.py` | passed |  |
| python syntax: coordinator/overnight/selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/selftest.py` | passed |  |
| python syntax: tests/test_builder_fallback.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_builder_fallback.py` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-vkllavuj -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-vkllavuj/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_builder_fallback | `python3 -m unittest tests.test_builder_fallback` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Recovery replay: PASS. A scratch COORDQ_DIR replay called block, note_probe, note_probe_failure, probe_due before and at the deadline, note_probe for a second request, a stale first-request failure, and unblock for the second request. All assertions passed. Command: `timeout 300 python3` with an inline scratch-store assertion script.

In-session review: PASS. Reviewed the two-line fix against the lane consumer: terminal failure clears the ID, the next pass checks the retained deadline, and mismatched failures cannot change a newer request. No added comments to remove; no unrelated cleanup needed. Coordinator Astra gate remains pending.

Device, handset and live-service cases: not run, waived by Shyam per the brief (2026-11-14).
