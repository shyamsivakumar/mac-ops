# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `2dfd34c1bedbe37c84e72861204498e29d52490d`
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
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-rpt_7vxw -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-rpt_7vxw/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_builder_fallback | `python3 -m unittest tests.test_builder_fallback` | failed | Command '['/Applications/Xcode.app/Contents/Developer/usr/bin/python3', '-m', 'unittest', 'tests.test_builder_fallback']' returned non-zero exit status 1. |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Device, handset and live-service testing: waived by Shyam (2026-11-14).

The configured check failed in `test_a_failed_probe_dispatch_never_moves_to_another_builder`. The current probe handling stops after one dispatch attempt, while the unchanged test expects three. Tests and checks were left unchanged.
