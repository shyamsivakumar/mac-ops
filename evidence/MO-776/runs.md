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

<!-- markdownlint-disable MD013 -->
```text
scorecard-main: error: argument command: invalid choice: 'compare' (choose from 'backfill')
```
<!-- markdownlint-enable MD013 -->

## Green on the branch

```text
no difference
```

## Synthetic A/A, 44 vs 44 percent (experiment x)

```text
control: 150 tickets in 100 clusters, first-gate PASS 43.3%
treatment: 150 tickets in 100 clusters, first-gate PASS 40.7%
target 260 tickets, 300 assigned
gap -2.7 points, cluster-bootstrap p 0.6458 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
no difference
```

## Synthetic treatment better, 35 vs 60 percent

```text
control: 150 tickets in 100 clusters, first-gate PASS 36.0%
treatment: 150 tickets in 100 clusters, first-gate PASS 55.3%
target 260 tickets, 300 assigned
gap +19.3 points, cluster-bootstrap p 0.0010 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
treatment wins
```

## Synthetic control better, 60 vs 35 percent

```text
control: 150 tickets in 100 clusters, first-gate PASS 62.7%
treatment: 150 tickets in 100 clusters, first-gate PASS 35.3%
target 260 tickets, 300 assigned
gap -27.3 points, cluster-bootstrap p 0.0005 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
control wins
```

## Two experiments in one journal

Experiment x is A/A (44 vs 44) and y has a real effect (35 vs 60).
Each has 300 tickets on the builder side and counts only its own.

```text
--experiment x
control: 150 tickets in 100 clusters, first-gate PASS 43.3%
treatment: 150 tickets in 100 clusters, first-gate PASS 40.7%
target 260 tickets, 300 assigned
gap -2.7 points, cluster-bootstrap p 0.6458 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
no difference

--experiment y
control: 150 tickets in 100 clusters, first-gate PASS 36.7%
treatment: 150 tickets in 101 clusters, first-gate PASS 60.0%
target 260 tickets, 300 assigned
gap +23.3 points, cluster-bootstrap p 0.0005 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
treatment wins
```

## No match, exit 1

These cases all print the output below and exit 1:

- a misspelled name (`zz`)
- a missing journal directory
- a read-only run on the live journal (no row has an experiment yet)

<!-- markdownlint-disable MD013 -->
```text
compare: no control or treatment assignments for zz in the journal; register an experiment in coordinator/config/factory.json
rc=1
```
<!-- markdownlint-enable MD013 -->

## Stamp

`journal.arms_for` with a builder experiment b1 and a gate experiment g1 registered:

<!-- markdownlint-disable MD013 -->
```text
{'arm': 'control', 'experiment': 'b1', 'gate_arm': 'control', 'gate_experiment': 'g1'}
```
<!-- markdownlint-enable MD013 -->

## Treatment tickets never merge (35 vs 60 percent PASS)

Treatment passes the gate more often but has no merged row, so `treatment wins` is withheld. Past the target (260, 300 assigned) the decision is `no difference`:

```
control: 150 tickets in 100 clusters, first-gate PASS 36.0%
treatment: 150 tickets in 100 clusters, first-gate PASS 55.3%
target 260 tickets, 300 assigned
gap +19.3 points, cluster-bootstrap p 0.0010 (4000 draws, seed 7)
time to merge: not enough merges
no difference
```

Same journal with `--target 400` (300 is past half but short of the target):

```
target 400 tickets, 300 assigned
gap +19.3 points, cluster-bootstrap p 0.0010 (4000 draws, seed 7)
time to merge: not enough merges
continue
```

The four cases above (A/A, treatment better, control better, two experiments) were rerun after this change with the same results, and the replacement proof command still ends in `no difference`.

## Control tickets never merge (60 vs 35 percent PASS)

The mirror of the case above. Control passes the gate more often, but only
treatment ticket numbers carry a `merged` row, so control has no observed
merge time and `control wins` is withheld too. Past the target (260, 300
assigned) the decision is `no difference`:

```text
control: 150 tickets in 100 clusters, first-gate PASS 62.7%
treatment: 150 tickets in 100 clusters, first-gate PASS 35.3%
target 260 tickets, 300 assigned
gap -27.3 points, cluster-bootstrap p 0.0005 (4000 draws, seed 7)
time to merge: not enough merges
no difference
```

Same journal with `--target 400` (300 is past half but short of the target):

```text
target 400 tickets, 300 assigned
gap -27.3 points, cluster-bootstrap p 0.0005 (4000 draws, seed 7)
time to merge: not enough merges
continue
```

`coordinator/bin/scorecard` at the previous head prints `control wins` for both
of those runs. A winner needs an observed merge time in both arms, so neither
arm can win on first-gate PASS results alone.

## Decision rule cases

`decide(p, gap, tickets, target, merge_ok)` is the whole stopping rule. The
twelve cases below are asserted against the function, so each branch is named
rather than inferred from a journal:

```text
ok   past target, merges ok -> treatment wins
ok   past target, merges unknown -> no difference
ok   treatment over the 15 percent limit -> no difference
ok   interim, merges unknown -> continue
ok   past target, control better, merges ok -> control wins
ok   past target, control better, merges unknown -> no difference
ok   interim, control better, merges unknown -> continue
ok   tie at the target -> no difference
ok   tie at interim -> continue
ok   below half of the target -> continue
ok   interim p cutoff not reached -> continue
ok   final p cutoff not reached -> no difference
all 12 decide() cases hold
```
