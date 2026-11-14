# MO-215 · Overnight T7a: Secret pattern list and redaction

Ticket: https://github.com/shyamsivakumar/mac-ops/issues/183
Spec: overnight runner spec part T7a (spec issue #172, copy in
`~/Code/coordinator/specs/overnight-runner-spec.md`).

## What was built

One redaction function with one pattern list, in the one module
(`coordinator/overnight/overnight`), used before every write under
`.overnight/`:

```
overnight redact --file fixture.txt
overnight redact --text 'GITHUB_TOKEN=ghp_...'
```

The rule (spec section 5, rule 4): the shift's receipts, logs and morning
report must not contain tokens, keys, cookies or `.env` values.

## The decisions

1. **One function, one list, one place.** `redact(text)` is the only
   thing that knows the patterns, and `SECRET_PATTERNS` is the only list
   of them. Every write in the module goes through `write_record` or
   `append_record`, which call `redact`. No writer has to remember the
   rule, so a new writer cannot forget it.
2. **The writes that are covered.** The receipt writer, the shift log
   (both the append and the attended night's rewrite), the policy
   snapshot, the `run/armed` and `run/deadline` markers, the attended
   night's receipts and the morning report. That is every write the
   module makes: `grep` for `write_text` in the module now finds the two
   helpers and nothing else.
3. **The replacement keeps no part of the value and says what it hid.**
   `[REDACTED:github token]`. A record that says what it hid is still a
   record; a record that keeps the value is a leak. A pattern that matched
   part of a line keeps the rest of the line, so
   `GITHUB_TOKEN=[REDACTED:github token]` still says which variable it
   was.
4. **Every pattern is matched against the text as it came in.** The
   spans that match are found in the original text, merged, and the merged
   span is replaced once. An earlier version replaced pattern by pattern
   on the text the previous pattern had already changed, and the
   replacement `[REDACTED:anthropic key]` was itself matched by the
   environment pattern, which left ` key]` behind. Matching the original
   text has no such leak: a replacement is never read again.
5. **The patterns are the spec's four kinds.** Tokens (GitHub, Anthropic,
   OpenAI, Slack, Google, Hugging Face, npm, Stripe, AWS, JWT), keys (a
   PEM private key block, `api_key`, `secret_key`, `client_secret`,
   `password`), cookies (`Cookie:`, `Set-Cookie:`, a session cookie on
   its own) and `.env` values (the value of a `.env` line, and the value
   of an environment variable whose name ends in `TOKEN`, `SECRET`, `KEY`,
   `PASSWORD`, `PASSWD` or `CREDENTIALS`).
6. **The receipt is compared redacted.** The receipt writer compares the
   receipt on disk with the body it would write. Both sides are redacted
   now, so a receipt that changed only because of the redaction is not
   rewritten on every cycle, and a receipt whose body holds a secret is
   written without it.
7. **`overnight redact` writes nothing.** The command is the redaction
   made visible: it reads a fixture (a string, a file or standard input)
   and prints what a record under `.overnight/` would hold. It is how the
   ticket's proof is produced, with the real command.
8. **Nothing else changes.** No merge rule, no push rule, no slot cap, no
   Ascend rule, no approval dialog handling. The pattern list is a list
   of regular expressions; it never reads a file and never runs a
   command.

## The proof

The real command, on a fixture that holds a fake key. No new unit test
files were written, per the ticket.

Run 1, the fixture:

```
$ cat "$TMPDIR/mo215-fixture.txt"
The builder ran with GITHUB_TOKEN=ghp_EXAMPLEEXAMPLEEXAMPLEEXAMPLEEXAMPLEE
aws key AKIAEXAMPLEEXAMPLEEX
openai key sk-EXAMPLEEXAMPLEEXAMPLEEXAMPLEEXAMPLEE
cookie: session=9f8a7b6c5d4e3f21; path=/
authorization: Bearer abcdefghijklmnopqrstuvwxyz.1234567890
DATABASE_URL=postgres://exam:passwor@db.example.com:5432/app
ANTHROPIC_API_KEY=sk-ant-EXAMPLEEXAMPLEEXAMPLEEXAMPLEEXAM
A normal line with no secret in it.
```

Run 2, the real command:

```
$ python3 coordinator/overnight/overnight redact --file "$TMPDIR/mo215-fixture.txt"
The builder ran with GITHUB_TOKEN=[REDACTED:github token]
aws key [REDACTED:aws key]
openai key [REDACTED:openai key]
cookie: [REDACTED:cookie]; path=/
authorization: [REDACTED:authorization header]
DATABASE_URL=[REDACTED:.env value]
ANTHROPIC_API_KEY=[REDACTED:anthropic key]
A normal line with no secret in it.
```

The fake key does not come out, and the line that carried it still says
which variable it was.

Run 3, the write path. A fixture receipt under a temporary overnight
root carries the fake key in its `Stopped because` line, and the real
report command writes the morning report under that root:

```
$ python3 coordinator/overnight/overnight report --root "$FIX" --date 2026-11-14
overnight: wrote .../mo215-fix/receipts/morning-2026-11-14.md

$ grep -n "REDACTED\|ghp_" .../mo215-fix/receipts/morning-2026-11-14.md
15:- MO-999 (#999) — Fixture ticket whose pull request body carries a fake key. Stopped: the builder printed GITHUB_TOKEN=[REDACTED:github token] while it worked. Next: the builder removes the key from the pull request body.
```

Run 4, no file the command wrote holds the key. The hand-made fixture
receipt is removed and the whole root is searched:

```
$ rm "$FIX/receipts/MO-999.md"
$ grep -rn "ghp_EXAMPLEEXAMPLEEXAMPLEEXAMPLE" "$FIX"
grep exit=1 (1 means no match)

$ find "$FIX" -type f
.../mo215-fix/receipts/morning-2026-11-14.md
```

## Checks

- `python3 scripts/mac_ops_fast_check.py` -> passed.
- `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` -> passed
  (the full local check per `README.md`, "Check a task").
