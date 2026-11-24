# MO-932 runs at code commit a49286766b62db8217c34aeb61ee24fc16dd3711 (merged with origin/main adc3269b)

## 1. Ticket proof command on origin/main (red)
```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'inbox_replay'
exit 1
```
## 2. Ticket proof command on the head (green)
```

exit 0
```
## 3. inbox eval with the previous inbox_replay.py (fc941d8b) and the new selftest (red)
```
  File "/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.ZShjnipIMR/coordinator/bin/inbox.py", line 147, in _insert
    conn.execute(
OverflowError: Python int too large to convert to SQLite INTEGER
exit 1
```
## 4. inbox eval on the head (green)
```
inbox eval ok
exit 0
```
