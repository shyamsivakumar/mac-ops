# MO-754 proof runs

## Before (origin/main)
```
[null,"null"]
```
## After, no receipt
```
["gpt-6.1-terra","null"]
```
## After, fixture receipt under HOME
```
["gpt-6.1-terra","string"]
```

## Notes
Adapted from the ticket command: run inside the worktree, the receipt fixture is written at `$HOME/.local/state/mac-ops/coordinator-installation.json`, which is where `install_coordinator.py` writes the receipt.

## coordq journal_item (launched row, temp dirs)
`["launched","gpt-6.1-terra","requested",5]`
