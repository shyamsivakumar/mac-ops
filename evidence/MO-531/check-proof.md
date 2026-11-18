# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `aba287b8bd6cc54ab14915d9e97a1abdead7a9be`
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
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-2u8nddkh -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-2u8nddkh/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_builder_fallback | `python3 -m unittest tests.test_builder_fallback` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Round 1 lane-driver repair. A probe that ends `completed` with an empty reply
is now recorded as a failed probe: `note_probe_failure` gets the full reply
text and the request id, so the matching `probeRequestId` is cleared and the
next probe waits its deadline instead of the pass skipping it forever. A probe
that has not reported back no longer skips the deadline either: once
`probe_due` says so, the pass starts a new probe.

Covered by three lane-driver tests in `tests/test_builder_fallback.py`:
`test_a_terminal_probe_without_an_answer_is_a_failed_probe`,
`test_a_failed_probe_keeps_the_reset_its_error_names` (a `failed` probe with
`resets in 2 hours` leaves `resetAt` two hours out), and
`test_a_probe_that_never_reported_is_retried_at_its_deadline`. They drive
`probe_blocked_builders` with a patched thread read and queue, so the lane
consumer itself is exercised, not only the store.

Device, handset and live-service cases: not run, waived by Shyam per the brief.
