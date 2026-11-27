# MO-1035 proof runs

Command (temp label, split, queue and guess files; relock stubbed; real labels
untouched):

    PYTHONPATH=coordinator/evals/hillclimb python3 evidence/MO-1035/proof.py <daily3.py>

## origin/main (red)

<!-- markdownlint-disable MD013 -->

    daily3.py record: error: the following arguments are required: --reason
    t1 ['--reason', 'Because the retry is'] -> rc=0 reason_in_row='Because the retry is cheap'
    t2 [] -> rc=SystemExit(2) reason_in_row=no row
    t3 ['--reason', 'xxxxxxxxxxxxxxxxxxxx'] -> rc=0 reason_in_row='xxxx...(201 x)'
    t4 ['--reason', 'line one\nline two'] -> rc=0 reason_in_row='line one\nline two'

<!-- markdownlint-enable MD013 -->

Red signature: t2 (no reason) fails, t3 (201 chars) and t4 (newline) are accepted.

## head (green)

<!-- markdownlint-disable MD013 -->

    daily3: --reason must be one line of at most 200 characters
    daily3: --reason must be one line of at most 200 characters
    t1 ['--reason', 'Because the retry is'] -> rc=0 reason_in_row='Because the retry is cheap'
    t2 [] -> rc=0 reason_in_row=''
    t3 ['--reason', 'xxxxxxxxxxxxxxxxxxxx'] -> rc=2 reason_in_row=no row
    t4 ['--reason', 'line one\nline two'] -> rc=2 reason_in_row=no row

<!-- markdownlint-enable MD013 -->

Green: `t2 [] -> rc=0 reason_in_row=''` and `t3 ... rc=2 reason_in_row=no row`.
