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

## After the coordinator review: per-repo proofOnOpen and checkout

Fixture f is a numbered `1. Proof command:` line. The last case is an SRW-shaped open run from /tmp with the flag off. Temp COORDQ_DIR and COORD_JOURNAL_DIR stayed empty.
```
== a (mac-ops, flag on, --repo-dir)
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1190", "title": "MO-1190 \u00b7 zz", "labels": ["stage:hold", "priority:3", "type:standard"], "proof": "red", "dryRun": true}
exit 0
== b (mac-ops, flag on, --repo-dir)
refused: proof passes on main: nothing to build
exit 2
== c (mac-ops, flag on, --repo-dir)
refused: proof is unresolved on main (exit 1, signature matched: False): ## Proof run: red 51a34824ba32ed37b497d2fb4c5bc7d2d7227863

```sh
echo "some other error" >&2; exit 1
```

```
some other error

```

{"state": "unresolved", "exit": 1, "matched": false, "ref": "51a34824ba32ed37b497d2fb4c5bc7d2d7227863"}

exit 2
== d (mac-ops, flag on, --repo-dir)
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1190", "title": "MO-1190 \u00b7 zz", "labels": ["stage:hold", "priority:3", "type:standard"], "proof": "prose", "dryRun": true}
exit 0
== e (mac-ops, flag on, --repo-dir)
refused: a behavior ticket needs an `Expected red signature:` line under its proof command, a regex the proof's output must match on main, for example `Expected red signature: AttributeError: .*repo_dir`
exit 2
== f (mac-ops, flag on, --repo-dir)
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1190", "title": "MO-1190 \u00b7 zz", "labels": ["stage:hold", "priority:3", "type:standard"], "proof": "red", "dryRun": true}
exit 0
== SRW-shaped open from another cwd, flag off, Expected on main: style body
{"repo": "shyamsivakumar/strategy-replay-workbench", "key": "SRW-1407", "title": "SRW-1407 \u00b7 zz", "labels": ["stage:hold", "priority:3", "type:standard"], "proof": "unchecked", "dryRun": true}
exit 0
```
