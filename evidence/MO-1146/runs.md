# Proof runs for #1146

## Ticket proof command

```
$ grep -q 'rule.get("scope"' scripts/mac_ops_fast_check.py || { echo "no scope handling"; exit 1; }
(origin/main) no scope handling, exit 1
(head) exit 0
```

## Fixture repo: guard.py already holds a git stash line on the base commit

`python3 evidence/MO-1146/proof.py <fast check file>` builds a temp git repo, then edits an unrelated line, then adds a new stash line.

### Red: origin/main scripts/mac_ops_fast_check.py (whole-file match)

```
unrelated edit, added scope : ['no-git-stash: stash (guard.py)']
unrelated edit, file scope  : ['whole-file: stash (guard.py)']
added stash line            : ['no-git-stash: stash (guard.py)']
```

The unrelated edit is flagged on lines it did not add.

### Green: the head

```
unrelated edit, added scope : []
unrelated edit, file scope  : ['whole-file: stash (guard.py)']
added stash line            : ['no-git-stash: stash (guard.py)']
bad scope                   : finding rule no-git-stash: scope must be 'added' or 'file'
```
