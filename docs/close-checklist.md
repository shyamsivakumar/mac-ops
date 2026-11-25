# The close checklist

`coordinator/bin/close_check.py` answers four items from the merged pull
request and its ticket, and the coordinator closes a ticket only when every
required item passes. A failing item sends the work back to its builder with
the item named, and leaves the ticket open.

```
python3 coordinator/bin/close_check.py --repo shyamsivakumar/mac-ops --pr <n> --issue <n>
```

## The four items

1. **scope** — every file the pull request changes is inside the ticket's
   stated scope.
2. **proof file** — the pull request carries its repository's own check
   evidence. In mac-ops that is a proof file, in strategy-replay-workbench a
   `success` `srw/agent-check` status on the head, elsewhere a
   `Builder check: PASS <head sha>` line in the pull request body.
3. **checks** — every check the mac-ops proof file lists is `passed`.
4. **cost note** — when `evidence/MO-1068/cost-report.md` exists, the pull
   request body carries a cost note. The item is skipped while that report
   does not exist.

## The scope item reads the declaration, not the background

The scope item is the one that fails on a ticket that was written well but
declared badly, so it is worth knowing exactly what it reads.

It reads the ticket's **declaration**: the words after an `In:` marker, and
the section under a heading that declares the scope, such as
`## Scope and non-goals`. Everything else in the ticket is background, and a
file named in the background does not widen the scope. That rule is
deliberate: a builder can edit the ticket body, so a name written anywhere in
it must not be able to authorize a file the ticket never asked for.

The consequence is that a ticket which lists the files it will touch under
`## Context` and then describes only *actions* under `In:` fails the scope
item, even though it did state the files. The fix is to name them in the
declaration:

```markdown
## Scope and non-goals

In:

- Rebase the branch and keep its intent.
- The files the change carries: `coordinator/bin/gh_isolation.py`,
  `coordinator/overnight/overnight`, `scripts/mac_ops_fast_check.py`.
```

A token names a file when it is the file, a directory that holds it, a glob
that matches it, or the file's own name. A directory token such as
`coordinator/` bounds every changed path under it, so a ticket that declares
a directory does not have to list each file.

A name is read whole. The leading part of a longer name is not a token
(`Foo.swift.template` names no `Foo.swift`), and neither is a name inside a
URL (`https://example.org/?file=Foo.swift` names no file in this
repository). A bare name is a token only when its extension is one the
checklist knows: the document and script extensions, plus `swift` for the
board's Apple apps.

Two allowances sit on top of the declaration:

- **Evidence travels.** A file under the ticket's own `evidence/<KEY>/`
  directory is in scope without being named. Another ticket's evidence is
  not.
- **A test follows its source.** A changed test file is in scope when its
  name matches a changed source file the ticket names, so `test_foo.py`
  follows `foo.py`. A test of something else is not part of the change.

An `Out:` marker, an `Out of scope:` heading, or a sentence that forbids a
change excludes what follows it, and an exclusion holds to the end of its
section. A file the ticket excludes fails the item even when the ticket also
names it.

## When the scope item fails

The detail names the files that fell outside. Either the ticket's declaration
is missing them, or the change reached past what the ticket asked for. Read
the ticket first: if the files are named in the background, move them into
the `In:` declaration and re-run the checklist. If they are not named
anywhere, the change is wider than the ticket and belongs in its own ticket.
