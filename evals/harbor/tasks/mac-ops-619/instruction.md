# Gatekeep drains the GitHub core quota every hour

Gatekeep spends about 60 GitHub core calls on every 60-second pass: issue comments, commit statuses, compare and recursive tree reads for every open PR, every pass, whether or not anything changed. From 00:46 to 01:06 PT on 2026-11-19 it made about 1190 of the 1990 gateway calls. Each hour it drains core from 5000 to the 1500 floor in about 25 minutes and then skips every pass until the reset (183 skips logged), so gates queue late.

Acceptance: one gatekeep pass on an unchanged board makes at least 75% fewer core calls than today, and the same gates get queued (a dry run before and after shows the same candidates and skips).

## Interface

The tests use these names and signatures, which the change must provide (names only, no behaviour implied):

- `coordinator/bin/coordq`: `constant _base_pins`
- `coordinator/bin/coordq`: `def pinned_base(repo, base)`
- `coordinator/bin/gh_gateway.py`: `def immutable(argv)`

The repository is at `/app`. Make the change there. Do not edit test files.
