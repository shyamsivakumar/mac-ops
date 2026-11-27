# MO-1021 proof

Command: `python3 evidence/MO-1021/prefix.py coordinator/bin/ticket`.

It byte-compares dry-run briefs for tickets 1020 and 1031 (no live start). Each
comes from `ticket start <repo>#<n> --dry-run --print-brief`.

For origin/main, pass that checkout's `coordinator/bin/ticket`.

## origin/main (red)

```text
brief bytes 2933 3032 common prefix bytes 59
sha256 of common prefix bbd3573e6671afaed5de1104ef4d93be5f4b10bc6af87361c7577829cb065b10
first line 1020: b'Ticket: https://github.com/shyamsivakumar/mac-ops/issues/1020'
first line 1031: b'Ticket: https://github.com/shyamsivakumar/mac-ops/issues/1031'
```

The common prefix stops inside the ticket URL.

## head (green)

<!-- markdownlint-disable MD013 -->

```text
brief bytes 2933 3032 common prefix bytes 733
sha256 of common prefix 51a1ec8984700e8a1edae8007b4b37c97b098688dc8dfb4579eac3561f667164
first line 1020: b'When a turn ends by asking Shyam a question, put the question on one line, then 2 to 4 opt'
first line 1031: b'When a turn ends by asking Shyam a question, put the question on one line, then 2 to 4 opt'
printed prefix sha 1020/1031: ['44b6cd4ce68a30e483973517e677a6fcfbcc883d7dfb79f1a9ed17575d22152b', '44b6cd4ce68a30e483973517e677a6fcfbcc883d7dfb79f1a9ed17575d22152b']
static prefix length 672 sha matches both briefs: True
```

<!-- markdownlint-enable MD013 -->

The 672-byte static prefix (answer format plus size rule) is identical. The dry
run prints its sha256, journaled as `promptPrefixSha` on `ticket_started`. Brief
sizes are unchanged (2933 and 3032 bytes), so only the order moved.

The arm-dependent severity bar (#997) follows the static prefix. Arms and tickets
therefore share the prefix.
