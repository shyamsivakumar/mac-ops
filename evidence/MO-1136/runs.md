## Proof run: red 3da3cdbfbdbf536eaf3199bc7f48549b8b0a8151

```sh
test -f coordinator/rules/answers.js || { echo "MISSING coordinator/rules/answers.js"; exit 1; }
python3 -m unittest tests.test_alarm_panel 2>&1 | tail -5
python3 -c "import install_coordinator as i,pathlib;h=pathlib.Path('/h');c=pathlib.Path('.').resolve();t=[str(x[1]) for x in i.plan(c,h)];assert '/h/.coordinator/answers.js' in t and '/h/.config/herdr-app/mods/coordinator/answers.js' in t,t;print('answers ok')"
```

```
MISSING coordinator/rules/answers.js

```

{"state": "red", "exit": 1, "matched": true, "ref": "3da3cdbfbdbf536eaf3199bc7f48549b8b0a8151"}
## Proof run: green a0137ad7e0f02fee192a65c2536862aed045a1f0

```sh
test -f coordinator/rules/answers.js || { echo "MISSING coordinator/rules/answers.js"; exit 1; }
python3 -m unittest tests.test_alarm_panel 2>&1 | tail -5
python3 -c "import install_coordinator as i,pathlib;h=pathlib.Path('/h');c=pathlib.Path('.').resolve();t=[str(x[1]) for x in i.plan(c,h)];assert '/h/.coordinator/answers.js' in t and '/h/.config/herdr-app/mods/coordinator/answers.js' in t,t;print('answers ok')"
```

```
----------------------------------------------------------------------
Ran 8 tests in 0.838s

OK
alarms: factory-watchdog|gatekeep failing (last exit code 1) quiet for 4 hours
answers ok

```

{"state": "green", "exit": 0, "matched": null, "ref": "a0137ad7e0f02fee192a65c2536862aed045a1f0"}
