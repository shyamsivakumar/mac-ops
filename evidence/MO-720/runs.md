# MO-720 runs

Stub xcodebuild on PATH, temp state directory, socket.gethostname patched, heavy._launch_job captures the argv. The config is the worktree board_governor.json (foreground_build_hosts: shyams-macbook-pro).

```
$ PATH=<stub>/bin:$PATH python3 run.py <temp-state>
Shyams-M4 -> ['/usr/sbin/taskpolicy', '-b', 'xcodebuild', '-version', '-derivedDataPath', '/Users/shyamsivakumar/Library/Developer/Xcode/DerivedData/shared-proj']
Shyams-MacBook-Pro.local -> ['xcodebuild', '-version', '-derivedDataPath', '/Users/shyamsivakumar/Library/Developer/Xcode/DerivedData/shared-proj']
```
