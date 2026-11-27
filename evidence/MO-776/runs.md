# MO-776 runs

## Replacement proof command (for the ticket Acceptance)

Assigned rows carry `experiment`, as `ticket start` now stamps them.
Heads are random because `clean_rows` drops 40 identical characters as a
placeholder. The old fixture's `aaaa...a` heads lost every verdict.

```bash
T=$(mktemp -d); python3 - $T <<'E'
import json, random, sys
random.seed(7); rows=[]
for i in range(300):
    arm = 'treatment' if i % 2 else 'control'
    head = '%040x' % random.getrandbits(160)
    rows.append({'v':1,'ts':1763600000+i,'event':'assigned',
        'repo':'r','ticket':i,'arm':arm,
        'data':{'experiment':'x','cluster':f'c{i//3}'}})
    rows.append({'v':1,'ts':1763600000+i,'event':'gate_verdict',
        'repo':'r','ticket':i,'pr':i,'head':head,
        'data':{'verdict':'PASS' if random.random()<0.44 else 'FAIL'}})
open(sys.argv[1]+'/events-2026-11.jsonl','w').write(
    '\n'.join(map(json.dumps,rows))+'\n')
E
python3 coordinator/bin/scorecard compare \
  --experiment x --journal-dir $T | tail -1
```

Expected red on `origin/main`:

<!-- markdownlint-disable MD013 -->
```text
scorecard: error: argument command: invalid choice: 'compare' (choose from 'backfill')
```
<!-- markdownlint-enable MD013 -->

Expected green on the PR head: `no difference`.

## Red on origin/main (897dced2)

```
scorecard-main: error: argument command: invalid choice: 'compare' (choose from 'backfill')
```

## Green on the branch (replacement proof command, full output)

```
target 260 tickets, 300 assigned, final cohort is the first 260
control: 130 tickets in 87 clusters, first-gate PASS 43.8%
treatment: 130 tickets in 87 clusters, first-gate PASS 38.5%
gap -5.4 points, cluster-bootstrap p 0.3854 (4000 draws, seed 7)
time to merge: not enough merges
no difference
```

Cohorts: the interim cohort is the first ceil(target/2) tickets by assignment time, the final cohort is the first target. Tickets after the target are counted but never change the decision. Runs below use 300 tickets, so the final cohort (the first 260) is decided.

## A/A, 44 vs 44

```
target 260 tickets, 300 assigned, final cohort is the first 260
control: 130 tickets in 87 clusters, first-gate PASS 43.8%
treatment: 130 tickets in 87 clusters, first-gate PASS 38.5%
gap -5.4 points, cluster-bootstrap p 0.3854 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
no difference
```

## Treatment better, 35 vs 60

```
target 260 tickets, 300 assigned, final cohort is the first 260
control: 130 tickets in 87 clusters, first-gate PASS 35.4%
treatment: 130 tickets in 87 clusters, first-gate PASS 53.8%
gap +18.5 points, cluster-bootstrap p 0.0015 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
treatment wins
```

## Control better, 60 vs 35

```
target 260 tickets, 300 assigned, final cohort is the first 260
control: 130 tickets in 87 clusters, first-gate PASS 63.8%
treatment: 130 tickets in 87 clusters, first-gate PASS 33.1%
gap -30.8 points, cluster-bootstrap p 0.0005 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
control wins
```

## Treatment tickets never merge, 35 vs 60

```
target 260 tickets, 300 assigned, final cohort is the first 260
control: 130 tickets in 87 clusters, first-gate PASS 35.4%
treatment: 130 tickets in 87 clusters, first-gate PASS 53.8%
gap +18.5 points, cluster-bootstrap p 0.0015 (4000 draws, seed 7)
time to merge: not enough merges
no difference
```

With --target 400 (interim cohort is the first 200 of 300):

```
target 400 tickets, 300 assigned, interim cohort is the first 200
control: 100 tickets in 67 clusters, first-gate PASS 37.0%
treatment: 100 tickets in 67 clusters, first-gate PASS 53.0%
gap +16.0 points, cluster-bootstrap p 0.0170 (4000 draws, seed 7)
time to merge: not enough merges
continue
```

## Two experiments in one journal (x is A/A, y has a real effect, 300 tickets each)

--experiment x

```
target 260 tickets, 300 assigned, final cohort is the first 260
control: 130 tickets in 87 clusters, first-gate PASS 43.8%
treatment: 130 tickets in 87 clusters, first-gate PASS 38.5%
gap -5.4 points, cluster-bootstrap p 0.3854 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
no difference
```

