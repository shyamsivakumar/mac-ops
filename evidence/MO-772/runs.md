## before (origin/main)
$ python3 evals/harbor/build_tasks.py check
ok: 10 tasks

## after
$ python3 evals/harbor/build_tasks.py add mac-ops 716
add: mac-ops-716
$ python3 evals/harbor/build_tasks.py add mac-ops 704
add: mac-ops-704
$ python3 evals/harbor/build_tasks.py add mac-ops 694
add: mac-ops-694
$ python3 evals/harbor/build_tasks.py add mac-ops 716
add: already present
$ python3 evals/harbor/build_tasks.py check
ok: 13 tasks

## build twice (byte-identical task folders)
$ python3 evals/harbor/build_tasks.py build mac-ops-716 mac-ops-704 mac-ops-694   (twice, folder hash compared)
ee688e52bc676a2f32993a151721e268c2342910  - == ee688e52bc676a2f32993a151721e268c2342910  -
