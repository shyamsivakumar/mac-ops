## Before (origin/main)
```
KeyError: 'parse_verdict'
```

## After (PR head)
```
FAIL 1 None
```

## Fixtures (adapted from the proof shape: three replies through parse_verdict, has_verdict, read_verdict)
```
valid json | parse_verdict: True | has_verdict: True | read_verdict: ('FAIL', [{'id': 'F1', 'severity': 'major', 'path': 'a.py', 'line': 3, 'text': 'bug'}])
malformed json, text fallback | parse_verdict: False | has_verdict: True | read_verdict: ('FAIL', [{'severity': 'major', 'path': 'b.py', 'line': 7, 'text': 'off by one'}])
old style | parse_verdict: False | has_verdict: True | read_verdict: ('FAIL', [{'severity': 'critical', 'path': 'c.py', 'line': 12, 'text': 'leaks a secret'}, {'severity': 'minor', 'path': 'd.py', 'line': 1, 'text': 'nit'}])
ticket proof: None
```
