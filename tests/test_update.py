import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import update
from launch import DestinationLock, verify
from release_template.core import ReleaseError, atomic_bytes


class UpdateTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.source, self.destination = self.root / "source", self.root / "consumer"
    self.source.mkdir()
    self.destination.mkdir()
    for name in ("release_template", "scripts"):
      shutil.copytree(ROOT / name, self.source / name, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(ROOT / "VERSION", self.source / "VERSION")
    self.git("init", "-b", "main")
    self.commit()

  def git(self, *arguments):
    environment = os.environ | {"GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                               "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
    return subprocess.check_output(["git", *arguments], cwd=self.source, env=environment, stderr=subprocess.DEVNULL).decode().strip()

  def commit(self):
    self.git("add", ".")
    self.git("commit", "-m", "Fixture revision")
    self.revision = self.git("rev-parse", "HEAD")

  def inventory(self):
    return update.source_inventory(self.source, self.revision)

  def install(self):
    with DestinationLock(self.destination):
      return update.transaction(self.destination, *self.inventory())

  def test_install_verify_and_dry_run_leave_consumer_configuration_alone(self):
    custom = self.destination / "release.json"
    custom.write_text('{"custom":"keep"}')
    with DestinationLock(self.destination):
      report = update.transaction(self.destination, *self.inventory(), dry_run=True)
      self.assertIn("scripts/launch.py", report["replace"])
      self.assertFalse((self.destination / "scripts").exists())
    self.install()
    record = verify(self.destination)
    self.assertEqual(record["revision"], self.revision)
    self.assertEqual(custom.read_text(), '{"custom":"keep"}')
    launcher = self.destination / "scripts/release.sh"
    self.assertTrue(launcher.stat().st_mode & 0o100)

  def test_mutable_revision_and_modified_managed_files_are_refused(self):
    with self.assertRaisesRegex(ReleaseError, "immutable"):
      update.source_inventory(self.source, "main")
    self.install()
    managed = self.destination / "scripts/release-template/release_template/__init__.py"
    managed.write_text("user work")
    with self.assertRaises(RuntimeError):
      self.install()
    self.assertEqual(managed.read_text(), "user work")

  def test_upstream_removal_prunes_only_owned_unchanged_files(self):
    extra = self.source / "release_template/obsolete.py"
    extra.write_text('"""Obsolete fixture module."""\n')
    self.commit()
    self.install()
    installed = self.destination / "scripts/release-template/release_template/obsolete.py"
    self.assertTrue(installed.exists())
    extra.unlink()
    self.commit()
    self.install()
    self.assertFalse(installed.exists())
    self.assertEqual(verify(self.destination)["revision"], self.revision)

  def test_interrupt_each_destination_write_recovers_completion_and_refuses_release_import(self):
    files, bootstrap, lock = self.inventory()
    total_writes = len(files) + len(bootstrap) + 1
    for boundary in range(1, total_writes + 1):
      with self.subTest(boundary=boundary), tempfile.TemporaryDirectory(dir=self.root) as temporary:
        destination = Path(temporary)
        seen = 0
        def interrupted(path, data, mode=0o600):
          nonlocal seen
          atomic_bytes(path, data, mode)
          if ".template-transaction" not in str(path):
            seen += 1
            if seen == boundary:
              raise SystemExit("Simulated process termination after durable file replacement")
        with DestinationLock(destination):
          with patch.object(update, "atomic_bytes", side_effect=interrupted), self.assertRaises(SystemExit):
            update.transaction(destination, files, bootstrap, lock)
          with self.assertRaisesRegex(RuntimeError, "Incomplete"):
            verify(destination)
          update.recover(destination, "complete")
          self.assertEqual(verify(destination)["revision"], self.revision)

  def test_interrupted_initial_install_can_restore_without_overwriting_user_changes(self):
    calls = 0
    def interrupted(path, data, mode=0o600):
      nonlocal calls
      atomic_bytes(path, data, mode)
      if ".template-transaction" not in str(path):
        calls += 1
        if calls == 3:
          raise SystemExit()
    with patch.object(update, "atomic_bytes", side_effect=interrupted), self.assertRaises(SystemExit):
      self.install()
    journal = update.load(self.destination / ".template-transaction/journal.json")
    written = next(self.destination / entry["path"] for entry in journal["entries"] if (self.destination / entry["path"]).is_file())
    before = written.read_bytes()
    written.write_text("user work")
    with self.assertRaisesRegex(ReleaseError, "User changes"):
      update.recover(self.destination, "restore")
    self.assertEqual(written.read_text(), "user work")
    written.write_bytes(before)
    update.recover(self.destination, "restore")
    self.assertFalse((self.destination / "release-template.lock.json").exists())
    self.assertFalse((self.destination / ".template-transaction").exists())
    self.assertFalse((self.destination / "scripts/release-template").exists())

  def test_update_and_release_share_a_destination_lock(self):
    with DestinationLock(self.destination):
      with self.assertRaisesRegex(RuntimeError, "Another"):
        with DestinationLock(self.destination):
          self.fail("Concurrent update/release acquired the same lock")

  def test_interrupted_existing_update_restores_old_inventory_and_preserves_config(self):
    self.install()
    old_lock = verify(self.destination)
    custom = self.destination / "release.json"
    custom.write_text("user configuration")
    source_file = self.source / "release_template/__init__.py"
    source_file.write_text(source_file.read_text() + "\n# New revision fixture\n")
    self.commit()
    seen = 0
    def interrupted(path, data, mode=0o600):
      nonlocal seen
      atomic_bytes(path, data, mode)
      if ".template-transaction" not in str(path):
        seen += 1
        if str(path).endswith("release-template.lock.json"):
          raise SystemExit()
    with patch.object(update, "atomic_bytes", side_effect=interrupted), self.assertRaises(SystemExit):
      self.install()
    update.recover(self.destination, "restore")
    self.assertEqual(verify(self.destination), old_lock)
    self.assertEqual(custom.read_text(), "user configuration")

  def test_unknown_extra_files_and_bootstrap_changes_refuse_update(self):
    self.install()
    extra = self.destination / "scripts/release-template/untracked.py"
    extra.write_text("user work")
    with self.assertRaises(RuntimeError):
      self.install()
    extra.unlink()
    launcher = self.source / "scripts/launch.py"
    launcher.write_text(launcher.read_text() + "\n# Changed bootstrap fixture\n")
    self.commit()
    with self.assertRaisesRegex(ReleaseError, "Bootstrap"):
      self.install()

  def test_install_refuses_symlink_escape_and_existing_untracked_launcher(self):
    (self.destination / "scripts").symlink_to(self.source / "scripts", target_is_directory=True)
    with self.assertRaises(ReleaseError):
      self.install()
    (self.destination / "scripts").unlink()
    (self.destination / "scripts").mkdir()
    (self.destination / "scripts/launch.py").write_text("user work")
    with self.assertRaises(ReleaseError):
      self.install()

  def test_installed_launcher_refuses_corrupt_inventory_before_engine_import(self):
    self.install()
    managed = self.destination / "scripts/release-template/release_template/cli.py"
    marker = self.destination / "unsafe-import"
    managed.write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
    environment = os.environ | {"PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, str(self.destination / "scripts/launch.py"), "validate"],
                            capture_output=True, text=True, env=environment)
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("inventory", result.stderr)
    self.assertFalse(marker.exists())

  def test_installed_launcher_validates_configuration_without_creating_bytecode_or_reading_credentials(self):
    from tests.support import configuration
    import json
    self.install()
    (self.destination / "release.json").write_text(json.dumps(configuration()))
    result = subprocess.run([sys.executable, str(self.destination / "scripts/launch.py"), "validate"],
                            capture_output=True, text=True,
                            env=os.environ | {"FORGEJO_TOKEN": "/never-read-fixture-token"})
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("no credentials", result.stdout)
    self.assertFalse(list((self.destination / "scripts/release-template").rglob("*.pyc")))
    self.assertEqual(verify(self.destination)["revision"], self.revision)
