"""update_references.save only reports paths it actually wrote."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import update_references


class TestUpdateReferencesSave(unittest.TestCase):
    def test_save_skips_unchanged_and_reports_writes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "wrapper.py"
            path.write_text("same\n")
            backup = root / "backups"

            self.assertIs(update_references.save(path, "same\n", backup), False)
            self.assertFalse(backup.exists())
            self.assertEqual(path.read_text(), "same\n")

            self.assertIs(update_references.save(path, "new\n", backup), True)
            self.assertEqual(path.read_text(), "new\n")
            copies = list(backup.iterdir())
            self.assertEqual(len(copies), 1)
            self.assertEqual(copies[0].read_text(), "same\n")


if __name__ == "__main__":
    unittest.main()
