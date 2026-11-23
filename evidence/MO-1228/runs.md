# MO-1228 runs

Proof command (from the ticket):

    python3 -c "import runpy, json, pathlib; s=runpy.run_path('scripts/install_deny_rules.py', run_name='proof'); r=s['claude_rules'](json.load(open('runtime/agents/deny-rules.json')), pathlib.Path.home())['ask']; assert 'Bash(gh pr merge:*)' in r and 'Bash(git push:*)' in r, r"

On origin/main (9217dab5): exit 1, AssertionError, ask list ends with
`Bash(git push origin main:*)`, `Bash(git push origin master:*)`.

On the branch: exit 0.

Installer dry run against a temp HOME (`install_deny_rules.py --root <tmp> --dry-run install`): ask_entries 0 -> 22 on main, 0 -> 24 on the branch; deny_entries 0 -> 24 on both. The real ~/.claude/settings.json was not touched.

Entry comparison of claude_rules, main vs branch, temp HOME:

    deny unchanged: True
    ask added: ['Bash(gh pr merge:*)', 'Bash(git push:*)']
    ask removed: []
    allow key present: False

Extended case (tests/test_install_deny_rules.py, test_claude_list_splits_ask_and_deny_and_covers_token_files): two assertIn lines for the new ask entries.
