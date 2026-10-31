# Install if behind model

`InstallIfBehind.tla` models the install automation chart in `docs/state-charts/installation.md` against `scripts/install_if_behind.py` at commit `dd91e98`. It follows `run_install_if_behind`, `evaluate_decision`, `rollback_to_release` and `install_lock`. It models two firings, F1 and F2, that contend for one `flock` on `install-if-behind.lock`. A firing that cannot take the lock defers. The lock is released when its holder exits or dies.

Each firing moves through idle, locked, decided, installing, observing and then done, rolledback or deferred. The model keeps the receipt commit (old or new), the active release, and whether the active new release passed observation. A firing decides up_to_date when the receipt already holds the new commit, and otherwise decides to install. The gate may block, which defers. Install writes the receipt before observation starts, as `install.sh` does. Observation then passes, which marks the release verified, or fails, which reactivates the old receipt and the old release.

The model checks four things. At most one firing is installing or observing. A firing that decided up_to_date while the receipt holds the new commit sees a verified release. A rollback leaves the old release active and the old receipt in place. With no crashes and weakly fair steps, every firing eventually ends done, rolledback or deferred.

`InstallIfBehind.cfg` sets `AllowCrash` to FALSE and is expected to pass. `InstallIfBehindCrash.cfg` sets `AllowCrash` to TRUE and is expected to fail on `NoUnverifiedAccepted`. TLC has not yet run on this spec (heavy was held at a zero limit by critical memory pressure on 2026-10-31). `replay_crash.py` reproduces the crash path against the real code: run `python3 formal/install-if-behind/replay_crash.py` and the killed firing is followed by `up_to_date` on the unverified receipt. A crash kills the holder at any point and releases the lock. The process may start again as a new firing, which loses its in-memory state. The real code persists no marker for observation. After a holder dies during observation, the receipt already names the new commit, so a later firing compares it with `origin/main`, returns up_to_date, and accepts a release that never passed observation. The failure shows that the receipt cannot distinguish "installed and verified" from "installed and unobserved". A fix needs a persisted observation state, written before install and cleared by observation, that the comparison step reads.

The model does not cover fetch failure, a dirty or non-main checkout, diverged history, dry runs, migration, agent parity, partial installs, a crash inside rollback, observation timing, or more than two firings. It assumes a firing that fails the gate or loses the lock takes no further action in that run. Rollback and install are single atomic steps. The remote commit is fixed as new, and the receipt starts as old. A missing receipt is not modelled. The second gate check before install is folded into the one gate step. Because rollback is one atomic step that cannot fail, `RollbackRestoresOld` holds by construction; the real rollback can fail and keep the new receipt (`scripts/install_if_behind.py:1003`), which the next model run should add.

Run both checks from this folder, one at a time, through `heavy`:

```
~/.local/bin/heavy java -XX:+UseParallelGC -cp ~/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 2 -metadir $TMPDIR/tlc-iib -config InstallIfBehind.cfg InstallIfBehind.tla
~/.local/bin/heavy java -XX:+UseParallelGC -cp ~/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 2 -metadir $TMPDIR/tlc-iib -config InstallIfBehindCrash.cfg InstallIfBehind.tla
```

The first run should report no error. The second should report that `NoUnverifiedAccepted` is violated and print the trace. The check requires Java 17 and the existing `~/Code/llmwiki/runtime/tla/tla2tools.jar`.
