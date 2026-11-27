# MO-1067 runs

Proof command (red on origin/main, green on the head):

```
out=$(python3 coordinator/evals/hillclimb/daily3.py --data "$(mktemp -d)" pick 2>&1); echo "$out"; case "$out" in *"unrecognized arguments"*|*"invalid choice"*|*usage*) exit 1;; esac
```

## Red on origin/main 120939b0 (the three scripts from main, run from a scratch dir)

```
usage: daily3.py [-h] {pick,record} ...
daily3.py: error: argument command: invalid choice: '/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.bswhrKm2aC' (choose from 'pick', 'record')
```

## Green on the head

```
daily3: nothing to ask; the inbox and the backlog are both empty
exit=0
```

## Writes land in the scratch copy only (copy of ~/Code/coordinator/evals/hillclimb, 147 labels)

```
$ daily3.py --data COPY pick
daily3: nothing to ask; the inbox and the backlog are both empty
$ burst.py --data COPY --log-disagreements
gate_disagreements.jsonl: 0 new
$ daily3.py --data COPY record --id merge-lmw-244 --choice no --escaped-bug
daily3: escaped bug merge-lmw-244 written to hard_set.jsonl (not scored)
$ daily3.py pick --data
--data needs a directory
copy hard_set.jsonl rows: 1
installed hard_set.jsonl rows: 0
installed gate_disagreements.jsonl size before and after the --data burst run: 11521 and 11521 bytes
```

## Overnight selftest (heavy): 37 PASS, 0 FAIL, including the inbox burst case that copies the scripts beside sentinel data.
