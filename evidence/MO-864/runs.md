# MO-864 runs

Proof command (saved as a script, same text as the ticket):
```
import runpy; s=runpy.run_path('coordinator/bin/coordq', run_name='proof'); r=s['pr_ticket_refs']('Fix (Refs #855)', 'ok  Refs-example: ' + chr(39) + 'Refs #81' + chr(39) + ' #13 -> False'); assert r == ['855'], r
```

## Red on origin/main (detached worktree)
```
KeyError: 'pr_ticket_refs'
```

## Green on the branch
```
exit 0
```

## Real merged PRs (title and body fetched with gh pr view)
```
#857 [MERGED] 'Read a reference verb only in reference position (Refs #855)'
  new: ['855']  old regex: ['12', '160', '81', '855']
#728 [MERGED] "MO-1141 · The close checklist accepts each repo's own check evidence"
  new: ['727']  old regex: ['727']
#682 [MERGED] 'Gate brief: always ask for the PROVIDES line'
  new: ['675']  old regex: ['675']
#668 [MERGED] 'Lane: trailing spaces no longer break a complete PASS; separate fixes for one ticket are not superseded'
  new: ['667']  old regex: ['667']
```

#728, #682 and #668 have no Refs in the title; each keeps its body Refs.
