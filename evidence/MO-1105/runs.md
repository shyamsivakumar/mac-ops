# MO-1105 proof

## Ticket proof command
```
on origin/main:
AttributeError: module 'install_coordinator' has no attribute 'unsourced_code'
on the branch:
['x.py']
exit 0
```

## status against a temp HOME and a temp coordinator folder

Folder holds: x.py (no source), set-posthog.sh and set-posthog-prod.sh (allowlisted), archive/y.py (excluded folder), evals/hillclimb/daily3.py (has a source), loop/settle.py.bak and loop/run.log (not code).
```
in_sync False
unsourced_code ['x.py']
exit 1
```

After removing x.py:

```
in_sync False
unsourced_code []
exit 0
```
