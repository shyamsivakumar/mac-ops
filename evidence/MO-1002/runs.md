# MO-1002 runs

## Red on origin/main: proof command
```
Traceback (most recent call last):
  File "<stdin>", line 10, in <module>
AssertionError: a Scope reference is read as a blocker: '#900 is merged. No open predecessor.\n\n**Scope and non-goals:** Use compact replay cases from #2624.'
```

## Red on origin/main: new selftest case
```

- ['shyamsivakumar/strategy-replay-workbench#816 is not merged']
+ []

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (failures=1)
```

## Green on branch: proof command
```
scan reads only the declared blocker sections
```

## Green on branch: new selftest case
```
----------------------------------------------------------------------
Ran 1 test in 0.000s

OK
```
