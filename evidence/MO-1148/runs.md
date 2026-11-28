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
removable = getattr(cleaner, "removal_candidates", None)
if waive is None or removable is None:
    print("FAIL buckets: waived_reasons or removal_candidates missing")
    sys.exit(1)
rows = json.load(open(fixture))["rows"]
for row in rows:
    row["path"] = row["path"].replace("@T3@", str(cleaner.T3_WORKTREE_ROOT))
    kept = waive(row, row["reasons"])
    row["t3_waiver"] = kept != row["reasons"]
    row["reasons"] = kept
    row["eligible"] = not row["reasons"]
got = dict(sorted(collections.Counter(cleaner.categorize(r) for r in rows).items()))
want = {"look": 10, "protected": 7, "prune": 3, "removed": 1, "safe": 3}
print("buckets", got)
if got != want:
    print("FAIL buckets want", want)
    sys.exit(1)
scheduled = [r["branch"] for r in removable(rows, False)]
clean_action = [r["branch"] for r in removable(rows, True)]
print("scheduled removes", scheduled)
print("clean action removes", clean_action)
if scheduled != ["eligible", "removed-earlier"] or clean_action != ["eligible", "removed-earlier", "t3/clean-no-pr-a", "t3/clean-no-pr-b"]:
    print("FAIL buckets: removal sets")
    sys.exit(1)
PY
```

```
FAIL buckets: fixture missing

```

{"state": "red", "exit": 1, "matched": true, "ref": "ed088e4f8f11984e00a4e3f166980520f6149f64"}
## Proof run: green 51328f403bd964f5329fd6b0a6f8f43a0f13af70

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
removable = getattr(cleaner, "removal_candidates", None)
if waive is None or removable is None:
    print("FAIL buckets: waived_reasons or removal_candidates missing")
    sys.exit(1)
rows = json.load(open(fixture))["rows"]
for row in rows:
    row["path"] = row["path"].replace("@T3@", str(cleaner.T3_WORKTREE_ROOT))
    kept = waive(row, row["reasons"])
    row["t3_waiver"] = kept != row["reasons"]
    row["reasons"] = kept
    row["eligible"] = not row["reasons"]
got = dict(sorted(collections.Counter(cleaner.categorize(r) for r in rows).items()))
want = {"look": 10, "protected": 7, "prune": 3, "removed": 1, "safe": 3}
print("buckets", got)
if got != want:
    print("FAIL buckets want", want)
    sys.exit(1)
scheduled = [r["branch"] for r in removable(rows, False)]
clean_action = [r["branch"] for r in removable(rows, True)]
print("scheduled removes", scheduled)
print("clean action removes", clean_action)
if scheduled != ["eligible", "removed-earlier"] or clean_action != ["eligible", "removed-earlier", "t3/clean-no-pr-a", "t3/clean-no-pr-b"]:
    print("FAIL buckets: removal sets")
    sys.exit(1)
PY
```

```
buckets {'look': 10, 'protected': 7, 'prune': 3, 'removed': 1, 'safe': 3}
scheduled removes ['eligible', 'removed-earlier']
clean action removes ['eligible', 'removed-earlier', 't3/clean-no-pr-a', 't3/clean-no-pr-b']

```

{"state": "green", "exit": 0, "matched": null, "ref": "51328f403bd964f5329fd6b0a6f8f43a0f13af70"}

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
