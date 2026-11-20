# MO-504 runs

## Renamed session (constructed): named #10, then #20, then o/r#30; turns cost 1, 2, 4; an 8 turn on 2026-11-19 falls outside the day
```
# Agent cost per pull request, 2026-11-17

$7.00 on 3 pull requests.
$0.00 on turns whose session name has no pull request number.

| Pull request | Cost | Turns |
| --- | ---: | ---: |
| o/r#30 | $4.00 | 1 |
| unknown-repo#20 | $2.00 | 1 |
| unknown-repo#10 | $1.00 | 1 |
```

## --repo o/r on the same file
```
# Agent cost per pull request in o/r, 2026-11-17

$4.00 on 1 pull requests.

| Pull request | Cost | Turns |
| --- | ---: | ---: |
| o/r#30 | $4.00 | 1 |
```

## Real traces, 2026-11-17, top 10
```
# Agent cost per pull request, 2026-11-17

$176.44 on 102 pull requests.
$138.22 on turns whose session name has no pull request number.

| Pull request | Cost | Turns |
| --- | ---: | ---: |
| shyamsivakumar/mac-ops#494 | $22.09 | 132 |
| shyamsivakumar/mac-ops#498 | $18.42 | 116 |
| shyamsivakumar/mac-ops#497 | $17.43 | 294 |
| shyamsivakumar/mac-ops#499 | $7.74 | 50 |
| shyamsivakumar/mac-ops#486 | $6.71 | 38 |
| digitized/Concerning#102 | $6.28 | 29 |
| shyamsivakumar/openscan#11 | $4.86 | 22 |
| shyamsivakumar/mac-ops#480 | $4.55 | 28 |
```

Reconciliation: independent sum of every turn cost on that local day is 314.66; the report shows 176.44 on pull requests plus 138.22 unattributed = 314.66.

## --repo digitized/Concerning on real traces
```
# Agent cost per pull request in digitized/Concerning, 2026-11-17

$15.18 on 4 pull requests.

| Pull request | Cost | Turns |
| --- | ---: | ---: |
| digitized/Concerning#102 | $6.28 | 29 |
| digitized/Concerning#104 | $3.64 | 23 |
| digitized/Concerning#98 | $2.74 | 17 |
| digitized/Concerning#100 | $2.53 | 17 |
```
