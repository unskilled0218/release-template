import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from release_template import cli
from release_template.core import ReleaseError, canonical, digest, load
from release_template.workflow import Workflow
from tests.support import COMMIT, REVISION, FakeGitea, FakeRegistry, FakeRunner, configuration, evidence, package


class CLITests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    (self.root / "release.json").write_text(json.dumps(configuration()))
    self.registry = FakeRegistry()
    self.gitea = FakeGitea(self.registry)
    self.runner = FakeRunner(self.registry)
    self.output, self.errors = io.StringIO(), io.StringIO()
    for target, replacement in (("credentials", ("fixture", "private-token")), ("Runner", self.runner),
                                ("Registry", self.registry), ("Gitea", self.gitea)):
      mock = patch.object(cli, target, return_value=replacement).start()
      self.addCleanup(patch.stopall)
      setattr(self, target, mock)

  def invoke(self, *arguments):
    with contextlib.redirect_stdout(self.output), contextlib.redirect_stderr(self.errors):
      return cli.main(self.root, REVISION, arguments)

  def test_validate_needs_no_credentials_or_remote_clients(self):
    self.assertEqual(self.invoke("validate"), 0)
    self.credentials.assert_not_called()
    self.Registry.assert_not_called()
    self.Gitea.assert_not_called()
    self.assertEqual(self.runner.calls, [])

  def test_legacy_and_mixed_configuration_fail_before_credentials_and_clients(self):
    valid = configuration()
    legacy = {key: value for key, value in valid.items() if key != "gitea"}
    legacy.update({"schema": 1, "forgejo": valid["gitea"]})
    for config in (legacy, valid | {"schema": 1}, valid | {"forgejo": valid["gitea"]}):
      for mode in ("validate", "publish", "resume", "cleanup-plan", "cleanup", "abandon"):
        with self.subTest(config=config, mode=mode):
          (self.root / "release.json").write_text(json.dumps(config))
          self.assertEqual(self.invoke(mode, "--tag", "v1.0.0"), 1)
          self.assertIn("migrate to schema 2", self.errors.getvalue())
          self.credentials.assert_not_called()
          self.Runner.assert_not_called()
          self.Registry.assert_not_called()
          self.Gitea.assert_not_called()
          self.assertFalse((self.root / ".release-template").exists())

  def test_publish_resume_and_cleanup_plan_report_recorded_success_without_enabling_deletion(self):
    self.assertEqual(self.invoke("publish", "--tag", "v1.0.0"), 1)
    self.assertIn("Publication succeeded; cleanup incomplete", self.errors.getvalue())
    self.assertTrue(self.gitea.release("v1.0.0"))
    self.assertEqual(self.invoke("resume", "--tag", "v1.0.0"), 1)
    self.assertEqual(self.invoke("cleanup-plan", "--tag", "v1.0.0"), 0)
    self.assertEqual(len([call for call in self.runner.calls if call[:3] == ["docker", "buildx", "build"]]), 1)
    self.assertEqual(self.gitea.deleted, [])
    self.assertNotIn("private-token", self.output.getvalue() + self.errors.getvalue())

  def test_platform_preflight_precedes_git_checks_tests_login_and_build(self):
    self.assertEqual(self.invoke("publish", "--tag", "v1.0.0"), 1)
    calls = self.runner.calls
    inspect = calls.index(["docker", "buildx", "inspect", "--bootstrap"])
    for index, call in enumerate(calls):
      if call[0] in ("git", "check-project") or call[:2] == ["docker", "login"] or call[:3] == ["docker", "buildx", "build"]:
        self.assertLess(inspect, index, repr(call))

  def test_missing_platform_fails_before_git_or_authentication(self):
    original = self.runner.run
    def run(arguments, **kwargs):
      if arguments[:3] == ["docker", "buildx", "inspect"]:
        self.runner.calls.append(arguments)
        return "Name: missing-arm\nPlatforms: linux/amd64\n"
      return original(arguments, **kwargs)
    self.runner.run = run
    self.assertEqual(self.invoke("publish", "--tag", "v1.0.0"), 1)
    self.assertFalse(any(call[0] == "git" or call[:2] == ["docker", "login"] for call in self.runner.calls))
    self.assertIn("missing-arm", self.errors.getvalue())

  def test_resume_refuses_missing_checkpoint(self):
    self.assertEqual(self.invoke("resume", "--tag", "v1.0.0"), 1)
    self.assertIn("existing verified release checkpoint", self.errors.getvalue())
    self.assertEqual(self.gitea.deleted, [])

  def test_abandon_confirmation_failure_reports_cleanup_incomplete_and_preserves_run(self):
    old = Workflow(self.root, configuration(), "0.9.0", REVISION, self.runner, self.registry, self.gitea, COMMIT)
    tag = "rt-" + old.state.data["run"] + "-application"
    root = self.registry.add("application", tag, "0.9.0")
    old.state.data["created"] -= 2 * 86400
    old.state.data["outputs"] = {"application": {"digest": root}}
    old.state.data["staging"] = {"application": {"tag": tag, "digest": root}}
    old.state.flush()
    before = old.state.path.read_bytes()
    self.gitea.package_records.append(package("application", tag))
    self.assertEqual(self.invoke("publish", "--tag", "v1.0.0"), 1)
    self.errors.seek(0)
    self.errors.truncate()
    path = evidence(self.root / "evidence.json")
    with patch.object(self.gitea, "delete_package", return_value=None):
      status = self.invoke("abandon", "--tag", "v1.0.0", "--run", old.state.data["run"],
                           "--minimum-age-days", "1", "--deletion-evidence", str(path))
    self.assertEqual(status, 1)
    self.assertIn("Publication succeeded; cleanup incomplete: Abandoned package deletion is not yet absent", self.errors.getvalue())
    self.assertEqual(old.state.path.read_bytes(), before)
    self.assertEqual(self.registry.resolve("application", tag), root)
    self.assertTrue(load(self.root / ".release-template/v1.0.0.json")["published"])

  def test_standalone_cli_refuses_test_http_without_contacting_loopback(self):
    config = configuration() | {"test_http": True, "gitea": "http://127.0.0.1:1", "registry": "127.0.0.1:1"}
    (self.root / "release.json").write_text(json.dumps(config))
    code = 'from pathlib import Path; import sys; from release_template.cli import main; raise SystemExit(main(Path(sys.argv[1]), "fixture", ["validate"]))'
    result = subprocess.run([sys.executable, "-B", "-c", code, str(self.root)], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parents[1])
    self.assertEqual(result.returncode, 1)
    self.assertIn("in-process test fixtures", result.stderr)

  def test_new_template_pin_rejects_old_checkpoint_without_mutation(self):
    self.assertEqual(self.invoke("publish", "--tag", "v1.0.0"), 1)
    checkpoint = self.root / ".release-template/v1.0.0.json"
    before = checkpoint.read_bytes()
    releases = json.loads(json.dumps(self.gitea.records))
    for mode in ("resume", "cleanup-plan", "cleanup"):
      with self.subTest(mode=mode):
        self.runner.calls.clear()
        with contextlib.redirect_stdout(self.output), contextlib.redirect_stderr(self.errors):
          status = cli.main(self.root, "c" * 40, [mode, "--tag", "v1.0.0"])
        self.assertEqual(status, 1)
        self.assertIn("Checkpoint identity differs", self.errors.getvalue())
        self.assertEqual(checkpoint.read_bytes(), before)
        self.assertEqual(self.gitea.records, releases)
        self.assertEqual(self.gitea.deleted, [])
        self.assertFalse(any(call[:2] in (["docker", "login"], ["git", "push"]) or
          call[:3] == ["docker", "buildx", "build"] or
          call[:4] == ["docker", "buildx", "imagetools", "create"] for call in self.runner.calls))

  def test_same_revision_cleanup_retry_revalidates_and_retires_staging(self):
    self.assertEqual(self.invoke("publish", "--tag", "v1.0.0"), 1)
    checkpoint = json.loads((self.root / ".release-template/v1.0.0.json").read_text())
    staging = checkpoint["staging"]["application"]["tag"]
    self.gitea.package_records.append(package("application", staging))
    evidence_path = evidence(self.root / "evidence.json")
    self.assertEqual(self.invoke("cleanup", "--tag", "v1.0.0", "--deletion-evidence", str(evidence_path)), 0)
    self.assertEqual(self.gitea.deleted, [("package", "application", staging)])
    self.assertEqual(self.invoke("cleanup", "--tag", "v1.0.0", "--deletion-evidence", str(evidence_path)), 0)
    self.assertEqual(len(self.gitea.deleted), 1)

  def test_old_configuration_checkpoint_is_not_adopted_under_schema_two(self):
    self.assertEqual(self.invoke("publish", "--tag", "v1.0.0"), 1)
    path = self.root / ".release-template/v1.0.0.json"
    state = json.loads(path.read_text())
    old_config = configuration()
    old_config["forgejo"] = old_config.pop("gitea")
    old_config["schema"] = 1
    state["identity"]["config"] = digest(canonical(old_config))
    path.write_text(json.dumps(state))
    before = path.read_bytes()
    releases = json.loads(json.dumps(self.gitea.records))
    aliases = dict(self.registry.aliases)
    for mode in ("resume", "cleanup-plan", "cleanup"):
      with self.subTest(mode=mode):
        self.runner.calls.clear()
        self.assertEqual(self.invoke(mode, "--tag", "v1.0.0"), 1)
        self.assertIn("Checkpoint identity differs", self.errors.getvalue())
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.gitea.records, releases)
        self.assertEqual(self.registry.aliases, aliases)
        self.assertEqual(self.gitea.deleted, [])
        self.assertFalse(any(call[:2] in (["docker", "login"], ["git", "push"]) or
          call[:3] == ["docker", "buildx", "build"] or
          call[:4] == ["docker", "buildx", "imagetools", "create"] for call in self.runner.calls))
