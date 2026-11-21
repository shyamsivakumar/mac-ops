# MO-622 proof runs

## Before (origin/main heavy.py)
```
{"devices": {"iOS 18": [{"udid": "OLD", "state": "Booted"}]}}
[job boots NEW, OLD booted before] still booted: ['OLD', 'NEW']  simctl shutdown calls: []
  events: []
[job boots NEW while another heavy job runs] still booted: ['OLD', 'NEW']  simctl shutdown calls: []
  events: []
[job boots nothing] still booted: ['OLD']  simctl shutdown calls: []
  events: []
```

## After (branch)
```
{"devices": {"iOS 18": [{"udid": "OLD", "state": "Booted"}]}}
[job boots NEW, OLD booted before] still booted: ['OLD']  simctl shutdown calls: ['shutdown NEW']
  events: [('simulator-shutdown', 'NEW')]
[job boots NEW while another heavy job runs] still booted: ['OLD', 'NEW']  simctl shutdown calls: []
  events: [('simulator-cleanup-skipped', 'NEW')]
[job boots nothing] still booted: ['OLD']  simctl shutdown calls: []
  events: []
```

Stubbed xcrun on PATH (fake simctl list/boot/shutdown, erase/delete log FORBIDDEN); real run_supervisor and Registry in a temp dir. No real simulator was booted.
