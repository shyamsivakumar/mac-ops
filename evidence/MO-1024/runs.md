# MO-1024 proof

Command: `bash evidence/MO-1024/proof.sh <tree>`.

It uses a temp COORD_JOURNAL_DIR and decisions file and emits 3 gap rows.
It runs `curator --dry-run`, then `curator`, then prints the board.

Code commit: 169bca12e06444f803d27cf14363e0ae12936ceb.

## origin/main (red), tree from `git archive origin/main coordinator`

```text
Traceback (most recent call last):
  File "<stdin>", line 5, in <module>
AttributeError: module 'journal' has no attribute 'emit_gap'
--- curator --dry-run
evidence/MO-1024/proof.sh: line 16: coordinator/bin/curator: No such file or directory
--- board after dry-run
{"items":[]}
--- curator
evidence/MO-1024/proof.sh: line 20: coordinator/bin/curator: No such file or directory
--- board
[]
```

## branch head (green)

<!-- markdownlint-disable MD013 -->

```text
--- curator --dry-run
{
  "id": "gap-e22545c45a",
  "group": "Coordinator",
  "kind": "ask",
  "title": "Playbook gap: 2 workers lacked 'no playbook for cloud run deploys'",
  "cause": "2 gap rows on cards 1101, 1102",
  "why": "Missing: no playbook for cloud run deploys!. Workers looked in: playbooks/ and wiki.",
  "options": [
    {
      "label": "Add it to the playbook the workers read",
      "detail": "",
      "recommended": true
    }
  ]
}
--- board after dry-run
{"items":[]}
--- curator
raised gap-e22545c45a
--- board
['gap-e22545c45a']
```

<!-- markdownlint-enable MD013 -->