--experiment y

```
target 260 tickets, 300 assigned, final cohort is the first 260
control: 130 tickets in 87 clusters, first-gate PASS 38.5%
treatment: 130 tickets in 87 clusters, first-gate PASS 58.5%
gap +20.0 points, cluster-bootstrap p 0.0015 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
treatment wins
```

## One interim look: more tickets between 130 and 259 never change the decision

Same seed, so each journal extends the previous one. A/A (no early stop) and a strong effect (30 vs 65, stops at the interim look) print the same interim result at 130, 160, 200 and 259 assigned. At 100 assigned (below half) the answer is continue. At the target the final cohort is decided.

A/A, 100 assigned

```
target 260 tickets, 100 assigned, interim cohort is the first 130
continue
```

A/A, 130 assigned

```
target 260 tickets, 130 assigned, interim cohort is the first 130
gap -7.7 points, cluster-bootstrap p 0.3754 (4000 draws, seed 7)
continue
```

A/A, 160 assigned

```
target 260 tickets, 160 assigned, interim cohort is the first 130
gap -7.7 points, cluster-bootstrap p 0.3754 (4000 draws, seed 7)
continue
```

A/A, 200 assigned

```
target 260 tickets, 200 assigned, interim cohort is the first 130
gap -7.7 points, cluster-bootstrap p 0.3754 (4000 draws, seed 7)
continue
```

A/A, 259 assigned

```
target 260 tickets, 259 assigned, interim cohort is the first 130
gap -7.7 points, cluster-bootstrap p 0.3754 (4000 draws, seed 7)
continue
```

30 vs 65, 130 assigned

```
target 260 tickets, 130 assigned, interim cohort is the first 130
gap +24.6 points, cluster-bootstrap p 0.0040 (4000 draws, seed 7)
treatment wins
```

30 vs 65, 200 assigned

```
target 260 tickets, 200 assigned, interim cohort is the first 130
gap +24.6 points, cluster-bootstrap p 0.0040 (4000 draws, seed 7)
treatment wins
```

30 vs 65, 259 assigned

```
target 260 tickets, 259 assigned, interim cohort is the first 130
gap +24.6 points, cluster-bootstrap p 0.0040 (4000 draws, seed 7)
treatment wins
```

## Settle cutoff: the same cohort read before and after it, and with post-cutoff events

Fixture timestamps are in November 2025, so no run waits. The interim cohort is the first 130 tickets; its cutoff is the 130th assignment plus 7 days. In this journal a third of the treatment tickets have no gate verdict or merge by the cutoff. A hidden --now sets the clock.

Before the cutoff (--now 1763830000):

```
target 260 tickets, 200 assigned, interim cohort is the first 130
continue (interim cohort settles at 2025-11-28T04:43-08:00)
```

After the cutoff:

```
target 260 tickets, 200 assigned, interim cohort is the first 130
control: 65 tickets in 43 clusters, first-gate PASS 35.4%
treatment: 65 tickets in 44 clusters, first-gate PASS 38.5%
gap +3.1 points, cluster-bootstrap p 0.6883 (4000 draws, seed 7)
continue
```

After the cutoff, with verdicts and merges for those pending tickets added at later timestamps (ignored, same decision):

```
target 260 tickets, 200 assigned, interim cohort is the first 130
control: 65 tickets in 43 clusters, first-gate PASS 35.4%
treatment: 65 tickets in 44 clusters, first-gate PASS 38.5%
gap +3.1 points, cluster-bootstrap p 0.6883 (4000 draws, seed 7)
continue
```

Control: the same late events placed before the cutoff would have flipped the look:

```
target 260 tickets, 200 assigned, interim cohort is the first 130
control: 65 tickets in 43 clusters, first-gate PASS 35.4%
treatment: 65 tickets in 44 clusters, first-gate PASS 72.3%
gap +36.9 points, cluster-bootstrap p 0.0005 (4000 draws, seed 7)
treatment wins
```

## No match, exit 1

```
compare: no control or treatment assignments for zz in the journal; register an experiment in coordinator/config/factory.json
rc=1
```

## Stamp

`journal.arms_for` with a builder experiment b1 and a gate experiment g1 registered:

<!-- markdownlint-disable MD013 -->
```text
{'arm': 'control', 'experiment': 'b1', 'gate_arm': 'control', 'gate_experiment': 'g1'}
```
<!-- markdownlint-enable MD013 -->
