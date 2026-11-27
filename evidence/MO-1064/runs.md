# Runs for #1064

Proof command (the ticket's, with the module directory as an argument):

    python3 -c "
    import sys
    sys.path.insert(0, '<dir>')
    import close_check as c
    t = c.scope_tokens(
        '## Scope and non-goals\n\nIn:\n\n'
        '- `.claude/hooks/config.json`: x\n\nOut: none.\n')
    print(t)
    sys.exit(0 if '.claude/hooks/config.json' in t else 1)"

## Red on origin/main c1224b58

    {'claude/hooks/config.json'}
    exit 1

## Green on this branch

    {'.claude/hooks/config.json'}
    exit 0

## Failure behavior cases on this branch

    # main: '/coordinator/x.py'; neither matches a repo path
    './coordinator/x.py'              -> {'./coordinator/x.py'}
    'e.g. foo, 3.9 and (a/b.py).'     -> {'a/b.py'}
    'In Foo.swift.'                   -> {'Foo.swift'}
    exclusion_tokens('.claude/a.json and .env.py.') -> {'.env.py', '.claude/a.json'}

## Existing tests

`python3 -m unittest tests.test_close_check`: Ran 100 tests, OK (includes the new
`test_a_dotfile_path_keeps_its_leading_dot`).
