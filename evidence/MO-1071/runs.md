# MO-1071 runs

Proof command: python3 coordinator/evals/hillclimb/climb.py --help

Red on origin/main:

```
origin/main has no coordinator/evals/hillclimb/climb.py (python3: can't open file 'coordinator/evals/hillclimb/climb.py': [Errno 2] No such file or directory)
```

Green on the head:

```
usage: climb.py [-h] --arm ARM [--arm-cmd ARM_CMD] --baseline BASELINE
                [--baseline-cmd BASELINE_CMD] [--repeats REPEATS]

Keep or revert one hill-climb change (MO-1199 c). Scores the candidate arm
exit=0
```

## Fixture run: scratch copy of ~/Code/coordinator/evals/hillclimb (147 labels), SCORE_PY a copy of evals/ladder/score.py, the repo lock matched

$ climb.py --data COPY --arm recorded --baseline random --repeats 5
KEEP lift 38.95 se 10.54 n 19
exit=0
$ climb.py --data COPY --arm random --baseline recorded --repeats 5
REVERT lift -38.95 se 10.54 n 19
exit=1
$ climb.py --data COPY --arm first-option --baseline first-option --repeats 3
REVERT lift 0.00 se 0.00 n 19
exit=1
$ climb.py --data COPY --arm mymodel --baseline random
climb: score.py exited 2: usage: score.py [-h] {locked,final,lock} ...
score.py: error: --arm mymodel is not built in; pass --arm-cmd
exit=1
climb_log.jsonl rows in the copy: 3
```

Selftest (heavy overnight selftest): 37 PASS, 0 FAIL.

Re-run on the head rebased onto mo1067-data-dir-v2 (84a00dfd) after the history scrub: help exit 0 and the four fixture runs print the same lines and exit codes as above; climb_log.jsonl rows in the copy: 3.
