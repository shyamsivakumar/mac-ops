# The cut-off pull request list is not an empty list

GitHub's `gh pr list` returns at most 100 pull requests of a repository.
A list that stops at the limit is missing the ones past it, so a ticket
whose pull request is one of those would look like it has none. The
health check must not classify a ticket from such a list.

The proof hands the check the inputs, so it starts no process and reads
no board:

    python3 - <<'PY'
    import importlib.machinery, importlib.util, json
    from pathlib import Path
    loader = importlib.machinery.SourceFileLoader("fo", "coordinator/overnight/overnight")
    spec = importlib.util.spec_from_loader(loader.name, loader)
    m = importlib.util.module_from_spec(spec); loader.exec_module(m)
    m.run = lambda argv, t, d: json.dumps([{"number": 7, "title": "t", "comments": [
        {"body": "Starting b attempt 1"},
        {"body": "Starting b attempt 2"},
        {"body": "Starting b attempt 3"}]}])
    m.read_decisions = lambda: (Path("/tmp/x.md"), [])
    m.read_pull_requests = lambda repo, d: ([], True)   # the list was cut off
    ran, found = m.check_attempts([{"repo": "o/r", "number": 7, "key": "R-7"}], [("o/r", "")], 0)
    print("RAN:", ran); print("FOUND:", json.dumps(found, indent=1))
    m.read_pull_requests = lambda repo, d: ([], False)  # the list is whole
    ran, found = m.check_attempts([{"repo": "o/r", "number": 7, "key": "R-7"}], [("o/r", "")], 0)
    print("RAN2:", ran); print("FOUND2:", json.dumps(found, indent=1))
    PY

The output:

    RAN: ['the open issues of o/r with their comments', 'the open pull requests of o/r were cut off at 100']
    FOUND: [
     {
      "check": "attempts",
      "subject": "o/r",
      "detail": "the open pull request list was cut off at 100, so the tickets of this repository are not classified: a pull request past the limit would look like none",
      "action": "raise the pull request limit and run the check again"
     }
    ]
    RAN2: ['the open issues of o/r with their comments', 'the open pull requests of o/r']
    FOUND2: [
     {
      "check": "attempts",
      "subject": "o/r#7",
      "detail": "R-7 was started 3 times and has no open pull request",
      "action": "read the last builder report, then reword the brief or park the ticket and open a re-spec ticket"
     }
    ]

The first run says the list was cut off and classifies no ticket: no
ticket is reported as having no open pull request. The second run, with
a whole list, classifies the ticket and reports it. The same rule is in
the `cycle-health` eval of `coordinator/overnight/selftest.py`.

The live cycle on this head is `cycle-live-cut.md`: all four checks ran
against the live queue and the live board.
