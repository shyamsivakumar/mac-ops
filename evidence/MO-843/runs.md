# MO-843 runs

Fixture: evidence/MO-843/fixture (60 labels, 20 held-out, 2 unscored). Temp lock and final log; no live data. The scorer runs once per call (no determinism re-run, no exit 4); repeats measure noise.

## Proof command

Before (origin/main e42a1d8c): `KeyError: 'locked_score'`

After (branch): `True`

## Runs (script: scratchpad proof843.sh, output verbatim)

```
== same arm twice
33.33
33.33
== first-option vs random: per-repeat first-option score (chance is about 100/avg options)
6.67
first-option [33.3, 44.4, 33.3, 50.0, 38.9] random [27.8, 27.8, 44.4, 27.8, 38.9] unscored 2 beats_noise False
== recorded vs random
33.33
{"repeat_scores": [{"arm": 66.66666666666667, "baseline": 27.77777777777778, "lift": 38.88888888888889}, {"arm": 66.66666666666667, "baseline": 27.77777777777778, "lift": 38.88888888888889}, {"arm": 66.66666666666667, "baseline": 44.44444444444444, "lift": 22.22222222222223}, {"arm": 66.66666666666667, "baseline": 27.77777777777778, "lift": 38.88888888888889}, {"arm": 66.66666666666667, "baseline": 38.888888888888886, "lift": 27.777777777777786}], "lift": 33.33333333333333, "paired_se": 12.099802839640404, "beats_noise": true, "min_detectable_lift": 24.199605679280808, "unscored": 2, "baseline": "random", "arm": "recorded", "n": 18}
== missing --baseline
score.py locked: error: the following arguments are required: --baseline
exit=2
== change smaller than noise
-6.67
lift -6.666666666666667 se 4.85071250072666 beats_noise False
== --arm-cmd (picks last shuffled option)
0.00
== arm not built in, no --arm-cmd
score.py: error: --arm mymodel is not built in; pass --arm-cmd
== baseline not built in, no --baseline-cmd
score.py: error: --baseline old is not built in; pass --baseline-cmd
== edited lock input
score: lock at TMP/lock does not match the labels, split or scorer
exit=3
== final twice
40.00
exit=0
score: the final split was checked at 2026-11-22T12:36:23.308409+00:00; wait 7 days
exit=5
{"ts": "2026-11-22T12:36:23.308409+00:00", "arm": "recorded", "baseline": "random", "lift": 40.0}
```

First-option scores 33 to 50% per repeat under the shuffle (chance is about 33% with 2 to 4 options).
