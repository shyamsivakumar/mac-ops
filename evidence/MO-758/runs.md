# MO-758 runs

## Before (origin/main coordq)
```
exit 1
    raise JSONDecodeError("Expecting value", s, err.value) from None
json.decoder.JSONDecodeError: Expecting value: line 1 column 20 (char 19)
queue.json
queue.json.prev
```

## After (branch)
```
exit 0
dispatch.stopped
j
queue.json
queue.json.prev
{"v":1,"ts":1795209549.544071,"event":"queue_fallback","actor":"coordq","repo":null,"ticket":null,"pr":null,"h
```

## New test cases: origin/main code (3 errors), then branch (OK)
```
Ran 3 tests in 0.622s

FAILED (errors=3)
Ran 3 tests in 0.016s

OK
```

The ticket proof command ran as written.
