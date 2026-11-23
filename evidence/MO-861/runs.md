# MO-861 runs

## shasum (live vs mac-ops source, sha256)

```text
946c7582a862a0f612032c2bbd89a1612fd61d6f06cae0ac9a2e80bb2daeb500  ~/Code/coordinator/evals/hillclimb/build_labels.py
946c7582a862a0f612032c2bbd89a1612fd61d6f06cae0ac9a2e80bb2daeb500  coordinator/evals/hillclimb/build_labels.py
7e5786ace3a4602e33afe59449fc6673f222451a70f0005931d86da194129c55  ~/Code/coordinator/evals/hillclimb/daily3.py
7e5786ace3a4602e33afe59449fc6673f222451a70f0005931d86da194129c55  coordinator/evals/hillclimb/daily3.py
58cf5d593841c503077162551be2db7c62d7f2dd31f7688b015f77cd73c06655  ~/Code/coordinator/evals/hillclimb/burst.py
58cf5d593841c503077162551be2db7c62d7f2dd31f7688b015f77cd73c06655  coordinator/evals/hillclimb/burst.py
2f5237bfcfa215f91bf9d446fdfcc2905b8c18df31a61b97079a7c8bf0ea460b  ~/Code/coordinator/evals/hillclimb/README.md
2f5237bfcfa215f91bf9d446fdfcc2905b8c18df31a61b97079a7c8bf0ea460b  coordinator/evals/hillclimb/README.md
d6eb76bd47b679d5f8bcd2b703dbb72c63aab1d98825cdb0bcdd237a1eb69588  ~/Code/coordinator/evals/hillclimb/arms/plain_agent.py
d6eb76bd47b679d5f8bcd2b703dbb72c63aab1d98825cdb0bcdd237a1eb69588  coordinator/evals/hillclimb/arms/plain_agent.py
```

## Proof command on main (module absent)

```text
ModuleNotFoundError: No module named 'tests.test_hillclimb_scripts'
FAILED (errors=1)
```

## Installer plan (changes() on a temp home and temp coordinator dir; the CLI dry run refuses a non-main checkout)

```text
<coordinator>/evals/hillclimb/README.md 0o644
<coordinator>/evals/hillclimb/arms/plain_agent.py 0o644
<coordinator>/evals/hillclimb/build_labels.py 0o644
<coordinator>/evals/hillclimb/burst.py 0o644
<coordinator>/evals/hillclimb/daily3.py 0o644
```

## Proof command on the branch

```text
test_mines_only_unanswered_thin_kinds_and_is_idempotent (tests.test_hillclimb_scripts.BurstMining) ... ok
test_pick_writes_three_guesses_before_printing_and_is_deterministic (tests.test_hillclimb_scripts.DailyPick) ... ok
test_record_appends_one_label_with_required_keys (tests.test_hillclimb_scripts.DailyRecord) ... ok
test_record_refuses_duplicate_id (tests.test_hillclimb_scripts.DailyRecord) ... ok
test_install_changes_list_hillclimb_code_and_no_data_files (tests.test_hillclimb_scripts.InstallPlan) ... ok

----------------------------------------------------------------------
Ran 5 tests in 0.049s

OK
```

## One-line break in a temp copy (daily3.py: duplicate check replaced by `if False:`)

```text
Traceback (most recent call last):
  File "/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmpq_g3jerv/tests/test_hillclimb_scripts.py", line 129, in test_record_refuses_duplicate_id
    self.assertEqual(self.record(base, labels, split, guesses), 2)
AssertionError: 0 != 2

----------------------------------------------------------------------
Ran 5 tests in 0.042s

FAILED (failures=1)
```

## Fix round: installer enumerates exactly the five managed files

Old head 781ccec9 installer, new test with stray `split.json` and `labels.jsonl` in the source dir:

```text
AssertionError: Items in the first set but not the second:
'labels.jsonl'
'split.json'

FAILED (failures=1)
```

This branch, same test (`python3 -m unittest tests.test_hillclimb_scripts`):

```text
Ran 5 tests in 0.117s

OK
```

`cmp` of the five scripts against `~/Code/coordinator/evals/hillclimb`: identical.

## Fix round 2: rebuild keeps recorded rows and writes the scorer's split format

Gate finding: `build_labels.py` replaced `labels.jsonl` (dropping Daily 3 records and their reasons) and wrote a `split.json` without the flat keys `score.py` reads.

New case `RebuildKeepsRecords` (temp dirs only, sources mocked, `score.read_cases` loads the split).

Old head 670feb7c `build_labels.py`:

```text
FAILED (failures=1)
```

This branch (`python3 -m unittest tests.test_hillclimb_scripts`): `Ran 6 tests ... OK`.

The scripts now differ from live. sha256 change (live to mac-ops source); `daily3.py`, `burst.py` and `plain_agent.py` still match live:

```text
build_labels.py  946c7582a862a0f612032c2bbd89a1612fd61d6f06cae0ac9a2e80bb2daeb500 -> 48fe5dffd0c0ed839dd59b5c32d04535d748b0dabdb917ec610f37c64d892207
README.md        2f5237bfcfa215f91bf9d446fdfcc2905b8c18df31a61b97079a7c8bf0ea460b -> 888937c93f99687baef5c57fbd94a4d93c2c25e882a3c5303f0cc2f68b949c2f
```

`build_labels.py` and `README.md` now differ from the live copies until the installer runs.
