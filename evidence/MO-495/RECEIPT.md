# Receipt for #495

Heavy frees a dead job's slot and cleans up the simulators a build booted.

## Dead job release

A real supervisor process ran in a real registry beside the live capacity
contract (`dead_job_and_simulator_proof.py`):

```
supervisor pid: 57938
active jobs before the kill: 1
reaped jobs: ['925cad6cb3424657a30290e862e6b076']
active jobs after the reap: 0
job-dead log lines: 1
job-dead log line: {"command": "sleep", "detail": "supervisor-gone; slot freed", "event": "job-dead", ...}
```

The process table is read under the registry lock, so a supervisor that
registered after the read is never reaped. The recorded boot id is part of the
identity, so a pid from another boot cannot match.

## Simulator cleanup

A simulator job records the booted devices before it starts. When the job ends
on any outcome, the devices that the job booted are shut down
(`simulator_cleanup_proof.py`):

```
booted devices before: ['0A9E4E19-...', '193BDCDC-...', '80064A77-...']
simulator process count before: 527
booted devices while the job runs: [4 devices]
simulator process count while the job runs: 547
devices shut down when the job ended: ['EE63FDDC-24A9-46CF-BD25-C384B5D1DD0B']
booted devices after: ['0A9E4E19-...', '193BDCDC-...', '80064A77-...']
simulator process count after: 527
baseline was: 527
```

The cleanup holds the simulator lock while it reads the competing jobs and
shuts a device down, and a simulator job takes the same lock before it records
its devices and launches its workload. A device another running job may use is
left alone.

## Orphan sweep

The governor tick stops the simulator processes that belong to no booted device.
A process is a simulator process only when its own executable is the simulator
launchd or lives in a device data directory or a simulator runtime, so a command
that only names a simulator path, such as a log tail, is never touched. Each
device is handled on its own: the booted devices and the process table are read
again after the identities were collected and right before that device's
processes are signalled, and again before the escalation to SIGKILL. A signal
goes only to a process whose uid and start token match the ones read with its
classification.

## M1 device and live testing

Waived by Shyam on 2026-11-14: "no testing is needed lets just finish backlog
building everything". The M1 heavy xcodebuild run that boots CI-iPhone, and the
M1 live post-build process count, are waived and not failed. The M1 host was
read only, without a build, at proof time: zero simulator runtime processes and
zero booted devices.

## Check

The repo check passed at `d4dc12726e3020a87bfa766c0d7b516675177cc8` with a
clean tree. The proof file `check-proof.md` lists every check, its command, and
its result.
