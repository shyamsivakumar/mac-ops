# Check proof

Code commit: `1e6bdeb0815b0a23a95b2ef639d54d6213824ef0`
Run result: incomplete; host capacity blocked the required repo check.

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| month-boundary regression | existing stale_started_refill selftest with original lookup, then fixed lookup | passed | original fails at February recovery; fixed lookup passes real February and December journals on 2025-03-01 |
| repo check through heavy | `timeout 300 ~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py --proof evidence/MO-1004/check-proof.md` | incomplete | exit 124; queued for capacity, then overnight selftests passed before another capacity pause; no completed full result |
| repo check through heavy review | `timeout 300 ~/.local/bin/heavy --review python3 scripts/mac_ops_fast_check.py --proof evidence/MO-1004/check-proof.md` | not run | exit 124 waiting for global slots/capacity; actual check never started |
| device, handset and live service | waived by Shyam | waived | not run; not failed |

No checks were bypassed and no host capacity setting was changed. The prior proof described the previous revision; it does not certify this fix. The required full check remains outstanding.
