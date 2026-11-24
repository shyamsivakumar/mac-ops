# MO-939 runs

## Ticket proof on origin/main (red)
AttributeError: module 'inbox_poll' has no attribute 'poll_ci'
exit 1

## Ticket proof on the head ecdad0a11635cb2e9608948cf5a139300a06f28f (green)
exit 0

## inbox eval, flat copy of coordinator/bin/*.py + coordinator/overnight/*.py
origin/main plus the new selftest (red): AttributeError: module 'inbox_poll' has no attribute 'poll_ci'
exit 1
head (green): inbox eval ok
exit 0

## inbox eval in place, head (green)
inbox eval ok (selftest's own stderr lines omitted)
exit 0

## Default fetch_status, read only, temp COORD_INBOX_DIR (contexts and states only), per_page=100
shyamsivakumar/strategy-replay-workbench total_count 2 [('srw/agent-check', 'success'), ('srw-telegram-paper - srw-learner', 'success')]
shyamsivakumar/mac-ops total_count 0 []
stderr: shyamsivakumar/mac-ops: no Mac-published status
poll_ci rows: 1 -> [('ci_main', 'batch', {"context": "srw/agent-check", "state": "success"})]
