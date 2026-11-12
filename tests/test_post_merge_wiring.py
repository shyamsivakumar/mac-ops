"""The installer ships the post-merge helper and its config."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WiringTests(unittest.TestCase):
    def test_installer_includes_helper_and_config(self):
        import install_coordinator
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as home:
            planned = {str(target.relative_to(home)): mode for _, target, mode in install_coordinator.plan(ROOT, Path(home))}
        self.assertEqual(planned[".local/lib/coordinator/post_merge.py"], 0o644)
        self.assertEqual(planned[".coordinator/post-merge.json"], 0o644)


if __name__ == "__main__":
    unittest.main(verbosity=2)
