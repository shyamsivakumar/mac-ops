# MO-1118 proof runs

## Ticket proof command: owner of a raised mac-ops card
origin/main prints `None` (red); the branch prints `t1j` (green).

## Selftest merged_restart (owner board case now asserts owner t1j)
origin/main: `AssertionError: expected 't1j', got None`
branch: `merged_restart ok`
