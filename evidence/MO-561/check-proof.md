# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `ee1d6ed196450e020a79f0254b063a15e985545e`
Working tree clean when the checks ran: yes
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: board_resources.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' board_resources.py` | passed |  |
| python syntax: scripts/mac_ops_fast_check.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/mac_ops_fast_check.py` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/pi/bin/coord-tick` | passed | 86 findings, all in the baseline |
| mypy --strict: board_resources.py | `uvx mypy@1.18.2 --strict --follow-imports=silent --python-version 3.9 --cache-dir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/mac-ops-mypy-cache board_resources.py` | passed | 1 module(s), no findings |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-dry04ngp -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-dry04ngp/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_heavy_host_headroom | `python3 -m unittest tests.test_heavy_host_headroom` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
