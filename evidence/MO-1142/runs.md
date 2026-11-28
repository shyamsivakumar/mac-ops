## Proof run: red ed088e4f8f11984e00a4e3f166980520f6149f64

```sh
python3 - <<'PY'
import collections, json, os, sys
sys.path.insert(0, "scripts/worktree-cleaner")
import cleaner
fixture = "verification/worktree-cleaner/fixtures/last.json"
if not os.path.exists(fixture):
    print("FAIL buckets: fixture missing")
    sys.exit(1)
waive = getattr(cleaner, "waived_reasons", None)
if waive is None:
    print("FAIL buckets: waived_reasons missing")
    sys.exit(1)
rows = json.load(open(fixture))["rows"]
for row in rows:
    row["path"] = row["path"].replace("@T3@", str(cleaner.T3_WORKTREE_ROOT))
    row["reasons"] = waive(row, row["reasons"])
    row["eligible"] = not row["reasons"]
got = dict(sorted(collections.Counter(cleaner.categorize(r) for r in rows).items()))
want = {"look": 10, "protected": 7, "prune": 3, "removed": 1, "safe": 3}
print("buckets", got)
if got != want:
    print("FAIL buckets want", want)
    sys.exit(1)
PY
```

```
FAIL buckets: fixture missing

```

{"state": "red", "exit": 1, "matched": true, "ref": "ed088e4f8f11984e00a4e3f166980520f6149f64"}
## Proof run: green 09c9ed71a948ab803e46844239d7d277de9efc3b

```sh
python3 - <<'PY'
import collections, json, os, sys
sys.path.insert(0, "scripts/worktree-cleaner")
import cleaner
fixture = "verification/worktree-cleaner/fixtures/last.json"
if not os.path.exists(fixture):
    print("FAIL buckets: fixture missing")
    sys.exit(1)
waive = getattr(cleaner, "waived_reasons", None)
if waive is None:
    print("FAIL buckets: waived_reasons missing")
    sys.exit(1)
rows = json.load(open(fixture))["rows"]
for row in rows:
    row["path"] = row["path"].replace("@T3@", str(cleaner.T3_WORKTREE_ROOT))
    row["reasons"] = waive(row, row["reasons"])
    row["eligible"] = not row["reasons"]
got = dict(sorted(collections.Counter(cleaner.categorize(r) for r in rows).items()))
want = {"look": 10, "protected": 7, "prune": 3, "removed": 1, "safe": 3}
print("buckets", got)
if got != want:
    print("FAIL buckets want", want)
    sys.exit(1)
PY
```

```
buckets {'look': 10, 'protected': 7, 'prune': 3, 'removed': 1, 'safe': 3}

```

{"state": "green", "exit": 0, "matched": null, "ref": "09c9ed71a948ab803e46844239d7d277de9efc3b"}

## Buckets on the fixture (origin/main cleaner on the stored rows vs this head with the waiver)

```
row                    before     after     
live-thread-dirty      protected  protected 
open-pr-young          look       protected   <-
open-pr-young-dirty    look       protected   <-
open-pr-a-day-old      look       look      
open-pr-old            look       look      
open-pr-age-unknown    look       look      
pr-not-closed-young    look       look      
dirty-young            look       look      
gone-detached          look       prune       <-
gone-prunable          prune      prune     
gone-locked            protected  protected 
gone-live-thread       protected  protected 
main                   protected  protected 
eligible               safe       safe      
removed-earlier        removed    removed   
t3/clean-no-pr-a       look       safe        <-
t3/clean-no-pr-b       look       safe        <-
t3/unpushed            look       look      
t3/dirty               look       look      
t3/live-cwd            protected  protected 
t3/gone-detached       look       prune       <-
t3/unverified          look       look      
feature-x              look       look      
t3/open-pr-old         look       look      
before {'look': 16, 'protected': 5, 'prune': 1, 'removed': 1, 'safe': 1}
after  {'look': 10, 'protected': 7, 'prune': 3, 'removed': 1, 'safe': 3}
```
