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

## The follow-up

Pull request #268 merged at 06:26 PT with the first version of this
part. The in-session review round on that branch found two blocking
defects (a receipt that was redacted twice, and a pattern list that
missed common secret shapes), and the coordinator merged the pull request
before the fixes landed. So the fixes are in their own pull request, on
top of the merged part, and this file is the evidence for both.

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
   module makes: `grep write_text coordinator/overnight/overnight` now
   finds the two helpers and nothing else.
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
5. **The redaction of a text is the same text.** Every value group starts
   with `(?!\[REDACTED:)`, so a redacted value is not redacted a second
   time. Without that, the receipt writer redacted the body, compared it
   with the receipt on disk, and then wrote it through the helper, which
   redacted it again: `password: [REDACTED:secret field] field]`. The
   receipt was rewritten on every cycle and the file on disk never
   matched the body. The receipt writer now writes the redacted body
   once, and the second cycle writes nothing.
6. **The patterns are the spec's four kinds.** Tokens (GitHub, GitLab,
   Anthropic, OpenAI, Slack, Google, Hugging Face, npm, Stripe, AWS,
   JWT), keys (a PEM private key block, including one that was cut
   short, `api_key`, `secret_key`, `client_secret`, `password`), cookies
   (`Cookie:`, `Set-Cookie:`, a session cookie on its own) and `.env`
   values (a `.env` line, and an environment variable whose name ends in
   `TOKEN`, `SECRET`, `KEY`, `PASSWORD`, `PASSWD`, `PASSPHRASE` or
   `CREDENTIALS`).
7. **The patterns leave prose alone.** `STATE=merged`,
   `session = 3 of 5` and a heading that says `Secret:` are records, not
   secrets, and they stay readable. A `.env` value has to be a whole
   line, a session cookie has to sit in a cookie context and be long
   enough to be a token, and a name that is a secret word has to be
   followed by `=` before it counts.
8. **The receipt is compared redacted.** The receipt writer compares the
   receipt on disk with the body it would write. Both sides are redacted
   now, so a receipt that changed only because of the redaction is not
   rewritten on every cycle, and a receipt whose body holds a secret is
   written without it.
9. **`overnight redact` writes nothing.** The command is the redaction
   made visible: it reads a fixture (a string, a file or standard input)
   and prints what a record under `.overnight/` would hold. It is how the
   ticket's proof is produced, with the real command.
10. **Nothing else changes.** No merge rule, no push rule, no slot cap,
    no Ascend rule, no approval dialog handling. The pattern list is a
    list of regular expressions; it never reads a file and never runs a
    command.

## The proof

The real command, on a fixture that holds fake keys. No new unit test
files were written, per the ticket.

Run 1, the fixture:

```
$ cat "$TMPDIR/mo215-fixture.txt"
The builder ran with GITHUB_TOKEN=ghp_AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHH1234
aws key AKIAIOSFODNN7EXAMPLE
openai key sk-abcdefghijklmnopqrstuvwxyz0123456789
cookie: session=9f8a7b6c5d4e3f21; path=/
authorization: Bearer abcdefghijklmnopqrstuvwxyz.1234567890
DATABASE_URL=postgres://user:hunter2@db.example.com:5432/app
ANTHROPIC_API_KEY=sk-ant-abcdefghijklmnopqrstuvwxyz123456
{"api_key": "abcd1234efgh"}
aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789
The builder ran with OPENAI_API_KEY=notaprefixedkey123
password="my secret phrase"
redis://:p4ssw0rd@host
A normal line with no secret in it.
STATE=merged
session = 3 of 5
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
{"api_key": [REDACTED:secret field]}
aws_secret_access_key=[REDACTED:environment secret]
[REDACTED:openai key]
The builder ran with OPENAI_API_KEY=[REDACTED:environment secret]
password=[REDACTED:secret field]
redis://:[REDACTED:url credentials]@host
A normal line with no secret in it.
STATE=merged
session = 3 of 5
```

No fake key comes out, and the last two lines show that a record which
holds no secret stays readable.

Run 3, the write path. The fixture receipt under a temporary overnight
root:

```
$ cat "$FIX/receipts/MO-999.md"
# MO-999

- Item: Fixture ticket whose pull request body carries a fake key
- Repo: shyamsivakumar/mac-ops
- Ticket: MO-999 (#999)
- State: stuck
- Checks: `python3 scripts/mac_ops_fast_check.py` exit 1
- Gate: FAIL
- Files: none
- Time used: 1 min
- Observed: 1 s
- Stopped because: the builder printed GITHUB_TOKEN=ghp_FAKEfakeFAKEfakeFAKEfake1234 while it worked
- Next: the builder removes the key from the pull request body
```

The real report command writes the morning report under that root:

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
$ grep -rn "ghp_FAKEfakeFAKEfakeFAKEfake1234" "$FIX"
grep exit=1 (1 means no match)

$ find "$FIX" -type f
.../mo215-fix/receipts/morning-2026-11-14.md
```

Run 5, the receipt writer keeps its own rule. The same body is written
three times: the first cycle writes it, the next two write nothing, and
the file on disk holds the redacted body and not a second redaction of
it.

```
$ python3 "$TMPDIR/mo215-receipt.py"
0 wrote
1 unchanged
2 unchanged
--- file ---
# MO-999

- Item: Fixture
- Repo: shyamsivakumar/mac-ops
- Ticket: MO-999 (#999)
- State: stuck
- Gate: FAIL
- Time used: 1 min
- Observed: 1 s
- Stopped because: the builder printed GITHUB_TOKEN=[REDACTED:github token]
- Next: fix it
```

## Checks

- `python3 scripts/mac_ops_fast_check.py` -> passed.
- `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` -> passed
  (the full local check per `README.md`, "Check a task").
