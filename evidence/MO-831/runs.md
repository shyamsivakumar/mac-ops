# MO-831 runs

Each run uses a temp HOME and a throwaway clone with branch main and origin/main at the commit under test (install.py requires that). Code commit: d8415c65b77cf4a5ff18e2609435c7e079ddafd6

## Ticket proof command, before (origin/main)

```
mkdir -p $HOME/.local/lib/mac-ops && echo '{"host":"m1"}' > $HOME/.local/lib/mac-ops/heavy_hosts.json
python3 install.py install --host-role runner --no-start && cat $HOME/.local/lib/mac-ops/*/heavy_hosts.json
echo; echo "--- LaunchAgents:"; ls $HOME/Library/LaunchAgents 2>&1
echo "--- flat layout:"; ls -A $HOME/.local/lib/mac-ops | grep -v "^[0-9a-f]\{20\}$"
echo "--- release:"; ls -l $HOME/.local/lib/mac-ops/*/
cat $HOME/.local/state/mac-ops/installation.json; echo
```

```
usage: install.py [-h] [--migrate] [--no-start] [--dry-run]
                  [--release RELEASE] [--source-commit SOURCE_COMMIT]
                  [{install,uninstall,status,finalize-migration,archive-legacy,rollback}]
install.py: error: unrecognized arguments: --host-role runner

--- LaunchAgents:
ls: <tmp>.3oJ6h6sMr7/Library/LaunchAgents: No such file or directory
--- flat layout:
heavy_hosts.json
--- release:
ls: <tmp>.3oJ6h6sMr7/.local/lib/mac-ops/*/: No such file or directory
cat: <tmp>.3oJ6h6sMr7/.local/state/mac-ops/installation.json: No such file or directory

```

## Ticket proof command, after (branch)

```
Installed heavy in <tmp>.ZqxTwanP6f/.local/bin/heavy
{"host":"m1"}

--- LaunchAgents:
ls: <tmp>.ZqxTwanP6f/Library/LaunchAgents: No such file or directory
--- flat layout:
heavy_hosts.json
--- release:
total 584
-rw-------@ 1 shyamsivakumar  staff   16173 Nov 21 11:33 agent_heavy_wait_pause.py
-rw-------@ 1 shyamsivakumar  staff     689 Nov 21 11:33 board_governor.json
-rw-------@ 1 shyamsivakumar  staff   70609 Nov 21 11:33 board_governor.py
-rw-------@ 1 shyamsivakumar  staff   30666 Nov 21 11:33 board_resources.py
-rw-------@ 1 shyamsivakumar  staff   19655 Nov 21 11:33 board_restart.py
-rw-------@ 1 shyamsivakumar  staff      14 Nov 21 11:33 heavy_hosts.json
-rw-------@ 1 shyamsivakumar  staff  135710 Nov 21 11:33 heavy.py
-rwx------@ 1 shyamsivakumar  staff     439 Nov 21 11:33 heavy.sh
-rw-------@ 1 shyamsivakumar  staff    1322 Nov 21 11:33 load_backstop.py
{"checkout": "<clone>", "release": "<tmp>.ZqxTwanP6f/.local/lib/mac-ops/6e29c1db89fbc309b2fe", "installed_at": 1795278819.6183748, "source_commit": "d8415c65b77cf4a5ff18e2609435c7e079ddafd6", "host_role": "runner"}
```

## Flat layout kept, wrapper archived not deleted, rollback stays runner, dry-run

