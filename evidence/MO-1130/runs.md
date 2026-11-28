## Proof run: red afebc91fce07dfe484d569025639e1b9ef5b5cee

```sh
python3 scripts/proof_verdict_class.py
```

```
/Applications/Xcode.app/Contents/Developer/usr/bin/python3: can't open file '/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/proof-run-kwg_auc5/checkout/scripts/proof_verdict_class.py': [Errno 2] No such file or directory

```

{"state": "red", "exit": 2, "matched": true, "ref": "afebc91fce07dfe484d569025639e1b9ef5b5cee"}
## Proof run: green 9c227c0d78a5343711e79fd12771f470431d2352

```sh
python3 scripts/proof_verdict_class.py
```

```
ok   want size  got size  Major: 616 changed lines against a hard 150 cap: runtime 145
ok   want size  got size  Major: 176 counted lines against the 150 aggregate, and a fo
ok   want proof got proof Major: Two required cases unproved: two lanes competing for 
ok   want proof got proof Major: The proof hashes a body and calls laneStore.apply ins
ok   want scope got scope Major: Edits an existing restart proof so the gate passes, w
ok   want scope got scope Major: 379 changed code lines across four files and it edits
ok   want logic got logic Major: A frozen account still permits a buy when the daily r
ok   want logic got logic Major: bot2_service.js:103 reports the pair blocked when Lan
ok   want minor_only got minor_only '```json\n{"verdict": "FAIL", "findings": '
ok   want logic      got logic      'VERDICT: FAIL'
ok   want environment got environment 'fails the same on origin/main\nVERDICT: F'
verdict class proof: ok

```

{"state": "green", "exit": 0, "matched": null, "ref": "9c227c0d78a5343711e79fd12771f470431d2352"}
