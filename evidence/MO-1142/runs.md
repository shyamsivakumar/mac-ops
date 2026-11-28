## Proof run: red 7c38f6b2066ad3f2ca46299a2c26cb768e486e25

```sh
python3 - <<'PY'
import collections, json, os, sys
sys.path.insert(0, "scripts/worktree-cleaner")
import cleaner
fixture = "verification/worktree-cleaner/fixtures/last.json"
if not os.path.exists(fixture):
    print("FAIL buckets: fixture missing")
    sys.exit(1)
rows = json.load(open(fixture))["rows"]
got = dict(sorted(collections.Counter(cleaner.categorize(r) for r in rows).items()))
want = {"look": 5, "protected": 6, "prune": 2, "removed": 1, "safe": 1}
print("buckets", got)
if got != want:
    print("FAIL buckets want", want)
    sys.exit(1)
PY
```

```
FAIL buckets: fixture missing

```

{"state": "red", "exit": 1, "matched": true, "ref": "7c38f6b2066ad3f2ca46299a2c26cb768e486e25"}
## Proof run: green 21f16b2caa11c94df3fee8e5e23f7556a71f541c

```sh
python3 - <<'PY'
import collections, json, os, sys
sys.path.insert(0, "scripts/worktree-cleaner")
import cleaner
fixture = "verification/worktree-cleaner/fixtures/last.json"
if not os.path.exists(fixture):
    print("FAIL buckets: fixture missing")
    sys.exit(1)
rows = json.load(open(fixture))["rows"]
got = dict(sorted(collections.Counter(cleaner.categorize(r) for r in rows).items()))
want = {"look": 5, "protected": 6, "prune": 2, "removed": 1, "safe": 1}
print("buckets", got)
if got != want:
    print("FAIL buckets want", want)
    sys.exit(1)
PY
```

```
buckets {'look': 5, 'protected': 6, 'prune': 2, 'removed': 1, 'safe': 1}

```

{"state": "green", "exit": 0, "matched": null, "ref": "21f16b2caa11c94df3fee8e5e23f7556a71f541c"}

## Buckets on the fixture (origin/main cleaner vs this head)

```
row                      before     after     
live-thread-dirty        protected  protected 
open-pr-young            look       protected   <-
open-pr-young-dirty      look       protected   <-
open-pr-a-day-old        look       look      
open-pr-old              look       look      
open-pr-age-unknown      look       look      
pr-not-closed-young      look       look      
dirty-young              look       look      
gone-detached            look       prune       <-
gone-prunable            prune      prune     
gone-locked              protected  protected 
gone-live-thread         protected  protected 
main                     protected  protected 
eligible                 safe       safe      
removed-earlier          removed    removed   
before {'look': 8, 'protected': 4, 'prune': 1, 'removed': 1, 'safe': 1}
after  {'look': 5, 'protected': 6, 'prune': 2, 'removed': 1, 'safe': 1}
```
