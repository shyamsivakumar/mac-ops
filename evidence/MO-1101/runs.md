# MO-1101 proof

## Ticket proof command, before (origin/main)
```
answered rows have no options
exit 1
```

## After (branch)
```
answered rows carry options
exit 0
```

## Temp journal run: fake card answered with an option, and with free text
```
held-out cases after 2020-01-01T00:00:00Z: 1; dropped for Ascend or secrets: 0
labels: 2
with options: 2
counts: {'FINAL': 1, 'DEV': 1, 'HELDOUT': 0}
repeats: 0 dropped: 0
--- heldout_cases.jsonl
{"id": "fake-1", "kind": "model_choice", "item_text": "Use the fast model or the slow model for the nightly job?", "recommended": "fast model", "answer": "slow model", "agree": false, "ts": "2026-11-28T05:55:12.638Z", "source": "journal decision_answered", "options": ["fast model", "slow model"], "recommended_option": "fast model"}
--- labels.jsonl fake-2 (kept, not counted)
{"id": "fake-2", "kind": "other", "item_text": "Pick a color", "recommended": "red", "answer": "purple, whatever", "agree": false, "ts": "2026-11-28T05:55:12.638Z", "source": "journal decision_answered", "options": ["red", "blue"], "recommended_option": "red"}
```
