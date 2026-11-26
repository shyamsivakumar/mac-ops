# MO-776 runs

Proof: A/A fixture, 300 tickets, 100 clusters of 3, 44% PASS in both arms.

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

Full output of the same run:

```text
control: 150 tickets in 100 clusters, first-gate PASS 0.0%
treatment: 150 tickets in 100 clusters, first-gate PASS 0.0%
gap +0.0 points, cluster-bootstrap p 1.0000 (4000 draws, seed 7)
time to merge median: control None, treatment None, non-inferior
no difference
```

Every fixture `gate_verdict` has the head `aaaa...a` (40 identical
characters). `clean_rows` drops it as a placeholder, discarding every verdict,
so both arms read 0.0 percent. The decision is correct but weak evidence. The
runs below use random heads, one `merged` row per ticket (500 seconds after assignment)
and the arm on the row, as `ticket start` writes it.

## Synthetic A/A, 44 vs 44 percent

```text
control: 150 tickets in 100 clusters, first-gate PASS 43.3%
treatment: 150 tickets in 100 clusters, first-gate PASS 40.7%
gap -2.7 points, cluster-bootstrap p 0.6458 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
no difference
```

## Synthetic treatment better, 35 vs 60 percent

```text
control: 150 tickets in 100 clusters, first-gate PASS 36.0%
treatment: 150 tickets in 100 clusters, first-gate PASS 55.3%
gap +19.3 points, cluster-bootstrap p 0.0010 (4000 draws, seed 7)
time to merge median: control 500.0, treatment 500.0, non-inferior
treatment wins
```

## Synthetic control better, 60 vs 35 percent, last line

```text
control wins
```

## No experiment data

Tried a missing journal directory and the live journal, read only:
`~/.local/state/coordinator/journal` (no `assigned` row has an arm yet).
Both exit 1 with a message, no traceback.

<!-- markdownlint-disable MD013 -->

```text
compare: no arm assignments for x in the journal, so no experiment has run (register one in coordinator/config/factory.json)
rc=1
```

<!-- markdownlint-enable MD013 -->
