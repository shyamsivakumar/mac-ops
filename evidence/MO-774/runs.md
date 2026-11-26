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

## Cluster walk, stamps, launch rows and crash paths (cluster-probe.py, temp COORD_JOURNAL_DIR and HOME)
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
--- crash paths
malformed json []
not an object []
bad entries []
one per side ['a', 'g']
assigned row without data treatment None
non-numeric ticket None None None

stderr:
journal: /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp4t7l_8cn/.coordinator/factory.json unreadable, no experiment registered: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
journal: /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp4t7l_8cn/.coordinator/factory.json unreadable, no experiment registered: 'list' object has no attribute 'get'
journal: experiment skipped, needs a name, a side of builder or gate and a numeric split: {'name': 'a', 'side': 'other', 'split': 5}
journal: experiment skipped, needs a name, a side of builder or gate and a numeric split: {'name': 'b', 'side': 'gate'}
journal: experiment skipped, needs a name, a side of builder or gate and a numeric split: {'name': 'c', 'side': 'gate', 'split': 'x'}
journal: experiment skipped, needs a name, a side of builder or gate and a numeric split: 'junk'
journal: experiment b refused, a is already active on side builder
```
