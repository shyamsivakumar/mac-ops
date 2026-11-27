import hashlib
import re
import subprocess
import sys

ticket = sys.argv[1]
briefs, printed = [], []
for n in (1020, 1031):
    out = subprocess.run(
        [
            ticket,
            "start",
            f"shyamsivakumar/mac-ops#{n}",
            "--dry-run",
            "--print-brief",
            "--force-text-blockers",
        ],
        check=False,
        capture_output=True,
        text=True,
    ).stdout
    briefs.append(out.split("brief:\n", 1)[1].encode())
    found = re.search(r"brief prefix sha256: (\w+)", out)
    printed.append(found.group(1) if found else None)
a, b = briefs
n = 0
while n < min(len(a), len(b)) and a[n] == b[n]:
    n += 1
print("brief bytes", len(a), len(b), "common prefix bytes", n)
print("sha256 of common prefix", hashlib.sha256(a[:n]).hexdigest())
print("first line 1020:", a.split(b"\n")[0][:90])
print("first line 1031:", b.split(b"\n")[0][:90])
print("printed prefix sha 1020/1031:", printed)
if printed[0]:
    length = next(
        (k for k in range(len(a)) if hashlib.sha256(a[:k]).hexdigest() == printed[0]),
        None,
    )
    print(
        "static prefix length",
        length,
        "sha matches both briefs:",
        length is not None and hashlib.sha256(b[:length]).hexdigest() == printed[0],
    )
