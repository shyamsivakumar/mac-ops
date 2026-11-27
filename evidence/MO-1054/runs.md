# MO-1054 runs

Red on origin/main (`git show origin/main:coordinator/bin/gate_bar.py | grep -c 'most severe first'` prints 0): the proof prints "gate_bar.py has no one-pass rule" and exits 1.

Green on the branch: `sh evidence/MO-1054/proof.sh` exits 0. The brief built by `build_gate_brief` contains the bullet and still ends with the CHECK and VERDICT line (last printed line above is the CHECK/VERDICT instruction).

`python3 -m unittest tests.test_gate_bar_convergence`: 7 tests OK (CONVERGENCE tuple extended with the new bullet; it fails on origin/main).
