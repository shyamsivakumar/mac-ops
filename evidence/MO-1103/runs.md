# MO-1103 runs

Proof command: `python3 scripts/settle_finished.py --dry-run`. It reads the live T3
(`t3_thread_list`, `t3_project_list`), the dispatch receipts, the journal and
`gh issue list`. It settles nothing in the default mode; `--apply` was not run.

## origin/main (red)

```text
/Applications/Xcode.app/Contents/Developer/usr/bin/python3: can't open file '/private/tmp/claude-501/-Users-shyamsivakumar-Code/c283b00e-e8c8-422f-9aa1-eb7c969bb5ce/scratchpad/v2/mo1099-main/scripts/settle_finished.py': [Errno 2] No such file or directory
```

## Branch, live dry run at 19:2x on 2026-11-27 (green)

First run, 322 completed unsettled threads (T3 total was 322 at that time):

```text
dry run: 322 completed unsettled threads
  settle:  144 ticket issue closed
  settle:   54 gate verdict recorded
  skip:    124 work not finished
  sample: a5a53dd936b0 'MO-PR review #1038 c1b8dad1' (gate verdict recorded)
  sample: 2a2e0ff93e21 'MO-PR review #1037 649f0fba' (gate verdict recorded)
  sample: 94e277a26597 'MO-PR review #1038 169fabd5' (gate verdict recorded)
  sample: 1f6e7546ea5d 'MO-PR review #989 e26e5089' (gate verdict recorded)
  sample: 1997891ffd28 'MO-PR review #974 a819703a' (gate verdict recorded)
  sample: c7bec4980814 'MO-PR review #992 c9a8b8b5' (gate verdict recorded)
  sample: 129cc5614398 'MO-776 review #1003 52a00a8c' (gate verdict recorded)
  sample: cc130ae6c85c 'MO-PR review #973 9c1e42de' (gate verdict recorded)
  sample: 148ee42304c0 'MO-PR review #976 6d9398e0' (gate verdict recorded)
  sample: 2a5a512133ec 'MO-776 review #1003 9aa49cd6' (gate verdict recorded)
```

Later run from the committed script. Another session settled about 230 threads in
between (T3 now reports 93 completed unsettled and 11687 settled), so the counts fell:

```text
dry run: 93 completed unsettled threads
  settle:   21 gate verdict recorded
  settle:    1 ticket issue closed
  skip:     71 work not finished
  sample: 1b41ee12acc7 'LMW-90 · Add manual MCP tool-description snapshots' (ticket issue closed)
  sample: a5a53dd936b0 'MO-PR review #1038 c1b8dad1' (gate verdict recorded)
  sample: 2a2e0ff93e21 'MO-PR review #1037 649f0fba' (gate verdict recorded)
  sample: 94e277a26597 'MO-PR review #1038 169fabd5' (gate verdict recorded)
  sample: 1f6e7546ea5d 'MO-PR review #989 e26e5089' (gate verdict recorded)
  sample: 1997891ffd28 'MO-PR review #974 a819703a' (gate verdict recorded)
  sample: c7bec4980814 'MO-PR review #992 c9a8b8b5' (gate verdict recorded)
  sample: 129cc5614398 'MO-776 review #1003 52a00a8c' (gate verdict recorded)
  sample: cc130ae6c85c 'MO-PR review #973 9c1e42de' (gate verdict recorded)
  sample: 148ee42304c0 'MO-PR review #976 6d9398e0' (gate verdict recorded)
```

Skip rules (pinned, snoozed, running or waiting, blocked, Ascend or slash-eureka) matched
no thread in either run. No pull request reason matched: T3 records every thread PR as
open in these threads. The first run used the same code, run read-only from the
checkout before the script was copied into this worktree.
