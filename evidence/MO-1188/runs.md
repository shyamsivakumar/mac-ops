# MO-1188 runs

## Before: origin/main on the M1 (Python 3.14.7, no ~/.herdr-projects)

    python3 -m unittest tests.test_retrospective tests.test_scorecard_policy
    FileNotFoundError: ~/.herdr-projects/data/tasks/catalogue/2/task.json
    FileNotFoundError: ~/.herdr-projects/data/tasks/strategy-replay-workbench/61/task.json
    FileNotFoundError: ~/.herdr-projects/data/tasks/llmwiki/10/task.json
    FAILED (errors=3)

The two retrospective ERRORs and the scorecard error all read live board files. The headroom case failed because Python 3.14 parses 2000 nested brackets without a RecursionError (it parses 100000 levels; it raises only near 1000000), and heavy.py refuses config files over 4096 bytes, so no file under the cap can raise it on 3.14.

## After: branch head 2c67e8f7 on the M1 and on this Mac (3.9)

    python3 -m unittest tests.test_scorecard_policy tests.test_retrospective tests.test_heavy_host_headroom
    Ran 26 tests ... OK   (M1, 3.14.7)
    Ran 26 tests ... OK   (this Mac, 3.9.6)

## M1 fast check

    scripts/remote_fast_check.sh --remote mo1188-m1-tests 2c67e8f7db33c269892a2a586e6e48bf74cc0d2d evidence/MO-1188/m1-check-proof.md
    grep -c "Run result: passed" evidence/MO-1188/m1-check-proof.md
    1
