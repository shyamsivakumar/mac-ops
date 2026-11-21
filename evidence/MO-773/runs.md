# MO-773 runs

## Before (origin/main journal.py)
```
AttributeError: module 'journal' has no attribute 'manifest_hash'  (installer writes no manifest; rows carry no data.manifest)
```

## After: receipt written by install_coordinator.manifest_hashes into a temp HOME, then a journal row from journal.py
```
"manifest":"f436d41367d748bdc8ae4b52c9c0b48ec5da52d9a6ae4f53349f628d0d2a9e50"
"manifest":"f436d41367d748bdc8ae4b52c9c0b48ec5da52d9a6ae4f53349f628d0d2a9e50"
f436d41367d748bdc8ae4b52c9c0b48ec5da52d9a6ae4f53349f628d0d2a9e50  -
```

A full install_coordinator.install into a temp HOME needs the real home and an origin/main checkout, so the receipt was written by the installer helper manifest_hashes plus the same JSON shape.
