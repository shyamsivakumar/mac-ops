# Runs

## Ticket proof (red on main, green on branch)

Command: `python3 coordinator/evals/hillclimb/daily3.py -h | grep -c "raise today's questions"`

- origin/main: 0
- branch: 1

## Behavior on temp dirs and a temp decisions file

```
== main: daily3.py post
usage: daily3.py [-h] {pick,record} ...
daily3.py: error: argument command: invalid choice: 'post' (choose from 'pick', 'record')
== main: burst.py without labels.jsonl
    return self._accessor.open(self, flags, mode)
FileNotFoundError: [Errno 2] No such file or directory: 'SCRATCH/d3QvDU/labels.jsonl'
== branch: post
daily3: posted 2 of 2 cards to SCRATCH/d3QvDU/decisions.json
rc=0
== branch: post again (same day)
daily3: already posted on 2026-11-27; nothing to do
rc=0
== cards on the temp board
{"id": "daily3-2026-11-27-a", "group": "Daily 3", "kind": "ask", "title": "Merge PR 1 now?", "why": "Daily 3 question (merge). Your answer becomes a scored label: daily3.py record --id a --choice '<option>'", "options": [{"label": "Merge it", "detail": "", "recommended": true}, {"label": "Hold it", "detail": "", "recommended": false}, {"label": "Close it", "detail": "", "recommended": false}]}
{"id": "daily3-2026-11-27-c", "group": "Daily 3", "kind": "ask", "title": "Spend 5 dollars?", "why": "Daily 3 question (money). Your answer becomes a scored label: daily3.py record --id c --choice '<option>'", "options": [{"label": "Yes spend", "detail": "", "recommended": false}, {"label": "No skip", "detail": "", "recommended": true}]}
5 items
== guess log
{"ts": "2026-11-27T21:28:23.949162+00:00", "label_id": "a", "kind": "merge", "item_text": "Merge PR 1 now?", "options": ["Merge it", "Hold it", "Close it"], "guess": "Merge it", "guess_source": "recorded recommended option", "posted": "2026-11-27"}
{"ts": "2026-11-27T21:28:23.949162+00:00", "label_id": "c", "kind": "money", "item_text": "Spend 5 dollars?", "options": ["Yes spend", "No skip"], "guess": "No skip", "guess_source": "recorded recommended option", "posted": "2026-11-27"}
== branch: burst.py without labels.jsonl
burst: SCRATCH/d3QvDU/coordinator/evals/hillclimb/labels.jsonl is missing; run build_labels.py first
gate_disagreements.jsonl: 35 new
rc=1
tmp: SCRATCH/d3QvDU
```

## Retry after a refused card

```
daily3: card daily3-2026-11-27-c could not be published
daily3: posted 1 of 2 cards to SCRATCH/tmpa57u433r/decisions.json
run 1 (card c refused): rc 1
cards: ['daily3-2026-11-27-a']
guess rows: 2 posted marker: False
daily3: posted 2 of 2 cards to SCRATCH/tmpa57u433r/decisions.json
run 2 (board healthy): rc 0
cards: ['daily3-2026-11-27-a', 'daily3-2026-11-27-c']
guess rows: 3 posted marker: True
daily3: already posted on 2026-11-27; nothing to do
run 3: rc 0
```
