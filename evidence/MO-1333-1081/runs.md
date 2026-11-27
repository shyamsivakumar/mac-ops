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

## Real journal, read-only

```
cases: every resolved card (journal cards closed or abandoned, type any; turns are lane starts)
model                        runs solved   pass turns/solved     $/solved  tokens/solved
router                        254    252    99%          1.3          n/a              ?
would pick: router (measured: router has the lowest turns_per_solved (1.254) among 1 within noise of the best pass rate 0.99)
cases: every resolved card (journal cards closed or abandoned, type risky; turns are lane starts)
model                        runs solved   pass turns/solved     $/solved  tokens/solved
router                        116    115    99%          1.5          n/a              ?
would pick: router (measured: router has the lowest turns_per_solved (1.478) among 1 within noise of the best pass rate 0.99)
```
