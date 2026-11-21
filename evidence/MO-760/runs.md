# MO-760 runs

Adapted proof command: the temp HOME is resolved with `pwd -P` because the installer opens paths with O_NOFOLLOW and `/var/folders/...` goes through the `/var` symlink (`Not a directory: 'var'`). `--no-smoke` added to skip smoke checks.

```
T=$(cd "$(mktemp -d)" && pwd -P); mkdir -p $T/.coordinator; python3 -c "
import json; c=json.load(open('coordinator/config/tickets.json')); del c['repos']['shyamsivakumar/mac-ops']['build']
json.dump(c, open('$T/.coordinator/tickets.json','w'))"
HOME=$T python3 install_coordinator.py status --no-smoke | jq -c '.config_key_drift'
```

- origin/main: `null`
- branch: `["repos.shyamsivakumar/mac-ops.build"]`
- extra live keys only (`repos.*.zzz`, `x`): `[]`
- live `projectId` differs: `[]`
- live `build` has another value: `["repos.shyamsivakumar/mac-ops.build"]`

`drift_alarm()` with a temp HOME, receipt pointing at this worktree, and first-seen backdated 60 minutes: the alarm text ends with `repos.shyamsivakumar/mac-ops.build`.
