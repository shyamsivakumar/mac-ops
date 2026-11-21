# MO-763 runs

Adapted: the ticket's proof uses label stage:hold, which the live labels do not list, so the runs use stage:todo. Temp COORDQ_DIR and COORD_JOURNAL_DIR.

## Ticket proof, origin/main (red)
```
{"repo": "shyamsivakumar/mac-ops", "key": "MO-1184", "title": "MO-1184 \u00b7 zz", "labels": ["stage:todo", "priority:3", "type:standard"], "dryRun": true}
exit 0
```

## Ticket proof, branch (green)
```
exit 2
```

## check_body on fixture bodies
```
passes (3 code files + evidence): None
oversized (5 files): Scope In names 5 code files, the cap is 3
oversized (400 lines): Size names 400 code lines, the cap is 150
no proof: a behavior ticket needs a `Proof command:` block (docs and config tickets say `Proof command: none (prose)`)
docs, prose: None
type:large 5 files: None
```

## Open stage:todo bodies (check_body, no labels)
762, 758, 742 pass; 740 and 708 have no Proof command line; 631 has no Goal and why section (old format, would be refused at open).

## key-mint selftest case (run alone, no heavy)
origin/main code with the new selftest: AssertionError: a body without a proof line was opened
branch: key_mint ok
