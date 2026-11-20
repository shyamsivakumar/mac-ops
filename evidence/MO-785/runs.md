# MO-785 runs

## Before (origin/main)

```
fatal: path 'scripts/remote_fast_check.sh' exists on disk, but not in 'origin/main'
no Host line in proof writer
```

## After: `scripts/remote_fast_check.sh --remote mo785-remote-fast-check e14c81af0917c1406b28224e07c0c60829dbe6ab evidence/MO-785/check-proof.md`

Remote commands run through a login shell (`ssh m1 zsh -l -s`), so python3 is /opt/homebrew/bin/python3 3.14.7, not the non-login /usr/bin/python3 3.9.6.

```
Shyams-MacBook-Pro.local
   a16bdbe2..73e745cd  main                    -> origin/main
heavy: queued role=ordinary position=1
heavy: waiting (first swap sample; normal wait, a few seconds)
/private/tmp/fastcheck-X0olUH/tests/test_close_check.py:590: SyntaxWarning: "\|" is an invalid escape sequence. Such sequences will not work in the future. Did you mean "\\|"? A raw string is also an 
  `make build \| tee build.log` is one command cell, so the row
fast-check: base=94db6bd757c2472f005155681434c8f93a5f1f39
fast-check: changed=['scripts/mac_ops_fast_check.py', 'scripts/remote_fast_check.sh']
fast-check: Python syntax=['scripts/mac_ops_fast_check.py']; shell syntax=['scripts/remote_fast_check.sh']; tests=[]
PASS lane-one-active
alarms: the mute state could not be read: the mute state is not readable: Expecting property name enclosed in double quotes: line 1 column 3 (char 2)
alarms: the mute state could not be read or locked: the mute state is not readable: Expecting property name enclosed in double quotes: line 1 column 3 (char 2)
PASS send-integrity
PASS root-workspace
PASS worktree-base-ref
PASS consolidation-guard
PASS script-results
PASS start-routing
PASS dead-run-recovery
PASS gate-pipeline
PASS merged-restart
PASS merge-pass
PASS gate-round-cap
PASS decisions-board-guard
PASS no-parking
PASS turncap
PASS watchdog
PASS zero-merge
PASS board-integrity
PASS api-budget
PASS ff-drift
PASS cycle-health
PASS stall
PASS alarm-mute
PASS router-build
PASS router-blocked
PASS key-mint
PASS credit-block
PASS provider-until
PASS close-evidence
PASS build-here
TLC2 Version 2026.10.20.183001 (rev: d2e1472)
Warning: Please run the Java VM, which executes TLC with a throughput optimized garbage collector, by passing the "-XX:+UseParallelGC" property.
(Use the -nowarning option to disable this warning.)
Running breadth-first search Model-Checking with fp 108 and seed 8500758074522236835 with 1 worker on 10 cores with 128MB heap and 64MB offheap memory [pid: 58600] (Mac OS X 27.0.1 aarch64, Homebrew 1
Parsing file /private/var/folders/4d/l9996sv53p7dl4l5x5y0skhc0000gn/T/heavy-queue-tlc-2k8ztsjt/HeavyQueue.tla
Parsing file /private/var/folders/4d/l9996sv53p7dl4l5x5y0skhc0000gn/T/heavy-queue-tlc-2k8ztsjt/tlc-11288396459723032308/Naturals.tla (jar:file:/Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.
Parsing file /private/var/folders/4d/l9996sv53p7dl4l5x5y0skhc0000gn/T/heavy-queue-tlc-2k8ztsjt/tlc-11288396459723032308/FiniteSets.tla (jar:file:/Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tool
Parsing file /private/var/folders/4d/l9996sv53p7dl4l5x5y0skhc0000gn/T/heavy-queue-tlc-2k8ztsjt/tlc-11288396459723032308/TLC.tla (jar:file:/Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar!/
Parsing file /private/var/folders/4d/l9996sv53p7dl4l5x5y0skhc0000gn/T/heavy-queue-tlc-2k8ztsjt/tlc-11288396459723032308/Sequences.tla (jar:file:/Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools
Semantic processing of module Naturals
Semantic processing of module Sequences
Semantic processing of module FiniteSets
Semantic processing of module TLC
Semantic processing of module HeavyQueue
Linting of module HeavyQueue
Starting... (2026-11-20 13:51:00)
Implied-temporal checking--satisfiability problem has 3 branches.
Computing initial states...
Finished computing initial states: 2 distinct states generated at 2026-11-20 13:51:00.
Progress(11) at 2026-11-20 13:51:00: 3,380 states generated, 888 distinct states found, 0 states left on queue.
Checking 3 branches of temporal properties for the complete state space with 2664 total distinct states at (2026-11-20 13:51:00)
Finished checking temporal properties in 00s at 2026-11-20 13:51:00
Model checking completed. No error has been found.
  Estimates of the probability that TLC did not check all reachable states
  because two distinct states had the same fingerprint:
  calculated (optimistic):  val = 1.2E-13
3380 states generated, 888 distinct states found, 0 states left on queue.
The depth of the complete state graph search is 11.
The average outdegree of the complete state graph is 1 (minimum is 0, the maximum 6 and the 95th percentile is 4).
Finished in 00s at (2026-11-20 13:51:00)
fast-check: passed; selected checks are not the full suite
remote_fast_check: removed /tmp/fastcheck-X0olUH on m1
scripts/remote_fast_check.sh --remote mo785-remote-fast-check    0.04s user 0.04s system 0% cpu 1:12.74 total
```

Local host: Shyams-M4.local. Proof host: Shyams-MacBook-Pro.local (M1). After the run `git worktree list` on the M1 shows only ~/Code/mac-ops on main, and no /tmp/fastcheck-* directory is left.