```
# script
L=$HOME/.local/lib/mac-ops; mkdir -p $L $HOME/.local/bin
echo '{"host":"m1"}' > $L/heavy_hosts.json; chmod 600 $L/heavy_hosts.json
echo old > $L/heavy.py; echo bak > $L/heavy.py.bak-20261120-mo629; echo b2 > $L/heavy.py.bak-1072
printf '#!/bin/sh\nexec /usr/bin/python3 -I %s/heavy.py "$@"\n' $L > $HOME/.local/bin/heavy; chmod 755 $HOME/.local/bin/heavy
(cd $L && shasum -a 256 heavy_hosts.json heavy.py heavy.py.bak-*) > $HOME/before.sha
python3 install.py install --host-role runner --no-start
(cd $L && shasum -a 256 heavy_hosts.json heavy.py heavy.py.bak-*) > $HOME/after.sha
cmp $HOME/before.sha $HOME/after.sha && echo "FLAT FILES UNCHANGED"; cat $HOME/after.sha
echo "--- bin:"; cat $HOME/.local/bin/heavy; echo "--- archived:"; ls $HOME/.local/state/mac-ops/install-backups
echo "--- release hosts mode:"; stat -f '%Lp %N' $L/*/heavy_hosts.json; cat $L/*/heavy_hosts.json; echo
echo "--- LaunchAgents:"; ls $HOME/Library/LaunchAgents 2>&1 | head -2
REL=$(ls -d $L/*/); python3 install.py rollback --release ${REL%/} --source-commit abc --no-start; grep -o '"host_role": "[a-z]*"' $HOME/.local/state/mac-ops/installation.json; ls $HOME/Library/LaunchAgents 2>&1 | head -1
echo "--- dry-run:"; python3 install.py install --host-role runner --dry-run | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["host_role"], d["carry_host_config"], d["services"])'

# output
Installed heavy in <tmp>.1mJE631Dqo/.local/bin/heavy
FLAT FILES UNCHANGED
31ac5307c11cc30d419ee2ddb542a40e5f496f4eb85148ecbe151952625094cf  heavy_hosts.json
01d09d19c2139a46aebfb577780d123d7396e97201bc7ead210a2ebff8239dee  heavy.py
65f653bec9d0d1be6a363cb500e002c0165efdc82ed058f38b786f05dd19d87f  heavy.py.bak-1072
810981d20c1093bf265a874db3f6e19e43011ae3d6aba942adac666ceb3297cc  heavy.py.bak-20261120-mo629
--- bin:
#!/bin/sh
exec /usr/bin/python3 -I '<tmp>.1mJE631Dqo/.local/lib/mac-ops/6e29c1db89fbc309b2fe/heavy.py' "$@"
--- archived:
heavy
--- release hosts mode:
600 <tmp>.1mJE631Dqo/.local/lib/mac-ops/6e29c1db89fbc309b2fe/heavy_hosts.json
{"host":"m1"}

--- LaunchAgents:
ls: <tmp>.1mJE631Dqo/Library/LaunchAgents: No such file or directory
Rolled back heavy to /private<tmp>.1mJE631Dqo/.local/lib/mac-ops/6e29c1db89fbc309b2fe (abc)
"host_role": "runner"
ls: <tmp>.1mJE631Dqo/Library/LaunchAgents: No such file or directory
--- dry-run:
runner <tmp>.1mJE631Dqo/.local/lib/mac-ops/heavy_hosts.json {}
```

## Default role unchanged (full still writes both plists)

```
com.shyam.board-governor.plist
com.shyam.load-backstop.plist
full ['com.shyam.load-backstop', 'com.shyam.board-governor']
```

## Read-only dry run on the M1 (branch exported with git archive to a temp dir, no install)

```
{
  "action": "install",
  "paths": {
    "release": "/Users/shyamsivakumar/.local/lib/mac-ops/6e29c1db89fbc309b2fe",
    "state": "/Users/shyamsivakumar/.local/state/mac-ops",
    "bin": "/Users/shyamsivakumar/.local/bin/heavy",
    "agents": "/Users/shyamsivakumar/Library/LaunchAgents",
    "legacy": "/Users/shyamsivakumar/.multica-codex"
  },
  "host_role": "runner",
  "carry_host_config": "/Users/shyamsivakumar/.local/lib/mac-ops/heavy_hosts.json",
  "services": {},
  "brew_dependencies": []
}

5
com.shyam.mac-ops-capacity.plist
com.shyam.mo-weekly.plist
com.shyam.tmp-sweep.plist
com.shyam.tnr27-acceptance.plist
com.shyamsivakumar.amp-runner-m1.plist
```

The M1 has no ~/.multica-codex, no installation.json, and a 0700 ~/.local/state/mac-ops, so none of install()'s preflight checks would block it.
Note: heavy.py on main reads board_governor.json next to itself (CONFIG_NAME); it does not read heavy_hosts.json. The file is carried into the release as the ticket asks, and stays at its flat path too.
