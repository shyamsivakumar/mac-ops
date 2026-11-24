## Ticket proof (HOME is a temp dir)

### origin/main coordq
```
  File "<string>", line 1, in <module>
AttributeError: module 'cq' has no attribute 'drop_older_heads'
exit 1
```

### branch, code commit 21ba13d7
```

exit 0
```

## send-integrity eval (extended)

### origin/main coordq
```
    dropped = coordq.drop_older_heads(queue, title, below)
AttributeError: module 'fixture_coordq' has no attribute 'drop_older_heads'
exit 1
```

### branch, in place
```
refused: the action key k1 is already queued as coordq #1
send-integrity OK
exit 0
```

### branch, flat copy of bin, overnight and models.json in one directory (temp HOME with tickets.json)
```
refused: the action key k1 is already queued as coordq #1
send-integrity OK
exit 0
```

## current_head against real PR #947 (read-only, fresh=True, temp COORDQ_DIR)
```
key MO, gh headRefOid 0a5d79a19144b02cc78d9aea4fe90574f0e66947
current_head("MO#947 check <40 a>") -> 0a5d79a19144b02cc78d9aea4fe90574f0e66947
current_head("ZZZ#947 check <40 a>") -> None (unknown key, no gh call)
```
