import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WiringTests(unittest.TestCase):
    def test_merge_records_before_post_step_and_reports_result(self):
        tree = ast.parse((ROOT / "empryo/bin/emp-hub").read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "tool_thread_merge")
        calls = sorted((n.lineno, n.func.id) for n in ast.walk(function) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name))
        names = [name for _, name in calls]
        self.assertLess(names.index("write_merge_record"), names.index("run_post_merge"))
        self.assertLess(names.index("run_post_merge"), names.index("write_post_merge_record"))
        self.assertTrue(any(isinstance(n, ast.Constant) and n.value == "postMerge" for n in ast.walk(function)))

    def test_installer_includes_helper_and_config(self):
        import install_empryo
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as home:
            planned = {str(target.relative_to(home)): mode for _, target, mode in install_empryo.plan(ROOT, Path(home))}
        self.assertEqual(planned[".local/lib/empryo/emp_post_merge.py"], 0o644)
        self.assertEqual(planned[".empryo/post-merge.json"], 0o644)


if __name__ == "__main__":
    unittest.main()
