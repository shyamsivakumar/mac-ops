# Proof runs for MO-1333 (Refs #1081)

## origin/main 906862ac (red)

```sh
python3 -c "import sys;sys.path[:0]=['coordinator/bin'];import models;a,b=[e['id'] for e in models.entries('build')[:2]];p,r=models.measured_pick('build',{a:{'pass_rate':0.9,'turns_per_solved':3.0},b:{'pass_rate':0.9,'turns_per_solved':1.5}});print(r);sys.exit(p['id']!=b)"
```

```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AttributeError: module 'models' has no attribute 'measured_pick'
exit=1
```

## head (green)

```
measured: cursor has the lowest turns_per_solved (1.5) among 2 within noise of the best pass rate 0.90
exit=0
```

## Real Harbor runs, read-only (~/Code/strata/jobs, 31 trials, 3 models)

```
cases: 10 shared by every measured model (all cases (Harbor logs carry no held-out flag))
model                        runs solved   pass turns/solved     $/solved  tokens/solved
MiniMax-M2                     10      1    10%        116.0          n/a         169278
MiniMax-M2.7                   10      0     0%            ?          n/a              ?
claude-sonnet-4-20250514       11      1     9%        142.0          n/a         209901
would pick: router (unsure: no measured model is in the build list, default stays)
```

## mac-ops Harbor example run (evals/harbor/logs)

```
cases: 1 shared by every measured model (all cases (Harbor logs carry no held-out flag))
model                        runs solved   pass turns/solved     $/solved  tokens/solved
MiniMax-M3.1-Flash              1      1   100%          2.0          n/a           3400
would pick: router (unsure: no measured model is in the build list, default stays)
```

Every Harbor result.json on this Mac (541 files) has `cost_usd` null, so $/solved is n/a; tokens and turns are recorded.
