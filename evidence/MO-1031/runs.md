# MO-1031 proof runs

Command: sh evidence/MO-1031/proof.sh <path to coordq>. It uses a temp COORDQ_DIR and COORD_JOURNAL_DIR, starts a wait, ages it 90 minutes, starts it again to show the first start is kept, lists, then ends it.

## origin/main (red)
~~~
usage: coordq [-h]
              {start,create,list,drop,status,dispatch,gatekeep,gate,fix} ...
coordq: error: argument cmd: invalid choice: 'wait' (choose from 'start', 'create', 'list', 'drop', 'status', 'dispatch', 'gatekeep', 'gate', 'fix')
~~~

## branch head (green)
~~~
[{"id": "card-1", "owner": "shyam", "since": 1795749420.903788, "ageMinutes": 0}]
[{"id": "card-1", "owner": "shyam", "since": 1795744020.959261, "ageMinutes": 90}]
[]
~~~
