# MO-562: pin ruff and mypy, report a missing tool as not run

`TOOL_VERSIONS` in `scripts/mac_ops_fast_check.py` is the one place the tool
versions live (`ruff` 0.14.0, `mypy` 1.18.2). Both tools run only through
`uvx <tool>@<version>`. The mypy check covers the modules in `MYPY_TARGETS`
(today `board_resources.py`, which is clean) with `--follow-imports=silent`, so
it reports on those modules only and adds no failures on existing code.

## With uvx on PATH

`check-proof.md` (run on `d9f7d394`):

```
| ruff F,B | `uvx ruff@0.14.0 check --select F,B ...` | passed | 86 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --follow-imports=silent --ignore-missing-imports board_resources.py` | passed | 1 modules, no issues |
Run result: passed
```

## With uvx removed from PATH

`PATH=/usr/bin:/bin:/usr/sbin:/sbin ~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py --proof evidence/MO-562/demo-no-uvx.md`
exits 1 and `demo-no-uvx.md` records:

```
| ruff F,B | `uvx ruff@0.14.0 check ...` | not run | uvx is not installed |
| mypy | `uvx mypy@1.18.2 ...` | not run | uvx is not installed |
Run result: incomplete
```

## A mypy error fails the check

Pointing `MYPY_TARGETS` at `heavy.py` in a scratch call to `check_mypy()` raised
`18 mypy errors; first: heavy.py:395: error: Incompatible return value type ...`.
`MYPY_TARGETS` was not changed in the repository.

## Left for later

- `heavy.py` has 18 mypy errors, so it is not in `MYPY_TARGETS` yet.
