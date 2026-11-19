# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `27427fa5af4a70992d008b26f624b78839193e1c`
Working tree clean when the checks ran: yes

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: board_governor.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' board_governor.py` | passed |  |
| python syntax: evidence/MO-495/dead_job_and_simulator_proof.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evidence/MO-495/dead_job_and_simulator_proof.py` | passed |  |
| python syntax: evidence/MO-495/simulator_cleanup_proof.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evidence/MO-495/simulator_cleanup_proof.py` | passed |  |
| python syntax: heavy.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' heavy.py` | passed |  |
| python syntax: tests/test_heavy_dead_job_simulators.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_heavy_dead_job_simulators.py` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-ngj3c7km -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-ngj3c7km/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_agent_heavy_wait_pause | `python3 -m unittest tests.test_agent_heavy_wait_pause` | passed |  |
| tests: tests.test_heavy_dead_job_simulators | `python3 -m unittest tests.test_heavy_dead_job_simulators` | passed |  |
| tests: tests.test_heavy_host_headroom | `python3 -m unittest tests.test_heavy_host_headroom` | passed |  |
| tests: tests.test_heavy_review_slots | `python3 -m unittest tests.test_heavy_review_slots` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.
