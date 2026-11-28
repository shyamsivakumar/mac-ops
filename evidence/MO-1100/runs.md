# Proof runs for MO-1339 (Refs #1100)

## Before: origin/mo-model-cost-v2 241975ad (red)

```
git show origin/mo-model-cost-v2:coordinator/model_prices.json
fatal: path 'coordinator/model_prices.json' exists on disk, but not in 'origin/mo-model-cost-v2'
exit=128
```

## After (green)

```
8
exit=0
```

## Report on the real Harbor data, read-only

Models left out of the price file because no official page lists a price: MiniMax-M2, MiniMax-M2.7 (not on platform.minimax.io pricing), grok-4.7-high (the page lists grok-4.7 only), the morph router models and cursor default (no per-token list price). They print n/a.

### ~/Code/strata/jobs (31 trials)
```
cases: 10 shared by every measured model (all cases (Harbor logs carry no held-out flag))
model                        runs solved   pass turns/solved          $/solved  tokens/solved
MiniMax-M2                     10      1    10%        116.0               n/a         169278
MiniMax-M2.7                   10      0     0%            ?               n/a              ?
claude-sonnet-4-20250514       11      1     9%        142.0      est. $1.0072         209901
would pick: router (unsure: no measured model is in the build list, default stays)
```

### ~/Code/mac-ops/evals/harbor/logs
```
cases: 1 shared by every measured model (all cases (Harbor logs carry no held-out flag))
model                        runs solved   pass turns/solved          $/solved  tokens/solved
MiniMax-M3.1-Flash              1      1   100%          2.0      est. $0.0005           3400
would pick: router (unsure: no measured model is in the build list, default stays)
```
