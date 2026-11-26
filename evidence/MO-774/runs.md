# MO-774 runs

## Proof command on origin/main (journal.py from origin/main)
```
  File "<string>", line 3, in <module>
  File "<string>", line 3, in <genexpr>
AttributeError: module 'journal' has no attribute 'arm_for'
```

## Proof command on the branch
```
True
```

## Cluster walk, stamps and launch rows (cluster-probe.py, temp COORD_JOURNAL_DIR and HOME)
```
chain ('o/r#1', None)
cycle ('o/r#2', 'cycle') ('o/r#2', 'cycle')
depth ('o/r#14', 'depth')
unreadable ('o/r#10', 'unreadable')
truncated ('o/r#9', 'unreadable')
no experiment stamp {'arm': None}
experiment stamp {'cluster': 'o/r#10', 'cluster_note': None, 'arm': 'control', 'gate_arm': 'control'}
assigned o/r 9 arm= control {'cluster': 'o/r#10', 'cluster_note': None, 'gate_arm': 'control'}
launched o/r 9 arm= control {}
launched o/r 8 arm= None {}
gate arm control None
```
