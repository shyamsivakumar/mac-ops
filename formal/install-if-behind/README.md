# Install if behind model

`InstallIfBehindMarker.tla` extends the historical `InstallIfBehind.tla` model with the persisted observation marker in `scripts/install_if_behind.py`. The original model and its checks remain unchanged. Two firings contend for the install lock; a crash releases it but preserves the receipt and marker. A firing seeing an unverified new receipt resumes observation, rather than accepting it as up to date. Successful observation or rollback clears the marker. Commit `5921917` introduced this behavior (merged in PR #40).

`InstallIfBehindMarker.cfg` checks safety and crash-free eventual completion; `InstallIfBehindMarkerCrash.cfg` checks safety under crashes. Both are expected to pass. TLC 2.19 explored 59 and 171 distinct states respectively, with no errors. The model abstracts marker writing and rollback as atomic steps; it does not model partial writes, failed rollback, or more than two firings.

Run the marker checks with a Java 17 runtime and a TLA+ tools jar:

```sh
java -cp "$TLA_JAR" tlc2.TLC -config InstallIfBehindMarker.cfg InstallIfBehindMarker.tla
java -cp "$TLA_JAR" tlc2.TLC -config InstallIfBehindMarkerCrash.cfg InstallIfBehindMarker.tla
```

`replay_crash.py` exercises the real crash path in an isolated temporary home. The next firing resumes observation and rolls back if it fails. The historical model and crash configuration retain the original counterexample.
