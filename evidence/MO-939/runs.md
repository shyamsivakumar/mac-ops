# MO-939 runs

## Ticket proof on origin/main (red)
AttributeError: module 'inbox_poll' has no attribute 'poll_ci'

## Ticket proof on the head (green)
exit 0

## inbox eval (coordinator/overnight/selftest.py), run flat from a copy of coordinator/bin/*.py + coordinator/overnight/*.py
head: inbox eval ok
origin/main plus the new selftest: AttributeError: module 'inbox_poll' has no attribute 'poll_ci'

## Default fetch_status, read only, temp COORD_INBOX_DIR (contexts and states only)
shyamsivakumar/strategy-replay-workbench [('srw/agent-check', 'success'), ('srw-telegram-paper - srw-learner', 'success')]
shyamsivakumar/mac-ops []
stderr: shyamsivakumar/mac-ops: no Mac-published status
poll_ci rows: 1 -> [('ci_main', 'batch', {"context": "srw/agent-check", "state": "success"})]
