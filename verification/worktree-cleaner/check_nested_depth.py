"""Regression for deeply nested ignored repositories and incomplete scans."""
import importlib.util
from pathlib import Path
import tempfile
import subprocess

script = Path(__file__).resolve().parents[2] / "scripts/worktree-cleaner/cleaner.py"
spec = importlib.util.spec_from_file_location("worktree_cleaner", script)
cleaner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleaner)

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    clone = root / "vendor" / "node_modules"
    for _ in range(16):
        clone /= "deep"
    clone.mkdir(parents=True)
    (clone / ".git").mkdir()
    bare = root / "ignored" / "nested" / "bare.git"
    bare.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "--bare", "--quiet", str(bare)], check=True)
    found, complete = cleaner.nested_checkout_scan(root)
    assert complete and clone in found and bare in found, (found, complete)
    _, complete = cleaner.nested_checkout_scan(root, budget=2)
    assert not complete
    print("deep nested repository detected; exhausted budget fails closed")
