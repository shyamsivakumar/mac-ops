# MO-1015 proof

Command: `python3 evidence/MO-1015/proof.py`

Red (checker from origin/main): both bad rules are accepted, nothing validates `check`.

```text
real rule: ['zip-strict-py39: zip(strict=...) needs Python 3.10; ... (fixture.py)']
bad rule accepted: {'id': 'r', 'paths': '*.py', 'pattern': 'x', 'message': 'm'}
bad rule accepted: {'id': 'r', ..., 'message': 'm', 'check': 'vibes'}
```

Green (head): missing and unknown `check` are refused, the real rule flags the fixture.

```text
real rule: ['zip-strict-py39: zip(strict=...) needs Python 3.10; ... (fixture.py)']
bad rule refused: finding rule r: missing check
bad rule refused: finding rule r: check 'vibes' ... grep, lint, type, property
```
