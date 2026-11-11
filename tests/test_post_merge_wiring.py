"""Wiring proofs for the post-merge step of emp_thread_merge.

The hub functions under test are loaded with AST, the way
`verification/check_hub_auto_merge.py` does it, so the hub module is never run
and no socket, engine or provider is started.
"""
import ast
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "empryo/bin/emp-hub"


def load_hub_functions(names, **extra):
    """Load the named functions of the hub source with AST, without running the hub."""
    source = HUB.read_text()
    tree = ast.parse(source)
    wanted = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    missing = set(names) - {n.name for n in wanted}
    if missing:
        raise AssertionError("the hub has no " + ", ".join(sorted(missing)))
    module = ast.Module(body=wanted, type_ignores=[])
    namespace = {"json": json, "os": os, "uuid": uuid, "threading": threading, "tempfile": tempfile,
                 "now_iso": lambda: "2026-01-01T00:00:00.000Z", "log": lambda message: None, **extra}
    exec(compile(ast.fix_missing_locations(module), str(HUB), "exec"), namespace)
    return namespace


class MergeRecordTests(unittest.TestCase):
    """One merge-gate evaluation leaves exactly one record."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pm-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.record_path = Path(self.tmp.name) / "merges.jsonl"
        self.namespace = load_hub_functions(["revision_inputs", "merge_record", "write_merge_record", "complete_merge_record"],
                                            MERGE_LOCK=threading.Lock(), MERGE_RECORD=str(self.record_path))
        self.thread = {"threadId": "t1"}
        self.evidence = {"pullRequest": {"number": 7, "headRefOid": "a" * 40, "baseRefName": "main"},
                         "checks": {"state": "green"},
                         "reviewGate": {"threadId": "r1", "verdictWord": "PASS", "model": "subscriptions/m", "runId": "run-1"}}

    def records(self):
        if not self.record_path.exists():
            return []
        return [json.loads(line) for line in self.record_path.read_text().splitlines() if line.strip()]

    def test_the_post_merge_outcome_completes_the_one_merge_record(self):
        write = self.namespace["write_merge_record"]
        complete = self.namespace["complete_merge_record"]
        record_id = write(self.thread, self.evidence, True, False)
        self.assertEqual(len(self.records()), 1, "a merge writes one record")
        self.assertTrue(self.records()[0]["merged"])
        self.assertNotIn("postMerge", self.records()[0], "the outcome is not known when the record is written")
        complete(record_id, postMerge={"install": {"status": "ok"}})
        records = self.records()
        self.assertEqual(len(records), 1, "the post-merge outcome completes the same record")
        self.assertEqual(records[0]["postMerge"], {"install": {"status": "ok"}})
        self.assertTrue(records[0]["merged"])
        self.assertFalse(records[0]["dryRun"])

    def test_completing_one_record_leaves_the_others_untouched(self):
        write = self.namespace["write_merge_record"]
        complete = self.namespace["complete_merge_record"]
        first = write(self.thread, self.evidence, False, True)
        write(self.thread, self.evidence, True, False)
        complete(first, postMerge={"install": {"status": "failed"}})
        records = self.records()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["postMerge"], {"install": {"status": "failed"}})
        self.assertNotIn("postMerge", records[1])

    def test_an_unknown_record_completes_nothing(self):
        write = self.namespace["write_merge_record"]
        complete = self.namespace["complete_merge_record"]
        write(self.thread, self.evidence, True, False)
        self.assertFalse(complete("not-a-record", postMerge={"install": {"status": "ok"}}))
        self.assertFalse(complete(None, postMerge={"install": {"status": "ok"}}))
        self.assertEqual(len(self.records()), 1)
        self.assertNotIn("postMerge", self.records()[0])

    def test_completing_a_record_leaves_an_existing_temporary_file_alone(self):
        write = self.namespace["write_merge_record"]
        complete = self.namespace["complete_merge_record"]
        record_id = write(self.thread, self.evidence, True, False)
        temporary = self.record_path.with_name(self.record_path.name + ".tmp")
        temporary.write_text("precious")
        complete(record_id, postMerge={"install": {"status": "ok"}})
        self.assertEqual(temporary.read_text(), "precious", "an existing temporary file is never written through")
        self.assertEqual(len(self.records()), 1)

    def test_completing_a_record_never_writes_through_a_linked_temporary_file(self):
        write = self.namespace["write_merge_record"]
        complete = self.namespace["complete_merge_record"]
        record_id = write(self.thread, self.evidence, True, False)
        other = Path(self.tmp.name) / "other.txt"
        other.write_text("keep")
        os.symlink(other, self.record_path.with_name(self.record_path.name + ".tmp"))
        complete(record_id, postMerge={"install": {"status": "ok"}})
        self.assertEqual(other.read_text(), "keep", "a linked file is never written through")
        self.assertEqual(len(self.records()), 1)


class WiringTests(unittest.TestCase):
    def test_the_merge_record_is_written_before_the_post_step_and_completed_after_it(self):
        tree = ast.parse(HUB.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "execute_thread_merge")
        calls = {}
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                calls.setdefault(node.func.id, []).append(node.lineno)
        self.assertEqual(len(calls["write_merge_record"]), 2, "the merge and the refusal each write one record")
        self.assertLess(min(calls["write_merge_record"]), min(calls["run_post_merge"]),
                        "the merge record is written before the post-merge step")
        self.assertLess(max(calls["run_post_merge"]), min(calls["complete_merge_record"]),
                        "the post-merge outcome completes the record after the post-merge step")
        completion = next(n for n in ast.walk(function) if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Name) and n.func.id == "complete_merge_record")
        self.assertTrue(any(keyword.arg == "postMerge" for keyword in completion.keywords),
                        "the post-merge outcome completes the merge record")
        defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertNotIn("write_post_merge_record", defined, "the post-merge outcome never appends a second record")

    def test_the_completion_replaces_the_record_line_in_place(self):
        source = HUB.read_text()
        tree = ast.parse(source)
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "complete_merge_record")
        body = ast.get_source_segment(source, function)
        self.assertIn("os.replace", body, "the record line is replaced in place")
        self.assertNotIn('"a"', body, "the completion never appends a line")

    def test_installer_includes_helper_and_config(self):
        import install_empryo
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as home:
            planned = {str(target.relative_to(home)): mode for _, target, mode in install_empryo.plan(ROOT, Path(home))}
        self.assertEqual(planned[".local/lib/empryo/emp_post_merge.py"], 0o644)
        self.assertEqual(planned[".empryo/post-merge.json"], 0o644)


if __name__ == "__main__":
    unittest.main(verbosity=2)
