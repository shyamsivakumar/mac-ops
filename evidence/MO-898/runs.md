# MO-898 runs

Proof command:
python3 -c "import json; v=json.load(open('coordinator/pi/settings.json')).get('defaultTools'); assert v == ['+codemode'], v"

## Before (origin/main)

AssertionError: None (exit 1)

## After (branch)

exit 0

## Source vs live key comparison (key names only)

Source `coordinator/pi/settings.json` vs live `~/.pi/agent-coordinator/settings.json`:
- keys only in one file: none
- keys present in both with differing values: none

Before the change the only differing key was `defaultTools`.
