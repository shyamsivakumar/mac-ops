# MO-622 proof runs

Fix round for PR 839: heavy shuts down only a simulator whose udid appears in the job's own command. A device that merely booted during the job is left alone.

## Before (PR head 0311a810 heavy.py)
```
[job boots NEW, OLD booted before] still booted: ['OLD']  simctl shutdown calls: ['shutdown NEW']
  events: [('simulator-shutdown', 'NEW')]
[job boots NEW while another heavy job runs] still booted: ['OLD', 'NEW']  simctl shutdown calls: []
  events: [('simulator-cleanup-skipped', 'NEW')]
[job boots NEW, a device not in its command boots too] still booted: ['OLD']  simctl shutdown calls: ['shutdown NEW', 'shutdown OTHER']
  events: [('simulator-shutdown', 'NEW'), ('simulator-shutdown', 'OTHER')]
[job boots nothing] still booted: ['OLD']  simctl shutdown calls: []
  events: []
[job boots A and B, a second job registers after A is shut down] still booted: ['OLD', 'B']  simctl shutdown calls: ['shutdown A']
  events: [('simulator-shutdown', 'A'), ('simulator-cleanup-skipped', 'B')]
```
The new case ("a device not in its command boots too") shuts down OTHER, a device the job never named.

## After (this fix)
```
[job boots NEW, OLD booted before] still booted: ['OLD']  simctl shutdown calls: ['shutdown NEW']
  events: [('simulator-shutdown', 'NEW')]
[job boots NEW while another heavy job runs] still booted: ['OLD', 'NEW']  simctl shutdown calls: []
  events: [('simulator-cleanup-skipped', 'NEW')]
[job boots NEW, a device not in its command boots too] still booted: ['OLD', 'OTHER']  simctl shutdown calls: ['shutdown NEW']
  events: [('simulator-shutdown', 'NEW')]
[job boots nothing] still booted: ['OLD']  simctl shutdown calls: []
  events: []
[job boots A and B, a second job registers after A is shut down] still booted: ['OLD', 'B']  simctl shutdown calls: ['shutdown A']
  events: [('simulator-shutdown', 'A'), ('simulator-cleanup-skipped', 'B')]
```
OTHER stays booted; NEW, named in the command, is shut down. The other scenarios are unchanged.

Stubbed xcrun on PATH (fake simctl list/boot/shutdown, erase/delete log FORBIDDEN); real run_supervisor and Registry in a temp dir. No real simulator was booted. Run: `python3 evidence/MO-622/proof.py [heavy dir]`.
