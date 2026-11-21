# MO-622 proof runs

## Before (origin/main heavy.py)
```
[job boots NEW, OLD booted before] still booted: ['OLD', 'NEW']  simctl shutdown calls: []
  events: []
[job boots NEW while another heavy job runs] still booted: ['OLD', 'NEW']  simctl shutdown calls: []
  events: []
[job boots nothing] still booted: ['OLD']  simctl shutdown calls: []
  events: []
Traceback (most recent call last):
  File "/Users/shyamsivakumar/Code/mac-ops-worktrees/mo622/evidence/MO-622/proof.py", line 93, in <module>
    second_job_after_first_shutdown()
  File "/Users/shyamsivakumar/Code/mac-ops-worktrees/mo622/evidence/MO-622/proof.py", line 76, in second_job_after_first_shutdown
    chained = dataclasses.replace(deps, shutdown_simulator=shutdown_then_register)
  File "/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/dataclasses.py", line 1284, in replace
    return obj.__class__(**changes)
TypeError: __init__() got an unexpected keyword argument 'shutdown_simulator'
```

(The last scenario cannot run on origin/main: it has no shutdown hook, so the script stops with the TypeError above. No simulator is shut down there in any scenario.)

## After (branch)
```
[job boots NEW, OLD booted before] still booted: ['OLD']  simctl shutdown calls: ['shutdown NEW']
  events: [('simulator-shutdown', 'NEW')]
[job boots NEW while another heavy job runs] still booted: ['OLD', 'NEW']  simctl shutdown calls: []
  events: [('simulator-cleanup-skipped', 'NEW')]
[job boots nothing] still booted: ['OLD']  simctl shutdown calls: []
  events: []
[job boots A and B, a second job registers after A is shut down] still booted: ['OLD', 'B']  simctl shutdown calls: ['shutdown A']
  events: [('simulator-shutdown', 'A'), ('simulator-cleanup-skipped', 'B')]
```

Stubbed xcrun on PATH (fake simctl list/boot/shutdown, erase/delete log FORBIDDEN); real run_supervisor and Registry in a temp dir. No real simulator was booted. The last scenario registers a second job between the shutdown of A and B: B is skipped and stays booted, so the overlap window is one device shutdown.
