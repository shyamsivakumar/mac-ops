import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

root = Path(__file__).resolve().parent
for name, version in (("pi-background-monitor", "1.0.1"), ("pi-checklist", "3.3.0"), ("pi-subagent-manager", "1.9.0")):
    url = f"https://registry.npmjs.org/{name}/{version}"
    with urllib.request.urlopen(url, timeout=30) as response:
        metadata = json.load(response)
    with urllib.request.urlopen(metadata["dist"]["tarball"], timeout=30) as response:
        payload = response.read()
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode()
    if integrity != metadata["dist"]["integrity"]:
        raise ValueError(f"Integrity mismatch: {name}")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if member.isfile() and not path.is_absolute() and ".." not in path.parts and path.suffix in {".ts", ".js", ".mjs", ".json", ".md"}:
                target = root / "sources" / name / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
    print(name, version, integrity, metadata.get("gitHead"))
