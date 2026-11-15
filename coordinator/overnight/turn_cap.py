import importlib.util
from pathlib import Path


def load_handler():
    path = Path.home() / "Code/coordinator/loop/turn_cap.py"
    spec = importlib.util.spec_from_file_location("canonical_turn_cap", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def one_pass(dry_run):
    return load_handler().one_pass(dry_run)
