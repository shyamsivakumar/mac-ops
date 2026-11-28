## Proof run: red afebc91fce07dfe484d569025639e1b9ef5b5cee

```sh
python3 -c "import sys,importlib.machinery as m,importlib.util as u;sys.path.insert(0,'coordinator/bin');l=m.SourceFileLoader('t','coordinator/bin/ticket');t=u.module_from_spec(u.spec_from_loader('t',l));l.exec_module(t);p=t.brief_prefix();ok='Runtime code lines:' in p and 'Proof lines:' in p;print(ok);sys.exit(not ok)" && grep -q 'Proof lines:' coordinator/config/AGENT-RULES.md
```

```
False

```

{"state": "red", "exit": 1, "matched": true, "ref": "afebc91fce07dfe484d569025639e1b9ef5b5cee"}
## Proof run: green dc33b94b5a1179a4897d976c76dba5b4aabf171b

```sh
python3 -c "import sys,importlib.machinery as m,importlib.util as u;sys.path.insert(0,'coordinator/bin');l=m.SourceFileLoader('t','coordinator/bin/ticket');t=u.module_from_spec(u.spec_from_loader('t',l));l.exec_module(t);p=t.brief_prefix();ok='Runtime code lines:' in p and 'Proof lines:' in p;print(ok);sys.exit(not ok)" && grep -q 'Proof lines:' coordinator/config/AGENT-RULES.md
```

```
True

```

{"state": "green", "exit": 0, "matched": null, "ref": "dc33b94b5a1179a4897d976c76dba5b4aabf171b"}
