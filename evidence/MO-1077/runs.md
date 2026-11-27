# Proof runs for #1077

## Red on origin/main

```
$ python3 coordinator/bin/coordq logs --help
coordq: error: argument cmd: invalid choice: 'logs' (choose from 'start', 'create', 'list', 'drop', 'status', 'spend', 'decision', 'actrate', 'wait', 'waits', 'dispatch', 'gatekeep', 'gate', 'fix')
exit 2
```

## Green on the head

```
$ python3 coordinator/bin/coordq logs --help
usage: coordq logs [-h] [--since SINCE] [--grep GREP] [--tail TAIL]
                   [source ...]
exit 0
```

## Missing log and redaction (temp COORD_LOOP_DIR, COORDQ_DIR, COORD_JOURNAL_DIR)

The ticks fixture line was `error token=abc123XYZ and Bearer abcdefghijklmnop api_key=zzz1 ghp_abcdefghijklmnopqrstuvwxyz1234`.

```
$ coordq logs ticks dispatch --tail 5
coordq logs: dispatch: cannot read <tmp>/q/dispatch.log: No such file or directory
== ticks (2 of 2 lines) ==
2026-11-27 10:00:00 tick ok
2026-11-27 10:01:00 error [redacted] and [redacted] [redacted] [redacted]
exit 1
```

## Quoted JSON secrets and --tail (second round)

Fixture line: `{"password": "hunter two", "x": 1} {"api_token":"abc123"} token=abc123XYZ Bearer abcdefghijklmnop ghp_abcdefghijklmnopqrstuvwxyz1234`

```
$ coordq logs ticks --tail 5
== ticks (2 of 2 lines) ==
2026-11-27 10:01:00 {"[redacted], "x": 1} {"[redacted]} [redacted] [redacted] [redacted]
plain line ok
exit 0
$ coordq logs ticks --tail 0
coordq logs: --tail 0: use 1 or more
exit 2
$ coordq logs ticks --tail -3
coordq logs: --tail -3: use 1 or more
exit 2
```

## Finding rules on a fixture

```
.github/workflows/ci.yml containing "on: push" -> ['no-github-workflows']
x.py containing subprocess.run("git stash")    -> ['no-git-stash']
x.py containing print("hi")                     -> []
ci.yml outside .github/workflows                -> []
.woodpecker.yml, .woodpecker.yaml, .woodpecker/build.yml -> ['no-woodpecker-workflows']
```
