import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("emp_post_merge", ROOT / "empryo/bin/emp_post_merge.py")
post = importlib.util.module_from_spec(spec)
spec.loader.exec_module(post)


class PostMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.remote = self.home / "remote.git"
        self.checkout = self.home / "Code" / "example"
        self.checkout.parent.mkdir(parents=True)
        self.git(self.home, "init", "--bare", str(self.remote))
        self.git(self.home, "clone", str(self.remote), str(self.checkout))
        self.git(self.checkout, "checkout", "-b", "main")
        self.git(self.checkout, "config", "user.email", "test@example.org")
        self.git(self.checkout, "config", "user.name", "Test")
        (self.checkout / "file").write_text("initial")
        self.git(self.checkout, "add", "file")
        self.git(self.checkout, "commit", "-m", "initial")
        self.git(self.checkout, "push", str(self.remote), "main")
        self.git(self.checkout, "remote", "set-url", "origin", "https://github.com/test/example.git")
        self.git(self.checkout, "config", "url." + str(self.remote) + ".insteadOf", "https://github.com/test/example.git")
        self.other = self.home / "other"
        self.git(self.home, "clone", "-b", "main", str(self.remote), str(self.other))
        self.git(self.other, "config", "user.email", "test@example.org")
        self.git(self.other, "config", "user.name", "Test")
        (self.other / "file").write_text("remote")
        self.git(self.other, "commit", "-am", "remote")
        self.git(self.other, "push", str(self.remote), "main")
        self.config = self.home / ".empryo" / "post-merge.json"
        self.config.parent.mkdir(parents=True, exist_ok=True)

    def git(self, cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()

    def write_config(self, **entry):
        self.config.write_text(json.dumps({"test/example": entry}))

    def run_post(self, base="main", config=None, changed_files=None):
        return post.post_merge("test/example", base, self.home, config or str(self.config), changed_files)

    def test_clean_main_behind_is_fast_forwarded(self):
        self.write_config()
        result = self.run_post()
        self.assertEqual(result["fastForward"]["status"], "ok")
        self.assertEqual(result["status"], "ok")
        self.assertEqual((self.checkout / "file").read_text(), "remote")

    def test_dirty_checkout_is_skipped_with_reason(self):
        self.write_config()
        (self.checkout / "file").write_text("local")
        result = self.run_post()
        self.assertEqual(result["fastForward"]["status"], "skipped")
        self.assertIn("local changes", result["reason"])
        self.assertEqual((self.checkout / "file").read_text(), "local")

    def test_checkout_on_another_branch_is_skipped(self):
        self.write_config()
        self.git(self.checkout, "checkout", "-b", "feature")
        result = self.run_post()
        self.assertIn("not on main", result["reason"])

    def test_diverged_main_is_skipped(self):
        self.write_config()
        (self.checkout / "local").write_text("local")
        self.git(self.checkout, "add", "local")
        self.git(self.checkout, "commit", "-m", "local")
        before = self.git(self.checkout, "rev-parse", "HEAD")
        result = self.run_post()
        self.assertIn("fast-forward failed", result["reason"])
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), before)

    def test_ahead_of_origin_is_skipped(self):
        self.write_config()
        self.git(self.checkout, "fetch", "origin", "main")
        self.git(self.checkout, "merge", "--ff-only", "origin/main")
        (self.checkout / "local").write_text("local")
        self.git(self.checkout, "add", "local")
        self.git(self.checkout, "commit", "-m", "local")
        result = self.run_post()
        self.assertIn("ahead of origin/main", result["reason"])
        self.assertNotEqual(result["install"]["status"], "ok")

    def test_missing_configuration_is_skipped(self):
        result = self.run_post(config=str(self.home / "missing.json"))
        self.assertIn("no post-merge configuration", result["reason"])
        self.assertFalse(result["configured"])

    def test_unknown_repository_fast_forwards_without_install(self):
        self.config.write_text(json.dumps({"other/example": {}}))
        result = self.run_post()
        self.assertEqual(result["fastForward"]["status"], "ok")
        self.assertEqual(result["install"]["status"], "skipped")

    def test_origin_mismatch_is_skipped(self):
        self.write_config()
        self.git(self.checkout, "remote", "set-url", "origin", "https://github.com/test/elsewhere.git")
        result = self.run_post()
        self.assertIn("origin does not match", result["reason"])

    def test_non_main_base_is_skipped(self):
        self.write_config()
        result = self.run_post(base="release")
        self.assertIn("did not target main", result["reason"])

    def test_invalid_checkout_name_is_skipped(self):
        self.config.write_text(json.dumps({"test/example": {"checkout": "../escape"}}))
        result = self.run_post()
        self.assertIn("checkout name", result["reason"])

    def test_missing_checkout_is_skipped(self):
        self.write_config(checkout="absent")
        result = self.run_post()
        self.assertIn("no checkout at", result["reason"])

    def test_install_success_is_recorded(self):
        self.write_config(install=["/bin/sh", "-c", "exit 0"])
        result = self.run_post()
        self.assertEqual(result["install"]["status"], "ok")

    def test_install_failure_is_recorded(self):
        self.write_config(install=["/bin/sh", "-c", "exit 3"])
        result = self.run_post()
        self.assertEqual(result["install"]["status"], "failed")
        self.assertEqual(result["status"], "failed")

    def test_install_deferral_is_not_a_failure(self):
        self.write_config(install=["/bin/sh", "-c", "echo '{\"decision\": \"deferred\", \"reason\": \"busy\"}'; exit 75"])
        result = self.run_post()
        self.assertEqual(result["install"]["status"], "deferred")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["install"]["reason"], "busy")

    def test_deferred_install_does_not_copy_config(self):
        self.write_config(install=["/bin/sh", "-c", "exit 75"], configSync=["EMPRYO.md"])
        result = self.run_post(changed_files=["empryo/config/EMPRYO.md"])
        self.assertEqual(result["install"]["status"], "deferred")
        self.assertEqual(result["configSync"][0]["reason"], "install did not complete")

    def test_install_rollback_is_a_failure(self):
        self.write_config(install=["/bin/sh", "-c", "echo '{\"decision\": \"rolled_back\", \"reason\": \"regression\"}'; exit 2"])
        result = self.run_post()
        self.assertEqual(result["install"]["status"], "failed")
        self.assertEqual(result["install"]["decision"], "rolled_back")
        self.assertEqual(result["install"]["reason"], "regression")

    def test_install_reason_is_shortened(self):
        self.write_config(install=["/bin/sh", "-c", "echo '{\"decision\": \"error\", \"reason\": \"" + "x" * 900 + "\"}'; exit 2"])
        result = self.run_post()
        self.assertEqual(result["install"]["status"], "failed")
        self.assertLessEqual(len(result["install"]["reason"]), 300)

    def test_install_timeout_is_recorded(self):
        self.write_config(install=["/bin/sh", "-c", "sleep 30"], timeout=1)
        result = self.run_post()
        self.assertEqual(result["install"]["status"], "failed")
        self.assertIn("timed out", result["install"]["reason"])

    def test_config_files_changed_by_the_merge_are_synced(self):
        source = self.other / "empryo" / "config"
        (source / "agents").mkdir(parents=True)
        (source / "EMPRYO.md").write_text("new rules")
        (source / "hooks.json").write_text("{}")
        (source / "agents" / "code-reviewer.md").write_text("reviewer")
        self.git(self.other, "add", "-A")
        self.git(self.other, "commit", "-m", "config")
        self.git(self.other, "push", str(self.remote), "main")
        live = self.home / ".empryo"
        (live / "agents").mkdir(parents=True, exist_ok=True)
        (live / "EMPRYO.md").write_text("old rules")
        (live / "agents" / "code-reviewer.md").write_text("old reviewer")
        self.write_config(configSync=["EMPRYO.md", "hooks.json", "agents/code-reviewer.md"])
        result = self.run_post(changed_files=["empryo/config/EMPRYO.md", "empryo/config/hooks.json", "empryo/config/agents/code-reviewer.md"])
        self.assertEqual((live / "EMPRYO.md").read_text(), "new rules")
        self.assertEqual((live / "agents" / "code-reviewer.md").read_text(), "reviewer")
        self.assertEqual((live / "hooks.json").read_text(), "{}")
        backups = sorted(p.name for p in live.glob("EMPRYO.md.before-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((live / backups[0]).read_text(), "old rules")
        self.assertTrue(next((live / "agents").glob("code-reviewer.md.before-*")))

    def test_protected_config_files_are_never_synced(self):
        source = self.other / "empryo" / "config"
        source.mkdir(parents=True)
        (source / "tickets.json").write_text("{}")
        (source / "config.json").write_text("{}")
        (source / "routing.json").write_text("{}")
        self.git(self.other, "add", "-A")
        self.git(self.other, "commit", "-m", "config")
        self.git(self.other, "push", str(self.remote), "main")
        live = self.home / ".empryo"
        live.mkdir(parents=True, exist_ok=True)
        (live / "tickets.json").write_text("keep")
        (live / "config.json").write_text("keep")
        self.write_config(configSync=["tickets.json", "config.json", "routing.json"])
        result = self.run_post(changed_files=["empryo/config/tickets.json", "empryo/config/config.json", "empryo/config/routing.json"])
        self.assertEqual((live / "tickets.json").read_text(), "keep")
        self.assertEqual((live / "config.json").read_text(), "keep")
        self.assertFalse((live / "routing.json").exists())
        for record in result["configSync"]:
            self.assertEqual(record["status"], "skipped")

    def test_an_ignored_local_file_is_never_overwritten_by_the_fast_forward(self):
        self.write_config()
        self.git(self.checkout, "fetch", "origin", "main")
        self.git(self.checkout, "merge", "--ff-only", "origin/main")
        (self.checkout / ".gitignore").write_text("local.txt\n")
        self.git(self.checkout, "add", ".gitignore")
        self.git(self.checkout, "commit", "-m", "ignore")
        self.git(self.checkout, "push", str(self.remote), "main")
        self.git(self.other, "fetch", "origin", "main")
        self.git(self.other, "merge", "--ff-only", "origin/main")
        (self.other / "local.txt").write_text("tracked now")
        self.git(self.other, "add", "-f", "local.txt")
        self.git(self.other, "commit", "-m", "track")
        self.git(self.other, "push", str(self.remote), "main")
        (self.checkout / "local.txt").write_text("local secret")
        result = self.run_post()
        self.assertEqual(result["fastForward"]["status"], "skipped")
        self.assertIn("fast-forward failed", result["reason"])
        self.assertEqual((self.checkout / "local.txt").read_text(), "local secret")

    def test_the_config_sync_never_writes_through_an_existing_temporary_file(self):
        source = self.other / "empryo" / "config"
        source.mkdir(parents=True)
        (source / "EMPRYO.md").write_text("new rules")
        self.git(self.other, "add", "-A")
        self.git(self.other, "commit", "-m", "config")
        self.git(self.other, "push", str(self.remote), "main")
        live = self.home / ".empryo"
        live.mkdir(parents=True, exist_ok=True)
        (live / "EMPRYO.md").write_text("old rules")
        (live / "EMPRYO.md.tmp").write_text("precious")
        self.write_config(configSync=["EMPRYO.md"])
        result = self.run_post(changed_files=["empryo/config/EMPRYO.md"])
        self.assertEqual(result["configSync"][0]["status"], "copied")
        self.assertEqual((live / "EMPRYO.md").read_text(), "new rules")
        self.assertEqual((live / "EMPRYO.md.tmp").read_text(), "precious",
                         "an existing temporary file is never written through")

    def test_the_config_sync_leaves_a_linked_file_alone(self):
        source = self.other / "empryo" / "config"
        source.mkdir(parents=True)
        (source / "EMPRYO.md").write_text("new rules")
        self.git(self.other, "add", "-A")
        self.git(self.other, "commit", "-m", "config")
        self.git(self.other, "push", str(self.remote), "main")
        live = self.home / ".empryo"
        live.mkdir(parents=True, exist_ok=True)
        (live / "elsewhere.md").write_text("keep")
        (live / "EMPRYO.md").symlink_to(live / "elsewhere.md")
        self.write_config(configSync=["EMPRYO.md"])
        result = self.run_post(changed_files=["empryo/config/EMPRYO.md"])
        self.assertEqual(result["configSync"][0]["status"], "skipped")
        self.assertIn("link", result["configSync"][0]["reason"])
        self.assertTrue((live / "EMPRYO.md").is_symlink())
        self.assertEqual((live / "elsewhere.md").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
