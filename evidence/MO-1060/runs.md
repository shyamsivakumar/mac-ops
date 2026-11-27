# MO-1060 proof

The installer's `--dry-run` refuses a linked worktree and requires branch main, so the same functions it uses
(`changes` and `changed_launchd_jobs`, the source of would_write and would_reload) were called directly,
read only, from each checkout. Script: scratchpad `spend-dry.py`.

## Ticket proof command

On main (c4979e4b), red:

    $ test -f coordinator/launchd/dev.coordinator.spend.plist || { echo "no dev.coordinator.spend.plist"; exit 1; }
    no dev.coordinator.spend.plist   (exit 1)

On the head, green: the command exits 0.

## plutil

    $ plutil -lint coordinator/launchd/dev.coordinator.spend.plist
    coordinator/launchd/dev.coordinator.spend.plist: OK

## Installer plan

Head:

    would_write:  ~/Library/LaunchAgents/dev.coordinator.spend.plist
    would_reload: dev.coordinator.spend

Main (c4979e4b): would_write [] and would_reload [] for spend.

## Overlap

launchd starts no second instance of a loaded job while one runs; no other coordinator plist or job adds its own lock.
The plist differs from gatekeep only in label, argument, StartInterval (600) and log name.
