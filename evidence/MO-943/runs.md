## Ticket proof (HOME is a temp dir)

### origin/main coordq
```
  File "<string>", line 1, in <module>
AttributeError: module 'cq' has no attribute 'drop_older_heads'
exit 1
```

### branch head 5bc8ffc2
```

exit 0
```

## Extended eval send-integrity (the new block covers older heads dropped, other PR/repo/thread kept, same head kept, started record kept, gate: kept, action key released, refused start, stale current head, unreadable current head)

### origin/main coordq with the new eval
```
    dropped = coordq.drop_older_heads(queue, title, target, below)
AttributeError: module 'fixture_coordq' has no attribute 'drop_older_heads'
exit 1
```

### branch
```
refused: the action key k1 is already queued as coordq #1
send-integrity OK
exit 0
```
