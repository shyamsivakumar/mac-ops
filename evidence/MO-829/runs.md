# MO-829 proof runs

## Before (origin/main gate_policy.py)
```
AttributeError: module 'gate_policy_main_tmp' has no attribute 'verdict'
old read_verdict on 1595 report: None
```

## After (branch), ticket proof command on three reports
```
1595 PASS
fail FAIL
none None
```

`grep -rn "VERDICT:" coordinator/bin` now shows the rule only in gate_policy.py (verdict regex); coordq calls it. ticket keeps its separate close-comment strings (out of scope).
