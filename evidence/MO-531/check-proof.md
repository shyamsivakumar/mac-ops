# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `1c10f21a477711ee9f388ec0c34db2334e5630fc`
Working tree clean when the checks ran: yes

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: coordinator/bin/builders.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/builders.py` | passed |  |
| python syntax: coordinator/bin/provider_health.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/provider_health.py` | passed |  |
| python syntax: coordinator/overnight/lane_driver.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/lane_driver.py` | passed |  |
| python syntax: coordinator/overnight/selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/selftest.py` | passed |  |
| python syntax: tests/test_builder_fallback.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_builder_fallback.py` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-6302werc -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-6302werc/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_builder_fallback | `python3 -m unittest tests.test_builder_fallback` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Device, handset and live-service testing: waived by Shyam (2026-11-14).

Changed test lines (MO-1082 allows existing tests to change as far as this needs):
`tests/test_builder_fallback.py:304` asserts one probe dispatch
(`self.assertEqual(len(calls), 1)`) instead of `module.MAX_ATTEMPTS`, and
`tests/test_builder_fallback.py:310` adds that the probe item leaves the queue.
A probe that fails is dispatched once and retires; the provider health store's
deadline decides the next probe, which is the one-probe-an-hour cadence the
issue asks for. The rest of the test is unchanged: the dispatch still names GLM
with the same request id, and the item still lands in the failed list.
