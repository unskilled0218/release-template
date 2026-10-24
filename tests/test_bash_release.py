"""Exercise the Bash entry point without credentials, Docker, or production services."""

import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import time


ROOT = Path(__file__).resolve().parents[1]


class BashInterfaceTests(unittest.TestCase):
  def test_help_describes_no_argument_release(self):
    result = subprocess.run(["bash", str(ROOT / "scripts/release.sh"), "--help"], capture_output=True, text=True)
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("No arguments: build and publish", result.stdout)

  def test_validate_needs_no_credentials_or_remote_operations(self):
    environment = os.environ | {"GIT_TOKEN": "/missing/must-not-be-read"}
    result = subprocess.run(["bash", str(ROOT / "scripts/release.sh"), "--validate"], env=environment,
                            capture_output=True, text=True)
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("no credentials or remote operations", result.stdout)

  def test_old_options_refuse_with_supported_usage(self):
    result = subprocess.run(["bash", str(ROOT / "scripts/release.sh"), "publish"], capture_output=True, text=True)
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("Usage: ./scripts/release.sh [--validate | --help]", result.stderr)
    self.assertNotIn("legacy-release.sh", result.stderr)

  def test_supported_tree_has_no_retired_tooling_or_imports(self):
    for name in ("release_template", "examples", "scripts/launch.py", "scripts/update.py",
                 "scripts/legacy-release.sh", "tests/support.py"):
      with self.subTest(path=name):
        self.assertFalse((ROOT / name).exists())
        self.assertFalse((ROOT / name).is_symlink())
    for directory in ("scripts", "tests"):
      for path in (ROOT / directory).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
          imports = [alias.name for alias in node.names] if isinstance(node, ast.Import) else \
                    [node.module or ""] if isinstance(node, ast.ImportFrom) else []
          self.assertFalse(any(name.split(".")[0] == "release_template" or name == "tests.support"
                               for name in imports), str(path))

  def test_root_version_drives_settings_readme_and_notes(self):
    config = helper_module().settings(ROOT)
    version = (ROOT / "VERSION").read_text().strip()
    self.assertEqual(config["version"], version)
    self.assertEqual(config["tag"], "v" + version)
    self.assertEqual(config["notes"], "docs/releases/" + version + ".md")
    self.assertTrue((ROOT / config["notes"]).read_text().startswith("# Release v" + version + "\n"))
    readme = (ROOT / "README.md").read_text()
    self.assertIn("Version " + version, readme)
    self.assertIn("](docs/releases/" + version + ".md)", readme)


def helper_module():
  spec = importlib.util.spec_from_file_location("bash_release_data", ROOT / "scripts/release-data.py")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


class BashPublicationTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory(prefix="bash-release-test-", dir="/tmp/opencode" if Path("/tmp/opencode").is_dir() else None)
    self.addCleanup(self.temporary.cleanup)
    self.base = Path(self.temporary.name)
    self.root, self.bin = self.base / "project", self.base / "bin"
    self.root.mkdir()
    self.bin.mkdir()
    (self.root / "scripts").mkdir()
    for name in ("release.sh", "release-common.sh", "release-data.py", "release.json"):
      shutil.copyfile(ROOT / "scripts" / name, self.root / "scripts" / name)
    for name in ("Dockerfile", ".dockerignore", ".gitignore"):
      shutil.copyfile(ROOT / name, self.root / name)
    (self.root / "VERSION").write_text("1.0.0\n")
    (self.root / "notes.md").write_text("# Release v1.0.0\n\nProject changes.\n")
    self.token = self.base / "token"
    self.token.write_text("SENTINEL_PRIVATE_TOKEN\n")
    self.token.chmod(0o600)
    config = json.loads((self.root / "scripts/release.json").read_text())
    config |= {"repository": "fixtures/application", "image": "git.lan/fixtures/application",
               "notes": "notes.md", "token_file": str(self.token)}
    (self.root / "scripts/release.json").write_text(json.dumps(config))
    self.state_path = self.base / "state.json"
    self.state_path.write_text(json.dumps({"objects": {}, "aliases": {}, "releases": []}))
    self.environment = os.environ | {"GIT_AUTHOR_NAME": "Fixture", "GIT_COMMITTER_NAME": "Fixture",
      "GIT_AUTHOR_EMAIL": "fixture@localhost", "GIT_COMMITTER_EMAIL": "fixture@localhost",
      "BASH_TEST_STATE": str(self.base), "PATH": str(self.bin) + ":" + os.environ["PATH"],
      "TMPDIR": str(self.base), "HOME": str(self.base)}
    for key in ("GIT_TOKEN", "GIT_USERNAME", "RELEASE_LOCK_FD", "DOCKER_CONTEXT", "DOCKER_CONFIG", "BUILDX_CONFIG",
                "DOCKER_HOST", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "BUILDX_BUILDER"):
      self.environment.pop(key, None)
    port = ROOT / "tests/fixtures/bash_release_ports.py"
    for name in ("git", "curl", "docker"):
      target = self.bin / name
      shutil.copyfile(port, target)
      target.chmod(0o755)
    self.git("init", "--quiet", "--initial-branch=main")
    self.git("init", "--bare", "--quiet", str(self.base / "remote.git"))
    self.git("remote", "add", "origin", str(self.base / "remote.git"))
    self.commit()

  def git(self, *args):
    return subprocess.check_output(["/usr/bin/git", "-C", str(self.root), *args], env=self.environment,
                                   stderr=subprocess.DEVNULL).decode().strip()

  def commit(self):
    self.git("add", ".")
    self.git("commit", "--quiet", "-m", "Fixture")
    self.git("push", "--quiet", "origin", "HEAD:main")

  def state(self):
    return json.loads(self.state_path.read_text())

  def change(self, **values):
    self.state_path.write_text(json.dumps(self.state() | values))

  def events(self):
    path = self.base / "events"
    return path.read_text().splitlines() if path.exists() else []

  def release(self, *args):
    result = subprocess.run(["bash", str(self.root / "scripts/release.sh"), *args], cwd=self.base,
                            env=self.environment, capture_output=True, text=True, timeout=90)
    self.assertNotIn("SENTINEL_PRIVATE_TOKEN", result.stdout + result.stderr)
    self.assertEqual(list(self.base.glob("bash-release.*")), [], "Only run-owned temporary paths must be cleaned")
    return result

  def assert_no_writes(self):
    self.assertFalse(set(self.events()) & {"build", "tag-push", "promote", "release-post"}, self.events())

  def predecessor(self):
    data = helper_module()
    body = data.canonical({"previous": "verified fixture alias"})
    reference = data.sha(body)
    state = self.state()
    state["objects"][reference] = body.decode()
    state["aliases"]["latest"] = reference
    self.change(**state)
    return reference

  def connection(self, context=None, host=None, configured=None, explicit_builder=False):
    directory = self.base / "original-docker"
    directory.mkdir(exist_ok=True)
    config = {"auths": {"foreign.invalid": {"auth": "UNRELATED_AUTH_SENTINEL"}},
              "credsStore": "must-not-run", "credHelpers": {"foreign.invalid": "must-not-run"}}
    if configured:
      config["currentContext"] = configured
    (directory / "config.json").write_text(json.dumps(config))
    named = context if context and context != "default" else configured
    if named:
      metadata = directory / "contexts/meta/fixture-id/meta.json"
      metadata.parent.mkdir(parents=True, exist_ok=True)
      metadata.write_text(json.dumps({"Name": named, "Endpoints": {"docker": {"Host": "tcp://context.fixture.invalid:2376"}}}))
      tls = directory / "contexts/tls/fixture-id/docker/ca.pem"
      tls.parent.mkdir(parents=True, exist_ok=True)
      tls.write_text("fixture-ca")
    buildx = self.base / "selected-buildx" if explicit_builder else directory / "buildx"
    buildx.mkdir(exist_ok=True)
    (buildx / "current").write_text(json.dumps({"Name": "fixture-builder"}))
    self.environment["DOCKER_CONFIG"] = str(directory)
    if context is not None:
      self.environment["DOCKER_CONTEXT"] = context
    else:
      self.environment.pop("DOCKER_CONTEXT", None)
    if host:
      self.environment["DOCKER_HOST"] = host
    else:
      self.environment.pop("DOCKER_HOST", None)
    certificates = self.base / "host-certificates"
    certificates.mkdir(exist_ok=True)
    (certificates / "ca.pem").write_text("fixture-host-ca")
    if host or named:
      self.environment |= {"DOCKER_TLS_VERIFY": "1", "DOCKER_CERT_PATH": str(certificates)}
    else:
      self.environment.pop("DOCKER_TLS_VERIFY", None)
      self.environment.pop("DOCKER_CERT_PATH", None)
    if explicit_builder:
      self.environment["BUILDX_CONFIG"] = str(buildx)
    else:
      self.environment.pop("BUILDX_CONFIG", None)
    return directory

  def assert_connection_preserved(self, expected_endpoint, expected_builder="fixture-builder"):
    selections = [json.loads(line) for line in (self.base / "docker-selections").read_text().splitlines()]
    operations = {tuple(row["operation"]) for row in selections}
    self.assertTrue({("buildx", "inspect"), ("login", "git.lan"), ("buildx", "build"), ("buildx", "imagetools")} <= operations)
    self.assertEqual({row["endpoint"] for row in selections}, {expected_endpoint})
    self.assertEqual({row["builder"] for row in selections}, {expected_builder})
    self.assertEqual({row["tls_verify"] for row in selections}, {self.environment.get("DOCKER_TLS_VERIFY")})
    self.assertEqual({row["cert_path"] for row in selections}, {self.environment.get("DOCKER_CERT_PATH")})

  def assert_promotion_read_refuses(self, fault):
    predecessor = self.predecessor()
    self.change(promotion_read_fault=fault)
    result = self.release()
    events = self.events()
    injection = "promotion-read-injected:" + fault
    self.assertIn(injection, events, "The precise post-guard read must receive the fault")
    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertNotIn("Publication verified", result.stdout)
    self.assertFalse(set(events[events.index(injection) + 1:]) & {"build", "tag-push", "promote", "release-post"})
    self.assertEqual(events.count("build"), 1)
    self.assertEqual(events.count("tag-push"), 1)
    self.assertEqual(self.state()["aliases"]["latest"], predecessor)
    self.assertEqual(self.state()["releases"], [])

  def assert_tag_change_refuses(self, stage, kind="absent"):
    predecessor = self.predecessor()
    self.change(tag_change={"stage": stage, "kind": kind})
    result = self.release()
    events = self.events()
    injection = "tag-change:" + stage + ":" + kind
    self.assertIn(injection, events)
    self.assertLess(events.index("tag-confirmed"), events.index(injection))
    self.assertNotEqual(result.returncode, 0)
    self.assertNotIn("Publication verified", result.stdout)
    self.assertFalse(set(events[events.index(injection) + 1:]) & {"build", "tag-push", "promote", "release-post"})
    self.assertEqual(events.count("tag-push"), 1)
    self.assertEqual(events.count("promote"), int(stage == "before_release"))
    self.assertEqual(events.count("release-post"), 0)
    self.assertEqual(self.state()["aliases"]["latest"], self.state()["prepared"] if stage == "before_release" else predecessor)
    if kind == "absent":
      self.assertEqual(self.git("ls-remote", "--tags", "origin", "refs/tags/v1.0.0"), "")
    annotation = self.git("cat-file", "tag", self.state()["confirmed_object"])
    identity = json.loads(annotation.split("\n\n", 1)[1].split("\n", 1)[1])
    self.assertEqual(identity["digest"], self.state()["prepared"])
    self.assertEqual(identity["predecessor"], predecessor)
    self.assertEqual(identity["commit"], self.git("rev-parse", "HEAD"))

  def test_promotion_read_overflow_blocks_later_writes(self):
    self.assert_promotion_read_refuses("overflow")

  def test_promotion_read_malformed_json_blocks_later_writes(self):
    self.assert_promotion_read_refuses("malformed")

  def test_promotion_read_null_blocks_later_writes(self):
    self.assert_promotion_read_refuses("null")

  def test_promotion_read_unauthorized_blocks_later_writes(self):
    self.assert_promotion_read_refuses("unauthorized")

  def test_promotion_read_server_error_blocks_later_writes(self):
    self.assert_promotion_read_refuses("server_error")

  def test_promotion_read_transport_failure_blocks_later_writes(self):
    self.assert_promotion_read_refuses("transport")

  def test_promotion_read_timeout_failure_blocks_later_writes(self):
    self.assert_promotion_read_refuses("timeout")

  def test_promotion_read_foreign_alias_is_not_overwritten(self):
    predecessor = self.predecessor()
    self.change(promotion_read_fault="foreign")
    result = self.release()
    events = self.events()
    self.assertIn("promotion-read-injected:foreign", events)
    self.assertNotEqual(result.returncode, 0)
    self.assertNotIn("promote", events)
    self.assertNotIn("release-post", events)
    self.assertNotIn(self.state()["aliases"]["latest"], (predecessor, self.state()["prepared"]))

  def test_promotion_read_prepared_alias_skips_duplicate_promotion(self):
    self.change(promotion_read_fault="prepared")
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("promotion-read-injected:prepared", self.events())
    self.assertNotIn("promote", self.events())
    self.assertEqual(self.events().count("release-post"), 1)

  def test_confirmed_tag_disappearance_stops_before_promotion(self):
    self.assert_tag_change_refuses("before_promotion")

  def test_confirmed_tag_disappearance_after_promotion_stops_before_release(self):
    self.assert_tag_change_refuses("before_release")

  def test_confirmed_tag_lightweight_replacement_refuses(self):
    self.assert_tag_change_refuses("before_promotion", "lightweight")

  def test_confirmed_tag_foreign_annotation_refuses(self):
    self.assert_tag_change_refuses("before_promotion", "changed")

  def test_confirmed_tag_wrong_peeled_commit_refuses(self):
    self.assert_tag_change_refuses("before_promotion", "wrong_peel")

  def test_host_only_connection_is_preserved(self):
    self.connection(host="tcp://host.fixture.invalid:2376")
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assert_connection_preserved("tcp://host.fixture.invalid:2376")

  def test_empty_context_preserves_host_connection(self):
    self.connection(context="", host="tcp://host.fixture.invalid:2376", explicit_builder=True)
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assert_connection_preserved("tcp://host.fixture.invalid:2376")

  def test_config_selected_named_context_is_preserved(self):
    self.connection(configured="remote-builder")
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assert_connection_preserved("tcp://context.fixture.invalid:2376")

  def test_explicit_named_context_keeps_precedence_over_host(self):
    self.connection(context="remote-builder", host="tcp://ignored.fixture.invalid:2376", explicit_builder=True)
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assert_connection_preserved("tcp://context.fixture.invalid:2376")

  def test_explicit_default_context_keeps_precedence_over_host(self):
    self.connection(context="default", host="tcp://ignored.fixture.invalid:2376")
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assert_connection_preserved("unix:///var/run/docker.sock")

  def test_default_connection_and_builder_are_preserved(self):
    self.connection()
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assert_connection_preserved("unix:///var/run/docker.sock")

  def test_relative_host_cert_and_buildx_paths_are_preserved(self):
    self.connection(host="tcp://host.fixture.invalid:2376", explicit_builder=True)
    for key in ("DOCKER_CONFIG", "DOCKER_CERT_PATH", "BUILDX_CONFIG"):
      self.environment[key] = str(Path(self.environment[key]).relative_to(self.base))
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assert_connection_preserved("tcp://host.fixture.invalid:2376")

  def test_empty_docker_config_uses_home_context_metadata(self):
    directory = self.connection(configured="remote-builder")
    directory.rename(self.base / ".docker")
    self.environment["DOCKER_CONFIG"] = ""
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assert_connection_preserved("tcp://context.fixture.invalid:2376")

  def test_explicit_builder_selection_is_preserved(self):
    self.connection(host="tcp://host.fixture.invalid:2376")
    self.environment["BUILDX_BUILDER"] = "environment-builder"
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assert_connection_preserved("tcp://host.fixture.invalid:2376", "environment-builder")

  def test_unusable_named_context_does_not_fall_back_or_publish(self):
    directory = self.connection(configured="remote-builder")
    (directory / "contexts/tls/fixture-id/docker/ca.pem").unlink()
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assert_no_writes()

  def test_publish_and_completed_retry_ignore_missing_or_foreign_staging(self):
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("Publication verified: v1.0.0", result.stdout)
    for action in ("build", "tag-push", "promote", "release-post"):
      self.assertEqual(self.events().count(action), 1, action)
    state = self.state()
    self.assertEqual(state["releases"][0]["body"], "# Release v1.0.0\n\nProject changes.\n")
    oid = self.git("ls-remote", "--tags", "origin", "refs/tags/v1.0.0").split()[0]
    staging = next(name for name in state["aliases"] if name.startswith("rt-"))
    for aliases in ({"latest": state["prepared"]}, {"latest": state["prepared"], staging: "sha256:" + "0" * 64}):
      self.change(aliases=aliases)
      (self.base / "events").write_text("")
      result = self.release()
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assert_no_writes()
      self.assertFalse(any(e.startswith("registry:rt-") for e in self.events()))
      self.assertEqual(self.git("ls-remote", "--tags", "origin", "refs/tags/v1.0.0").split()[0], oid)

  def test_tag_only_startup_refuses_before_staging_or_build(self):
    self.change(fail_release=True)
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("Release creation not confirmed", result.stderr)
    (self.base / "events").write_text("")
    self.change(fail_release=False)
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("Ambiguous", result.stderr)
    self.assert_no_writes()
    self.assertFalse(any(e.startswith("registry:") for e in self.events()))

  def test_release_only_startup_refuses_before_build(self):
    self.change(releases=[{"id": 1, "tag_name": "v1.0.0", "draft": False, "prerelease": False}])
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("Ambiguous", result.stderr)
    self.assert_no_writes()

  def test_lost_accepted_responses_are_reconciled_without_duplicate_writes(self):
    self.change(lose_tag=True, lose_promotion=True, lose_release=True)
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    for action in ("build", "tag-push", "promote", "release-post"):
      self.assertEqual(self.events().count(action), 1, action)

  def test_unbound_interrupted_build_reuses_verified_staging(self):
    self.change(lose_build=True)
    self.assertNotEqual(self.release().returncode, 0)
    self.change(lose_build=False)
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(self.events().count("build"), 1)

  def test_preflight_refusals_do_not_write(self):
    for flag in ("wrong_remote", "wrong_main", "unsupported", "null_inventory", "malformed", "oversized", "realm_foreign"):
      with self.subTest(flag=flag):
        self.change(**{flag: True})
        self.assertNotEqual(self.release().returncode, 0)
        self.assert_no_writes()
        self.change(**{flag: False})
    for status in (401, 500):
      self.change(status=status)
      self.assertNotEqual(self.release().returncode, 0)
      self.assert_no_writes()
    self.change(status=None)

  def test_dirty_source_and_unsafe_credentials_stop_before_build(self):
    (self.root / "untracked").write_text("user work")
    self.assertNotEqual(self.release().returncode, 0)
    (self.root / "untracked").unlink()
    self.token.chmod(0o644)
    self.assertNotEqual(self.release().returncode, 0)
    self.assert_no_writes()

  def test_invalid_config_and_local_validation_do_not_read_token(self):
    self.token.unlink()
    result = self.release("--validate")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(self.events(), [])
    path = self.root / "scripts/release.json"
    original = path.read_text()
    for text in (original[:-1] + ',"schema":1}', original[:-1] + ',"extra":true}', '{"schema":null}', '{'):
      path.write_text(text)
      self.assertNotEqual(self.release("--validate").returncode, 0)
    self.assertEqual(self.events(), [])

  def test_legacy_markers_and_non_main_refuse(self):
    for name in ("release-template.lock.json", "scripts/release-template", ".template-transaction", ".release-template/v1.0.0.json"):
      path = self.root / name
      path.parent.mkdir(exist_ok=True)
      if name == "scripts/release-template":
        path.mkdir()
      else:
        path.write_text("legacy")
      result = self.release()
      self.assertNotEqual(result.returncode, 0)
      self.assertNotIn("legacy-release.sh", result.stderr)
      self.assertIn("original", result.stderr)
      self.assert_no_writes()
      if path.is_dir():
        path.rmdir()
      else:
        path.unlink()
    self.git("switch", "--quiet", "-c", "task")
    self.assertNotEqual(self.release().returncode, 0)
    self.assert_no_writes()

  def test_unsupported_options_refuse_before_credentials_or_commands(self):
    self.token.unlink()
    for arguments in (("publish",), ("resume",), ("--config", "missing.json"), ("--unknown",)):
      with self.subTest(arguments=arguments):
        result = self.release(*arguments)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stderr)
        self.assertNotIn("legacy-release.sh", result.stderr)
        self.assertEqual(self.events(), [])
        self.assertFalse((self.root / ".template-operation.lock").exists())

  def test_old_marker_symlinks_refuse_without_touching_targets(self):
    for name in ("release-template.lock.json", "scripts/release-template", ".template-transaction", ".release-template/v1.0.0.json"):
      for target in (self.token, self.base / "missing-old-state"):
        with self.subTest(marker=name, target=target.name):
          path = self.root / name
          path.parent.mkdir(exist_ok=True)
          path.symlink_to(target)
          result = self.release()
          self.assertNotEqual(result.returncode, 0)
          self.assertIn("original", result.stderr)
          self.assertNotIn("legacy-release.sh", result.stderr)
          self.assertTrue(path.is_symlink())
          self.assertEqual(self.token.read_text(), "SENTINEL_PRIVATE_TOKEN\n")
          self.assert_no_writes()
          path.unlink()

  def test_notes_use_literal_committed_blobs_and_narrow_normalization(self):
    data = helper_module()
    raw = b"# Release v1.0.0\r\n\r\nProject  fixes.\rKeep spaces.  \r\n\r\n"
    literal = "notes with space*.md"
    (self.root / literal).write_bytes(raw)
    (self.root / "notes-link.md").symlink_to("notes.md")
    self.commit()
    commit = self.git("rev-parse", "HEAD")
    config = data.settings(self.root) | {"notes": literal}
    (self.root / literal).write_text("Uncommitted replacement")
    self.assertEqual(data.blob(self.root, commit, literal), raw)
    self.assertEqual(data.notes(self.root, commit, config), "# Release v1.0.0\n\nProject  fixes.\nKeep spaces.  \n")
    for name in ("notes-link.md", "scripts", "notes with space?.md"):
      with self.subTest(path=name), self.assertRaises(data.Refusal):
        data.blob(self.root, commit, name)

  def test_notes_invalid_utf8_content_and_size_refuse(self):
    data = helper_module()
    config = data.settings(self.root)
    for raw in (b"\xff", b"# Release v1.0.0\n", b"# Release v1.0.0\n\nBad\x00text\n", b"x" * 65537):
      with self.subTest(content=raw[:30]):
        (self.root / "notes.md").write_bytes(raw)
        self.commit()
        with self.assertRaises((data.Refusal, UnicodeError)):
          data.notes(self.root, self.git("rev-parse", "HEAD"), config)

  def test_annotation_roundtrip_is_deterministic_and_conflicts_refuse(self):
    data = helper_module()
    commit = self.git("rev-parse", "HEAD")
    config = data.settings(self.root)
    identity = data.base_identity(self.root, commit, config) | {"digest": "sha256:" + "a" * 64, "predecessor": None}
    oid = data.create_tag(self.root, identity)
    self.assertEqual(data.create_tag(self.root, identity), oid)
    self.assertEqual(data.inspect_tag(self.root, commit, oid, config), identity)
    self.assertEqual(self.git("cat-file", "tag", oid).encode() + b"\n", data.tag_bytes(identity))
    self.assertEqual(self.git("tag", "--list"), "")
    for change in ({"extra": True}, {"repository": "foreign/project"}, {"digest": "latest"}, {"predecessor": "bad"}):
      with self.subTest(change=change), self.assertRaises(data.Refusal):
        foreign = data.create_tag(self.root, identity | change)
        data.inspect_tag(self.root, commit, foreign, config)
    self.git("tag", "v1.0.0")
    with self.assertRaisesRegex(data.Refusal, "Local tag conflicts"):
      data.create_tag(self.root, identity)

  def test_newer_publication_and_repeated_pages_refuse(self):
    self.change(releases=[{"id": 2, "tag_name": "v2.0.0", "draft": False, "prerelease": False}])
    self.assertNotEqual(self.release().returncode, 0)
    self.assert_no_writes()
    self.change(releases=[{"id": 1, "tag_name": "v0.9.0", "draft": False, "prerelease": False}], repeat_pages=True)
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("Pagination did not advance", result.stderr)
    self.assert_no_writes()

  def test_bad_build_metadata_stops_before_tag_and_promotion(self):
    self.change(bad_metadata=True)
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertEqual(self.events().count("build"), 1)
    self.assertFalse(set(self.events()) & {"tag-push", "promote", "release-post"})

  def test_completed_missing_bound_content_or_final_alias_never_repairs(self):
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    original = self.state()
    for aliases, objects in (({}, original["objects"]),
                             ({"latest": "sha256:" + "a" * 64}, original["objects"]),
                             (original["aliases"], {})):
      with self.subTest(aliases=aliases):
        self.change(aliases=aliases, objects=objects)
        (self.base / "events").write_text("")
        self.assertNotEqual(self.release().returncode, 0)
        self.assert_no_writes()
    self.change(**original)

  def test_completed_changed_body_or_local_tag_refuses(self):
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    records = self.state()["releases"]
    self.change(releases=[records[0] | {"body": "Foreign body"}])
    (self.base / "events").write_text("")
    self.assertNotEqual(self.release().returncode, 0)
    self.assert_no_writes()
    self.change(releases=records)
    self.git("tag", "v1.0.0")
    self.assertNotEqual(self.release().returncode, 0)
    self.assert_no_writes()

  def test_source_change_does_not_adopt_old_publication(self):
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    (self.root / "new-source").write_text("Different source\n")
    self.commit()
    (self.base / "events").write_text("")
    self.assertNotEqual(self.release().returncode, 0)
    self.assert_no_writes()

  def test_local_tag_conflict_refuses_before_build(self):
    self.git("tag", "v1.0.0")
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("Local tag", result.stderr)
    self.assert_no_writes()

  def test_captured_external_symlink_never_enters_build(self):
    (self.root / "escape").symlink_to(self.token)
    self.commit()
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("symlink escapes", result.stderr)
    self.assert_no_writes()

  def test_lock_symlink_and_other_lock_owner_refuse(self):
    lock = self.root / ".template-operation.lock"
    lock.symlink_to(self.token)
    self.assertNotEqual(self.release().returncode, 0)
    self.assertEqual(self.token.read_text(), "SENTINEL_PRIVATE_TOKEN\n")
    lock.unlink()
    import fcntl
    with lock.open("w") as held:
      fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
      self.assertNotEqual(self.release().returncode, 0)
    self.assert_no_writes()

  def test_ignored_worktree_secret_is_not_in_committed_snapshot(self):
    with (self.root / ".gitignore").open("a") as output:
      output.write("ignored-secret\n")
    self.commit()
    (self.root / "ignored-secret").write_text("SENTINEL_PRIVATE_TOKEN")
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)

  def test_token_symlink_is_rejected(self):
    backing = self.base / "backing"
    self.token.rename(backing)
    self.token.symlink_to(backing)
    self.assertNotEqual(self.release().returncode, 0)
    self.assert_no_writes()

  def test_wrong_notes_heading_fails_before_credential_read(self):
    (self.root / "notes.md").write_text("# Release v9.0.0\n\nWrong version.\n")
    self.commit()
    self.token.unlink()
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("notes heading", result.stderr)
    self.assert_no_writes()

  def test_signal_cleans_owned_temporaries_and_releases_lock(self):
    self.change(hang_build=True)
    process = subprocess.Popen(["bash", str(self.root / "scripts/release.sh")], cwd=self.base,
                               env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
      deadline = time.monotonic() + 30
      while "build" not in self.events() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
      self.assertIn("build", self.events())
      process.terminate()
      stdout, stderr = process.communicate(timeout=10)
      self.assertNotEqual(process.returncode, 0)
      self.assertNotIn("SENTINEL_PRIVATE_TOKEN", stdout + stderr)
      self.assertEqual(list(self.base.glob("bash-release.*")), [])
      import fcntl
      with (self.root / ".template-operation.lock").open() as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
      if process.poll() is None:
        process.kill()
      process.communicate()

  def test_changed_predecessor_after_build_stops_before_tag(self):
    self.change(change_latest_build=True)
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("Latest changed", result.stderr)
    self.assertEqual(self.events().count("build"), 1)
    self.assertFalse(set(self.events()) & {"tag-push", "promote", "release-post"})

  def test_post_write_budget_failure_never_continues_or_rolls_back(self):
    self.change(oversize_after_promotion=True)
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("byte limit", result.stderr)
    self.assertEqual(self.events().count("promote"), 1)
    self.assertNotIn("release-post", self.events())
    self.assertEqual(self.state()["aliases"]["latest"], self.state()["prepared"])

  def test_historical_note_blob_ignores_current_external_symlink(self):
    data = helper_module()
    captured = self.git("rev-parse", "HEAD")
    original = (self.root / "notes.md").read_bytes()
    (self.root / "notes.md").unlink()
    (self.root / "notes.md").symlink_to(self.token)
    self.commit()
    self.assertEqual(data.blob(self.root, captured, "notes.md"), original)
    current = self.git("rev-parse", "HEAD")
    with self.assertRaises(data.Refusal):
      data.blob(self.root, current, "notes.md")
    for path in ("../notes.md", "/notes.md", "notes*.md", "bad\x00.md"):
      with self.subTest(path=path), self.assertRaises(data.Refusal):
        data.blob(self.root, captured, path)


class BashDataTests(unittest.TestCase):
  def setUp(self):
    self.data = helper_module()

  def http_reply(self, status, body, headers=None):
    raw = "HTTP/1.1 " + str(status) + " Fixture\r\n"
    raw += "".join(key + ": " + value + "\r\n" for key, value in (headers or {}).items()) + "\r\n"
    return 0, {"stdout": str(status).encode(), "headers": raw.encode(), "body": body}

  def test_same_origin_bearer_challenge_retries_with_private_token(self):
    body = b'{"schemaVersion":2}'
    digest = self.data.sha(body)
    replies = [self.http_reply(401, b"{}", {"WWW-Authenticate": 'Bearer realm="https://fixture.invalid/token",service="registry"'}),
               self.http_reply(200, b'{"token":"FIXTURE_BEARER_TOKEN"}'),
               self.http_reply(200, body, {"Docker-Content-Digest": digest})]
    with tempfile.TemporaryDirectory(dir="/tmp/opencode") as work, patch.object(self.data, "capture", side_effect=replies) as capture:
      self.assertEqual(self.data.registry(work, "https://fixture.invalid", "fixture.invalid/fixtures/application",
                                          "manifests", digest), (digest, {"schemaVersion": 2}))
      calls = [call.args[0] for call in capture.call_args_list]
      self.assertEqual(len(calls), 3)
      self.assertEqual(calls[0][-1], calls[2][-1])
      self.assertIn("scope=repository%3Afixtures%2Fapplication%3Apull", calls[1][-1])
      self.assertEqual(Path(calls[1][calls[1].index("--config") + 1]).name, "registry.curl")
      self.assertEqual(Path(calls[2][calls[2].index("--config") + 1]).name, "bearer.curl")
      self.assertEqual((Path(work) / "bearer.curl").read_text(), 'header = "Authorization: Bearer FIXTURE_BEARER_TOKEN"\n')
      for args in calls:
        self.assertEqual(args[:2], ["curl", "-q"])
        self.assertNotIn("--location", args)
        self.assertNotIn("--insecure", args)
        self.assertNotIn("FIXTURE_BEARER_TOKEN", " ".join(args))

  def test_registry_absence_does_not_hide_http_auth_json_or_digest_errors(self):
    arguments = ("unused", "https://fixture.invalid", "fixture.invalid/fixtures/application", "manifests")
    with patch.object(self.data, "capture", return_value=self.http_reply(404, b"{}")):
      self.assertIsNone(self.data.registry(*arguments, "latest", missing=True))
      with self.assertRaises(self.data.Refusal):
        self.data.registry(*arguments, "latest")
    body = b'{"schemaVersion":2}'
    for reply, reference in ((self.http_reply(401, b"{}"), "latest"),
                             (self.http_reply(500, b"{}"), "latest"),
                             (self.http_reply(302, b"{}"), "latest"),
                             (self.http_reply(200, b"{broken"), "latest"),
                             (self.http_reply(200, body), "sha256:" + "0" * 64),
                             (self.http_reply(200, body, {"Docker-Content-Digest": "sha256:" + "0" * 64}), "latest")):
      with self.subTest(status=reply[1]["stdout"], reference=reference), \
           patch.object(self.data, "capture", return_value=reply), self.assertRaises((self.data.Refusal, ValueError)):
        self.data.registry(*arguments, reference, missing=True)
    with patch.object(self.data, "capture", return_value=self.http_reply(200, b"null")):
      config = {"gitea": arguments[1], "image": arguments[2]}
      with self.assertRaisesRegex(self.data.Refusal, "two-platform"):
        self.data.image("unused", config, "latest", "a" * 40, missing=True)

  def test_foreign_bearer_realm_stops_before_token_request(self):
    reply = self.http_reply(401, b"{}", {"WWW-Authenticate": 'Bearer realm="https://foreign.invalid/token"'})
    with patch.object(self.data, "capture", return_value=reply) as capture:
      with self.assertRaisesRegex(self.data.Refusal, "same-origin"):
        self.data.registry("unused", "https://fixture.invalid", "fixture.invalid/fixtures/application", "manifests", "latest")
      self.assertEqual(capture.call_count, 1)

  def test_guard_read_failures_remain_fatal_in_conditional_callers(self):
    script = '''set -Eeuo pipefail
source "$1"
root=unused work=unused commit=unused predecessor='' prepared=digest
fault_status=$3
data() { return "$fault_status"; }
if "$2"; then echo continued; fi
'''
    for helper, message in (("scan", "Cannot verify captured source"),
                            ("tag_state", "Cannot read observed tag object"),
                            ("alias_guard", "Cannot verify latest alias")):
      for status in (1, 2):
        with self.subTest(helper=helper, status=status):
          result = subprocess.run(["bash", "-c", script, "fixture", str(ROOT / "scripts/release-common.sh"), helper, str(status)],
                                  capture_output=True, text=True)
          self.assertNotEqual(result.returncode, 0)
          self.assertIn(message, result.stderr)
          self.assertNotIn("continued", result.stdout)

  def test_bounded_capture_exact_limit_and_overflow(self):
    output = self.data.command([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x'*64)"], 64)
    self.assertEqual(len(output), 64)
    with self.assertRaisesRegex(self.data.Refusal, "byte limit"):
      self.data.command([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x'*65)"], 64)

  def test_unending_producer_and_stderr_are_bounded(self):
    with self.assertRaisesRegex(self.data.Refusal, "byte limit"):
      self.data.command([sys.executable, "-c", "import os\nwhile True: os.write(1,b'x'*65536)"], 1024)
    with self.assertRaisesRegex(self.data.Refusal, "byte limit"):
      self.data.command([sys.executable, "-c", "import os\nwhile True: os.write(2,b'x'*65536)"], 1024)

  def test_timeout_reaps_producer(self):
    with self.assertRaisesRegex(self.data.Refusal, "timed out"):
      self.data.command([sys.executable, "-c", "import time; time.sleep(5)"], seconds=0.05)

  def test_strict_json_and_versions(self):
    for text in (b'{"x":1,"x":2}', b'{"x":NaN}', b'"\xff"'):
      with self.assertRaises((self.data.Refusal, ValueError, UnicodeError)):
        self.data.decode(text)
    for value in ("01.0.0", "1.0", "v1.0.0", None):
      with self.assertRaises(self.data.Refusal):
        self.data.version(value)
    self.assertLess(self.data.version("1.9.0"), self.data.version("1.10.0"))

  def test_all_byte_budgets_allow_exact_size_and_refuse_extra_byte(self):
    # Exercise the receiving helper at real production capacities, without buffering remote data in a fake parser.
    capacities = {16, self.data.ANNOTATION_LIMIT, self.data.CONFIG_LIMIT, self.data.API_LIMIT, self.data.REF_LIMIT}
    for capacity in sorted(capacities):
      for extra in (0, 1):
        with self.subTest(capacity=capacity, extra=extra):
          command = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b' '*int(sys.argv[1]))", str(capacity + extra)]
          if extra:
            with self.assertRaisesRegex(self.data.Refusal, "byte limit"):
              self.data.command(command, capacity)
          else:
            self.assertEqual(len(self.data.command(command, capacity)), capacity)

  def test_inventory_page_item_byte_and_time_budgets(self):
    config = {"gitea": "https://fixture.invalid", "repository": "fixtures/application", "tag": "v1.0.0", "version": "1.0.0"}
    record = {"tag_name": "v0.9.0", "draft": False, "prerelease": False}
    body = self.data.canonical([record])
    empty = b"[]"
    for cap, value, replies, expected in (
      ("ITEM_LIMIT", 1, [body, empty, empty], True),
      ("ITEM_LIMIT", 0, [body], False),
      ("INVENTORY_LIMIT", len(body) + 4, [body, empty, empty], True),
      ("INVENTORY_LIMIT", len(body) + 3, [body, empty, empty], False),
      ("PAGE_LIMIT", 2, [empty, empty], True),
      ("PAGE_LIMIT", 1, [empty], False)):
      with self.subTest(cap=cap, value=value), patch.object(self.data, cap, value), \
           patch.object(self.data, "http", side_effect=[(200, {}, data) for data in replies]), \
           patch.object(self.data, "command", return_value=b""):
        if expected:
          self.assertIsNone(self.data.inventory("unused", "unused", config)["object"])
        else:
          with self.assertRaises(self.data.Refusal):
            self.data.inventory("unused", "unused", config)
    with patch.object(self.data.time, "monotonic", side_effect=[0, 601]):
      with self.assertRaisesRegex(self.data.Refusal, "budget"):
        self.data.inventory("unused", "unused", config)

  def test_inventory_repetition_duplicates_and_incomplete_pages(self):
    config = {"gitea": "https://fixture.invalid", "repository": "fixtures/application", "tag": "v1.0.0", "version": "1.0.0"}
    record = {"tag_name": "v0.9.0", "draft": False, "prerelease": False}
    cases = [([record], [record]), ([record], [record | {"id": 2}])]
    for pages in cases:
      with patch.object(self.data, "http", side_effect=[(200, {}, self.data.canonical(page)) for page in pages]):
        with self.assertRaises(self.data.Refusal):
          self.data.inventory("unused", "unused", config)
    with patch.object(self.data, "PAGE_LIMIT", 2), patch.object(self.data, "http", side_effect=[
        (200, {}, self.data.canonical([record | {"tag_name": "v0.8.0"}])),
        (200, {}, self.data.canonical([record]))]):
      with self.assertRaisesRegex(self.data.Refusal, "terminal"):
        self.data.inventory("unused", "unused", config)

  def test_ref_inventory_overflow_and_malformed_advertisement(self):
    config = {"gitea": "https://fixture.invalid", "repository": "fixtures/application", "tag": "v1.0.0", "version": "1.0.0"}
    for refs in (b"bad ref\n", ("a" * 40 + "\trefs/tags/v1.0.0^{}\n").encode()):
      with patch.object(self.data, "http", return_value=(200, {}, b"[]")), patch.object(self.data, "command", return_value=refs):
        with self.assertRaises(self.data.Refusal):
          self.data.inventory("unused", "unused", config)

  def test_timeout_and_overflow_kill_descendant_processes(self):
    with tempfile.TemporaryDirectory() as directory:
      marker = Path(directory) / "escaped"
      code = ("import subprocess,sys,time; "
              "subprocess.Popen([sys.executable,'-c',sys.argv[1]]); time.sleep(5)")
      child = "import time; from pathlib import Path; time.sleep(.3); Path(" + repr(str(marker)) + ").write_text('bad')"
      with self.assertRaises(self.data.Refusal):
        self.data.command([sys.executable, "-c", code, child], seconds=0.1)
      time.sleep(0.4)
      self.assertFalse(marker.exists())

  def test_image_verification_rejects_wrong_platform_labels_and_member_shapes(self):
    config = {"gitea": "https://fixture.invalid", "image": "fixture.invalid/fixtures/application",
              "repository": "fixtures/application", "version": "1.0.0"}
    commit = "a" * 40
    root, member, content = "sha256:" + "1" * 64, "sha256:" + "2" * 64, "sha256:" + "3" * 64
    labels = {"org.opencontainers.image.revision": commit, "org.opencontainers.image.version": "1.0.0",
              "org.opencontainers.image.source": "https://fixture.invalid/fixtures/application"}
    index = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json", "manifests": [
      {"digest": member, "platform": {"os": "linux", "architecture": "amd64"}},
      {"digest": member, "platform": {"os": "linux", "architecture": "arm64"}}]}
    manifest = {"schemaVersion": 2, "config": {"digest": content}}
    for content_value in ({"os": "linux", "architecture": "riscv64", "config": {"Labels": labels}},
                          {"os": "linux", "architecture": "amd64", "config": {"Labels": labels | {"org.opencontainers.image.version": "2.0.0"}}}):
      with patch.object(self.data, "registry", side_effect=[(root, index), (member, manifest), (content, content_value)]):
        with self.assertRaises(self.data.Refusal):
          self.data.image("unused", config, root, commit)
    for bad in ({}, index | {"manifests": []}, index | {"schemaVersion": 1}):
      with patch.object(self.data, "registry", return_value=(root, bad)):
        with self.assertRaises(self.data.Refusal):
          self.data.image("unused", config, root, commit)

  def test_advertised_platforms_are_tokens_not_substring_matches(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / "builder"
      path.write_text("Platforms: linux/amd64, linux/arm64\n")
      self.assertEqual(self.data.dispatch(["platforms", str(path)]), 0)
      for text in ("Platforms: linux/amd64foreign, linux/arm64\n", "random linux/amd64 linux/arm64"):
        path.write_text(text)
        with self.assertRaises(self.data.Refusal):
          self.data.dispatch(["platforms", str(path)])

  def test_blocked_stdin_is_also_subject_to_deadline(self):
    with self.assertRaises(self.data.Refusal):
      self.data.command([sys.executable, "-c", "import time; time.sleep(5)"], seconds=0.05, input_data=b"x" * 65536)

  def test_git_destination_normalization_keeps_ssh_ports_independent(self):
    for url in ("git@git.lan:fixtures/application.git", "ssh://git@git.lan:2222/fixtures/application.git",
                "https://git.lan:443/fixtures/application.git"):
      self.assertEqual(self.data.remote_key(url), ("git.lan", "fixtures/application"))
    self.assertEqual(self.data.remote_key("https://git.lan:8443/fixtures/application.git"),
                     ("git.lan:8443", "fixtures/application"))
