"""The test package.

Importing it puts the fake `gh` first on PATH and points the gh usage log,
the gh cache and the skip log at a temp directory, so a run of the suite
never spends the live quota and never appends a fixture row to the live
logs. The environment is set here, once, so every test module inherits it
without a per-test edit.
"""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "coordinator" / "bin"

_loader = SourceFileLoader("gh_isolation", str(BIN / "gh_isolation.py"))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
_isolation = importlib.util.module_from_spec(_spec)
_loader.exec_module(_isolation)
_isolation.install()
