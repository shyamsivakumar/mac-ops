# MO-1052 runs

## Red on origin/main

Ticket proof command (grep on tickets.json):

```
tickets.json has no Failure behavior section
```

Fixture proof (`python3 evidence/MO-1052/proof.py <ticket>` on an origin/main extract; the traceback is the missing brief sentence):

```
open, body without the section: None
open, body with the section: None
start, existing ticket without the section: start accepted
start, ticket missing Rollback: start refused: template sections Rollback (missing)
brief has failure instruction: False
Traceback (most recent call last):
  File "evidence/MO-1052/proof.py", line 52, in <module>
    brief.index("Prove each listed case") < brief.index("Failure behavior\n"),
ValueError: substring not found
```

## Green on the branch

```
ticket proof command: exit 0
open, body without the section: template section 'Failure behavior' is missing
open, body with the section: None
start, existing ticket without the section: start accepted
start, ticket missing Rollback: start refused: template sections Rollback (missing)
brief has failure instruction: True
prefix before body: True
prefix sha: 1b2040840e8156f90ab3413a49ea9229f06ec245c363af2eb83c8da0ec14dec6
```

Existing open tickets: the line "start, existing ticket without the section" is accepted on both runs, so `ticket start` still works on a body without the section. Opening a NEW ticket without it is refused. A start still refuses other missing sections. The sentence sits in the static prefix; the ticket section stays in the card body. Fixture bodies only, no live opens.
