# MO-769 proof runs

The ticket's proof body fails the template check on main and on the branch (it has only one section), so the fixtures use a full-template body with the proof block varied. Fixtures: a = fails with the named signature, b = passes on main, c = fails with the wrong error, d = prose, e = no signature. All runs use --dry-run with temp COORDQ_DIR and COORD_JOURNAL_DIR; the temp dirs stayed empty.

## Before: origin/main (475627f9)
```
== a
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1189", "title": "MO-1189 \u00b7 zz", "labels": ["stage:hold", "priority:3", "type:standard"], "dryRun": true}
exit 0
== b
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1189", "title": "MO-1189 \u00b7 zz", "labels": ["stage:hold", "priority:3", "type:standard"], "dryRun": true}
exit 0
== c
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1189", "title": "MO-1189 \u00b7 zz", "labels": ["stage:hold", "priority:3", "type:standard"], "dryRun": true}
exit 0
== d
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1189", "title": "MO-1189 \u00b7 zz", "labels": ["stage:hold", "priority:3", "type:standard"], "dryRun": true}
exit 0
== e
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1189", "title": "MO-1189 \u00b7 zz", "labels": ["stage:hold", "priority:3", "type:standard"], "dryRun": true}
exit 0
```

## After: branch
```
== a
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1189", "title": "MO-1189 \u00b7 zz", "labels": ["stage:hold", "priority:3", "type:standard"], "proof": "red", "dryRun": true}
exit 0
== b
refused: proof passes on main: nothing to build
exit 2
== c
refused: proof is unresolved on main (exit 1, signature matched: False): ## Proof run: red 475627f97492222c355b850bfb9a6682d0c4508c

```sh
echo "some other error" >&2; exit 1
```

```
some other error

```

{"state": "unresolved", "exit": 1, "matched": false, "ref": "475627f97492222c355b850bfb9a6682d0c4508c"}

exit 2
== d
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1189", "title": "MO-1189 \u00b7 zz", "labels": ["stage:hold", "priority:3", "type:standard"], "proof": "prose", "dryRun": true}
exit 0
== e
refused: a behavior ticket needs an `Expected red signature:` line under its proof command
exit 2
```
