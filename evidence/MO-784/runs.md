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

## Round 2 fixtures (gate findings: conflict and malformed findings)
Script: three reports through read_verdict and report_for_builder (a: JSON PASS with final `VERDICT: FAIL`; b: FAIL block with one string finding plus a prose `[major]` line; c: valid block).

Before (prior PR head, dc13619d plus merge):
```
a json PASS, final VERDICT: FAIL | read_verdict: ('PASS', [])
   report_for_builder: ok
b findings list with a string entry | read_verdict: ('FAIL', ['a.py:3 bug'])
   report_for_builder raises: AttributeError 'str' object has no attribute 'get'
c valid block | read_verdict: ('FAIL', [{'id': 'F1', 'severity': 'major', 'bar_clause': 'x', 'path': 'a.py', 'line': 3, 'text': 'bug', 'fixed_when': 'y'}])
   report_for_builder: ok
```

After (9b4fae53):
```
a json PASS, final VERDICT: FAIL | read_verdict: ('CONFLICT', [])
   report_for_builder: ok
b findings list with a string entry | read_verdict: ('FAIL', [{'severity': 'major', 'path': 'b.py', 'line': 7, 'text': 'off by one'}])
   report_for_builder: ok
c valid block | read_verdict: ('FAIL', [{'id': 'F1', 'severity': 'major', 'bar_clause': 'x', 'path': 'a.py', 'line': 3, 'text': 'bug', 'fixed_when': 'y'}])
   report_for_builder: ok
```
gate_verdict in lane_driver.py maps a CONFLICT from any reviewer to SPLIT.

## Round 3 fixtures (gate finding: a finding without `line` raised KeyError in classify_failure)
Script: two reports through parse_verdict, read_verdict and classify_failure (a: JSON block whose finding omits `line`, plus a prose `[major] b.py:7` line; b: JSON block with `"line": null`).

Before (current head 3a9bccf0):
```
line omitted | parse_verdict: True | read_verdict: [{'id': 'F1', 'severity': 'major', 'path': 'a.py', 'text': 'bug'}]
   classify_failure raises: KeyError 'line'
line null | parse_verdict: True | read_verdict: [{'id': 'F1', 'severity': 'major', 'path': 'a.py', 'line': None, 'text': 'bug'}]
   classify_failure: logic
```

After (valid_finding requires the `line` key; classify_failure reads f.get("line")):
```
line omitted | parse_verdict: False | read_verdict: [{'severity': 'major', 'path': 'b.py', 'line': 7, 'text': 'off by one'}]
   classify_failure: logic
line null | parse_verdict: True | read_verdict: [{'id': 'F1', 'severity': 'major', 'path': 'a.py', 'line': None, 'text': 'bug'}]
   classify_failure: logic
```
