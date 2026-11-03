"""Exercise the Bash entry point without credentials, Docker, or production services."""

import ast
import errno
import importlib.util
import json
import os
from pathlib import Path
import shutil
import selectors
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import time


ROOT = Path(__file__).resolve().parents[1]


def owned_temporary_directory(prefix="bash-release-test-"):
  return tempfile.TemporaryDirectory(prefix=prefix, dir="/tmp/opencode" if Path("/tmp/opencode").is_dir() else None)


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
    self.temporary = owned_temporary_directory()
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
    config |= {"repository": "fixtures/application", "image": "git.lan/fixtures/application-hello",
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
    self.assertFalse(set(self.events()) & {"build", "tag-push", "promote", "release-post", "package-link"}, self.events())

  def assert_progress_order(self, result, messages):
    position = -1
    for message in messages:
      current = result.stderr.find("Release progress: " + message, position + 1)
      self.assertGreater(current, position, message + "\n" + result.stderr)
      position = current
    self.assertNotIn("Release progress:", result.stdout)

  def real_source_environment(self):
    environment = {key: value for key, value in self.environment.items() if not key.startswith("GIT_CONFIG")}
    return environment | {"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}

  def real_source(self):
    with patch.dict(os.environ, self.real_source_environment(), clear=True):
      return helper_module().source(self.root, remote=False)

  def test_real_git_push_fanout_is_refused(self):
    allowed = "https://git.lan/fixtures/application.git"
    original = (self.root / ".git/config").read_text()
    for key in ("url", "pushurl"):
      for extra in (allowed, "https://foreign.invalid/other/project.git"):
        with self.subTest(key=key, extra=extra):
          (self.root / ".git/config").write_text(original)
          self.git("remote", "set-url", "origin", allowed)
          if key == "pushurl":
            self.git("config", "--add", "remote.origin.pushurl", allowed)
          self.git("config", "--add", "remote.origin." + key, extra)
          with patch.dict(os.environ, self.real_source_environment(), clear=True):
            data = helper_module()
            observed = data.git(self.root, "remote", "get-url", "--push", "--all", "origin").decode().splitlines()
            self.assertEqual(observed, [allowed, extra])
            with self.assertRaisesRegex(data.Refusal, "one valid effective Git destination"):
              data.source(self.root, remote=False)

  def test_real_git_single_push_targets_keep_supported_normalization(self):
    original = (self.root / ".git/config").read_text()
    for destination in ("https://git.lan/fixtures/application.git", "https://git.lan:443/fixtures/application",
                        "git@git.lan:fixtures/application.git", "ssh://git@git.lan:2222/fixtures/application.git"):
      for explicit in (False, True):
        with self.subTest(destination=destination, explicit=explicit):
          (self.root / ".git/config").write_text(original)
          self.git("remote", "set-url", "origin", destination)
          if explicit:
            self.git("config", "--add", "remote.origin.pushurl", destination)
          self.assertEqual(self.real_source(), self.git("rev-parse", "HEAD"))

  def test_real_git_destination_rewrites_are_validated(self):
    allowed = "https://git.lan/fixtures/application.git"
    original = (self.root / ".git/config").read_text()
    for rule in ("insteadOf", "pushInsteadOf"):
      for target in (allowed, "https://foreign.invalid/other/project.git"):
        with self.subTest(rule=rule, target=target):
          (self.root / ".git/config").write_text(original)
          # A push-only rewrite leaves the permitted fetch URL unchanged.
          raw = "fixture:application" if rule == "insteadOf" else allowed
          self.git("remote", "set-url", "origin", raw)
          self.git("config", "url." + target + "." + rule, raw)
          with patch.dict(os.environ, self.real_source_environment(), clear=True):
            data = helper_module()
            self.assertEqual(data.git(self.root, "remote", "get-url", "--push", "--all", "origin").decode().strip(), target)
            if target == allowed:
              self.assertEqual(data.source(self.root, remote=False), self.git("rev-parse", "HEAD"))
            else:
              with self.assertRaisesRegex(data.Refusal, "Git destination differs"):
                data.source(self.root, remote=False)

  def test_push_url_evidence_refuses_before_publication(self):
    allowed = "https://git.lan/fixtures/application.git\n"
    cases = ({"push_url_output": allowed + "https://foreign.invalid/other/project.git\n"},
             {"push_url_output": allowed * 2}, {"push_url_output": ""},
             {"push_url_output": "\n"}, {"push_url_output": allowed + "\n"},
             {"push_url_output": allowed.replace("\n", "\r\n")},
             {"push_url_output": allowed.replace("application", "app\x00lication")},
             {"push_url_output": "https://foreign.invalid/other/project.git\n"},
             *({"push_url_fault": fault} for fault in ("command", "overflow", "encoding")))
    before = self.git("ls-remote", "origin")
    for case in cases:
      with self.subTest(case=case):
        self.change(**({"push_url_output": allowed, "push_url_fault": None} | case))
        result = self.release()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("push-urls-read", self.events())
        self.assertIn("Release stopped (source verification)", result.stderr)
        self.assertNotIn("Publication verified", result.stdout)
        self.assertNotIn("foreign.invalid", result.stdout + result.stderr)
        self.assert_no_writes()
        self.assertEqual(self.git("ls-remote", "origin"), before)
        self.assertEqual(self.state()["objects"], {})

  def test_push_urls_changed_after_build_block_tag_dispatch(self):
    self.change(push_urls_change_after_build=True)
    result = self.release()
    events = self.events()
    self.assertIn("push-urls-changed", events)
    self.assertLess(events.index("build"), events.index("push-urls-changed"))
    self.assertNotEqual(result.returncode, 0)
    self.assertNotIn("Publication verified", result.stdout)
    self.assertEqual(events.count("build"), 1)
    self.assertFalse(set(events) & {"tag-push", "promote", "release-post", "package-link"})
    self.assertEqual(self.git("ls-remote", "--tags", "origin"), "")
    self.assertTrue(any(name.startswith("rt-") for name in self.state()["aliases"]))
    self.assertIn(self.state()["prepared"], self.state()["objects"])

  def assert_post_confirmation_refusal(self, fault, skip=False, lost=False):
    predecessor = self.predecessor()
    self.change(post_confirmation_fault=fault, post_confirmation_predecessor=predecessor,
                promotion_read_fault="prepared" if skip else None, lose_promotion=lost)
    result = self.release()
    events = self.events()
    injection = "post-confirmation-injected:" + fault
    self.assertIn(injection, events)
    self.assertLess(events.index("promotion-confirmation-read"), events.index(injection))
    self.assertIn("digest promotion verified", result.stderr)
    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertNotIn("Publication verified", result.stdout)
    self.assertFalse(set(events[events.index(injection) + 1:]) & {"build", "tag-push", "promote", "release-post", "package-link"})
    for action, count in (("build", 1), ("tag-push", 1), ("promote", int(not skip)), ("release-post", 0), ("package-link", 0)):
      self.assertEqual(events.count(action), count, action)
    state = self.state()
    latest = state["aliases"].get("latest")
    if fault == "predecessor":
      self.assertEqual(latest, predecessor)
    elif fault == "absent":
      self.assertIsNone(latest)
    elif fault == "foreign":
      self.assertNotIn(latest, (predecessor, state["prepared"]))
    else:
      self.assertEqual(latest, state["prepared"])
    self.assertEqual(state["releases"], [])
    self.assertTrue(any(name.startswith("rt-") and value == state["prepared"] for name, value in state["aliases"].items()))
    self.assertIn(state["prepared"], state["objects"])
    oid = self.git("ls-remote", "--tags", "origin", "refs/tags/v1.0.0").split()[0]
    self.assertEqual(oid, state["confirmed_object"])
    identity = json.loads(self.git("cat-file", "tag", oid).split("\n\n", 1)[1].split("\n", 1)[1])
    self.assertEqual(identity["digest"], state["prepared"])
    self.assertEqual(identity["predecessor"], predecessor)
    self.assertEqual(identity["commit"], self.git("rev-parse", "HEAD"))

  def test_post_confirmation_predecessor_reversion_blocks_release(self):
    self.assert_post_confirmation_refusal("predecessor")

  def test_post_confirmation_absence_blocks_release(self):
    self.assert_post_confirmation_refusal("absent")

  def test_post_confirmation_foreign_alias_blocks_release(self):
    self.assert_post_confirmation_refusal("foreign")

  def test_post_confirmation_failed_read_blocks_release(self):
    self.assert_post_confirmation_refusal("transport")

  def test_post_confirmation_malformed_read_blocks_release(self):
    self.assert_post_confirmation_refusal("malformed")

  def test_post_confirmation_oversized_read_blocks_release(self):
    self.assert_post_confirmation_refusal("overflow")

  def test_skipped_promotion_confirmation_reversion_blocks_release(self):
    self.assert_post_confirmation_refusal("predecessor", skip=True)

  def test_reconciled_promotion_confirmation_reversion_blocks_release(self):
    self.assert_post_confirmation_refusal("predecessor", lost=True)

  def test_progress_is_visible_while_build_is_blocked(self):
    self.change(build_barrier=True)
    descriptors = []
    for name in ("build-entered", "build-release"):
      os.mkfifo(self.base / name)
      descriptors.append(os.open(self.base / name, os.O_RDWR | os.O_NONBLOCK))
    entered, release = descriptors
    process = subprocess.Popen(["bash", str(self.root / "scripts/release.sh")], cwd=self.base,
                               env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    def cleanup():
      os.write(release, b"1")
      if process.poll() is None:
        process.terminate()
      try:
        process.communicate(timeout=10)
      except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=10)
      finally:
        for descriptor in descriptors:
          os.close(descriptor)
    self.addCleanup(cleanup)
    output = {"stdout": bytearray(), "stderr": bytearray(), "entered": bytearray()}
    start = b"starting multi-platform build; staging may be pushed during this operation"
    with selectors.DefaultSelector() as selector:
      for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr"), (entered, "entered")):
        os.set_blocking(stream if isinstance(stream, int) else stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
      deadline = time.monotonic() + 45
      while not (output["entered"] and start in output["stderr"]):
        self.assertLess(time.monotonic(), deadline, "Build entry/progress was not observed before timeout")
        self.assertIsNone(process.poll(), bytes(output["stderr"]).decode())
        for key, _ in selector.select(min(1, max(0, deadline - time.monotonic()))):
          chunk = os.read(key.fd, 65536)
          if chunk:
            output[key.data].extend(chunk)
          else:
            selector.unregister(key.fileobj)
      # Drain messages already available while the fixture cannot finish the build.
      while ready := selector.select(0):
        self.assertLess(time.monotonic(), deadline, "Progress pipes did not drain before timeout")
        for key, _ in ready:
          chunk = os.read(key.fd, 65536)
          if chunk:
            output[key.data].extend(chunk)
          else:
            selector.unregister(key.fileobj)
    self.assertIsNone(process.poll())
    during = bytes(output["stdout"] + output["stderr"])
    self.assertNotIn(b"staging build and immutable verification complete", during)
    self.assertNotIn(b"Publication verified", during)
    self.assertNotIn("build-barrier-released", self.events())
    os.write(release, b"1")
    stdout, stderr = process.communicate(timeout=45)
    stdout, stderr = bytes(output["stdout"]) + stdout, bytes(output["stderr"]) + stderr
    self.assertEqual(process.returncode, 0, stderr.decode())
    self.assertIn(b"staging build and immutable verification complete", stderr)
    self.assertIn(b"Publication verified: v1.0.0", stdout)
    self.assertNotIn(b"SENTINEL_PRIVATE_TOKEN", stdout + stderr)
    self.assertEqual(list(self.base.glob("bash-release.*")), [])

  def test_missing_prerequisites_give_install_instructions_without_commands(self):
    original = self.environment["PATH"]
    tools = ("python3", "git", "docker", "curl")
    try:
      for missing in tools:
        with self.subTest(tool=missing):
          isolated = self.base / ("without-" + missing)
          isolated.mkdir()
          for tool in ("bash", "dirname", *tools):
            if tool != missing:
              target = self.bin / tool if tool in ("git", "docker", "curl") else Path(shutil.which(tool))
              (isolated / tool).symlink_to(target)
          self.environment["PATH"] = str(isolated)
          result = self.release()
          self.assertNotEqual(result.returncode, 0)
          self.assertIn("Install " + ("Python 3.11" if missing == "python3" else missing), result.stderr)
          self.assertEqual(self.events(), [])
          self.assertFalse((self.root / ".template-operation.lock").exists())
    finally:
      self.environment["PATH"] = original

  def test_readiness_failures_give_stage_guidance_without_writes(self):
    cases = (("builder_failure", "builder readiness", "Buildx installation"),
             ("unsupported", "platform readiness", "docs/platform-preparation.md"),
             ("wrong_main", "source verification", "already-pushed source"),
             ("http_transport_failure", "read-only startup classification", "DNS"))
    for flag, phase, advice in cases:
      with self.subTest(fault=flag):
        self.change(**{flag: True}, hostile_output=True)
        result = self.release()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Release stopped (" + phase + ")", result.stderr)
        self.assertIn(advice, result.stderr)
        self.assertIn("No publication writes were sent by this invocation", result.stderr)
        self.assertNotIn("HOSTILE_REMOTE_OUTPUT", result.stdout + result.stderr)
        self.assertNotIn(str(self.token), result.stdout + result.stderr)
        self.assert_no_writes()
        if flag == "builder_failure":
          self.assertNotIn("prepare emulation", result.stderr)
        self.change(**{flag: False})

  def test_credential_failure_explains_private_token_setup(self):
    self.token.chmod(0o644)
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("Release stopped (credential preparation)", result.stderr)
    self.assertIn("private token ownership/mode", result.stderr)
    self.assertNotIn(str(self.token), result.stdout + result.stderr)
    self.assert_no_writes()

  def test_failed_build_warns_of_possible_staging_write_without_later_writes(self):
    self.change(build_failure=True, hostile_output=True)
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("Release stopped (staging build and immutable verification)", result.stderr)
    self.assertIn("registry push access", result.stderr)
    self.assertIn("inspect exact remaining objects without rollback", result.stderr)
    self.assertNotIn("No publication writes were sent", result.stderr)
    self.assertNotIn("HOSTILE_REMOTE_OUTPUT", result.stdout + result.stderr)
    self.assertNotIn(str(self.token), result.stdout + result.stderr)
    self.assertNotIn("staging build and immutable verification complete", result.stderr)
    self.assertNotIn("Publication verified", result.stdout + result.stderr)
    self.assertEqual(self.events().count("build"), 1)
    self.assertFalse(set(self.events()) & {"tag-push", "promote", "release-post", "package-link"})

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

  def plugin_marker(self, directory, identity):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "docker-buildx"
    path.write_text("#!/bin/sh\n# " + identity + "\nexit 0\n")
    path.chmod(0o755)
    return path

  def test_buildx_discovery_preserves_candidates_across_auth_isolation(self):
    for mode in ("local", "shadow", "extra", "system", "missing-config", "unset", "empty", "relative", "spaces", "symlink", "null"):
      with self.subTest(mode=mode):
        case = BashPublicationTests()
        try:
          case.setUp()
          original = case.connection()
          local = case.plugin_marker(original / "cli-plugins", "config-local")
          system = case.plugin_marker(case.base / "system-plugins", "system")
          expected = local
          config_path = original / "config.json"
          config = json.loads(config_path.read_text())
          if mode == "local":
            system.unlink()
          elif mode in ("extra", "relative", "spaces"):
            first = case.plugin_marker(case.base / "extra plugins", "extra-first")
            second = case.plugin_marker(case.base / "second-extra", "extra-second")
            config["cliPluginsExtraDirs"] = [str(first.parent), str(second.parent)]
            expected = first
            if mode == "relative":
              config["cliPluginsExtraDirs"] = [str(first.parent.relative_to(case.base)), str(second.parent.relative_to(case.base))]
              case.environment["DOCKER_CONFIG"] = str(original.relative_to(case.base))
            if mode == "spaces":
              renamed = case.base / "original docker"
              original.rename(renamed)
              original, config_path = renamed, renamed / "config.json"
              case.environment["DOCKER_CONFIG"] = str(renamed)
          elif mode in ("system", "missing-config"):
            local.unlink()
            expected = system
          elif mode in ("unset", "empty"):
            original.rename(case.base / ".docker")
            original = case.base / ".docker"
            config_path = original / "config.json"
            expected = original / "cli-plugins/docker-buildx"
            if mode == "unset":
              case.environment.pop("DOCKER_CONFIG")
            else:
              case.environment["DOCKER_CONFIG"] = ""
          elif mode == "symlink":
            backing = case.plugin_marker(case.base / "linked-plugin", "symlink-target")
            local.unlink()
            local.symlink_to(backing)
          elif mode == "null":
            config["cliPluginsExtraDirs"] = None
          config_path.write_text(json.dumps(config))
          if mode == "missing-config":
            config_path.unlink()
          case.change(plugin_discovery=True, plugin_system_dirs=[str(system.parent)])
          result = case.release()
          self.assertEqual(result.returncode, 0, result.stderr)
          selections = [json.loads(line) for line in (case.base / "docker-selections").read_text().splitlines()]
          buildx = [row for row in selections if row["operation"][0] == "buildx"]
          self.assertEqual(len(buildx), 3)
          self.assertEqual({row["plugin"] for row in buildx}, {str(expected)})
          self.assertEqual({row["plugin_identity"] for row in buildx}, {expected.read_text()})
          private = json.loads((case.base / "private-docker-config.json").read_text())
          self.assertEqual(set(private), {"auths", "cliPluginsExtraDirs"})
          self.assertEqual(private["cliPluginsExtraDirs"][-1], str(original / "cli-plugins"))
          self.assertNotIn("UNRELATED_AUTH_SENTINEL", json.dumps(private))
          if mode != "missing-config":
            case.assert_connection_preserved("unix:///var/run/docker.sock")
        finally:
          case.doCleanups()

  def test_noncanonical_plugin_fields_refuse_without_silent_fallback(self):
    original = self.connection()
    extra = self.plugin_marker(self.base / "extra-plugins", "extra-selected-before-refusal")
    local = self.plugin_marker(original / "cli-plugins", "local-fallback")
    field = "cliPluginsExtraDirs"
    cases = [{alias: [str(extra.parent)]} for alias in ("CLIPluginsExtraDirs", "clipluginsextradirs", "cliPluginſExtraDirs")]
    cases += [{field: [str(local.parent)], "CLIPluginsExtraDirs": [str(extra.parent)]},
              {"CLIPluginsExtraDirs": [str(extra.parent)], field: [str(local.parent)]},
              {field: [str(extra.parent)], "CLIPluginsExtraDirs": [str(extra.parent)]},
              {field: None, "CLIPluginsExtraDirs": [str(extra.parent)]},
              {field: [str(extra.parent)], "CLIPluginsExtraDirs": None}]
    self.change(plugin_discovery=True, plugin_system_dirs=[])
    for values in cases:
      with self.subTest(values=values):
        (self.base / "events").write_text("")
        (self.base / "docker-selections").write_text("")
        (original / "config.json").write_text(json.dumps(values))
        result = self.release()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires canonical cliPluginsExtraDirs spelling", result.stderr)
        self.assertIn("builder", self.events())
        selected = json.loads((self.base / "docker-selections").read_text().splitlines()[0])
        effective = list(values.values())[-1] or [str(local.parent)]
        self.assertEqual(selected["plugin"], str(Path(effective[0]) / "docker-buildx"))
        self.assertNotIn(str(self.base), result.stdout + result.stderr)
        self.assertNotIn("CLIPluginsExtraDirs", result.stdout + result.stderr)
        self.assert_no_writes()

  def assert_setup_refusal(self, result, phase, advice):
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("Release stopped (" + phase + ")", result.stderr)
    self.assertIn("Next:", result.stderr)
    self.assertIn(advice, result.stderr)
    self.assertIn("No publication writes were sent by this invocation", result.stderr)
    self.assertNotIn("Publication verified", result.stdout)
    self.assertNotIn(str(self.base), result.stdout + result.stderr)
    self.assertNotIn("SENTINEL_PRIVATE_TOKEN", result.stdout + result.stderr)
    self.assertEqual(self.events(), [])

  def test_temporary_parent_failures_have_safe_guidance_and_release_lock(self):
    import fcntl
    for parent in (self.base / "missing-private-parent", self.token):
      with self.subTest(parent=parent.name):
        self.environment["TMPDIR"] = str(parent)
        result = self.release()
        self.assert_setup_refusal(result, "temporary storage", "valid writable temporary parent")
        with (self.root / ".template-operation.lock").open() as lock:
          fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertEqual(self.token.read_text(), "SENTINEL_PRIVATE_TOKEN\n")

  def test_temporary_creation_os_failures_suppress_raw_stderr(self):
    command = self.bin / "mktemp"
    command.write_text("#!/bin/sh\necho 'SENTINEL_PRIVATE_TOKEN " + str(self.token) + " storage error' >&2\nexit 1\n")
    command.chmod(0o755)
    result = self.release()
    self.assert_setup_refusal(result, "temporary storage", "available space")
    self.assertNotIn("storage error", result.stderr)

  def test_invalid_inherited_lock_descriptor_has_guidance(self):
    self.environment["RELEASE_LOCK_FD"] = "999999"
    self.assert_setup_refusal(self.release(), "checkout lock verification", "filesystem lock support")

  def test_inherited_lock_identity_mismatch_preserves_files(self):
    (self.root / ".template-operation.lock").write_text("checkout lock")
    with self.token.open() as foreign:
      environment = self.environment | {"RELEASE_LOCK_FD": str(foreign.fileno())}
      result = subprocess.run(["bash", str(self.root / "scripts/release.sh")], env=environment,
                              pass_fds=(foreign.fileno(),), cwd=self.base, capture_output=True, text=True, timeout=30)
    self.assert_setup_refusal(result, "checkout lock verification", "Do not delete or bypass")
    self.assertEqual((self.root / ".template-operation.lock").read_text(), "checkout lock")
    self.assertEqual(self.token.read_text(), "SENTINEL_PRIVATE_TOKEN\n")

  def assert_promotion_read_refuses(self, fault):
    predecessor = self.predecessor()
    self.change(promotion_read_fault=fault)
    result = self.release()
    events = self.events()
    injection = "promotion-read-injected:" + fault
    self.assertIn(injection, events, "The precise post-guard read must receive the fault")
    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertNotIn("Publication verified", result.stdout)
    self.assertFalse(set(events[events.index(injection) + 1:]) & {"build", "tag-push", "promote", "release-post", "package-link"})
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
    self.assertFalse(set(events[events.index(injection) + 1:]) & {"build", "tag-push", "promote", "release-post", "package-link"})
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
    self.assertIn("latest already matches the prepared digest; skipping promotion", result.stderr)

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
    self.change(hostile_output=True)
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("Publication verified: v1.0.0", result.stdout)
    self.assertNotIn("HOSTILE_REMOTE_OUTPUT", result.stdout + result.stderr)
    self.assertNotIn(str(self.token), result.stdout + result.stderr)
    self.assert_progress_order(result, ("prerequisite checks", "builder readiness", "platform readiness",
      "source verification", "credential preparation", "read-only startup classification", "staging lookup",
      "registry login", "starting multi-platform build", "staging build and immutable verification complete",
      "tag publication", "digest promotion", "release creation", "final publication verification",
      "package association", "final association verification"))
    self.assertEqual(result.stderr.count("Release progress: prerequisite checks"), 1)
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
      self.assert_progress_order(result, ("completed-publication verification", "package association",
        "final association verification"))
      self.assertNotIn("HOSTILE_REMOTE_OUTPUT", result.stdout + result.stderr)
      self.assertNotIn(str(self.token), result.stdout + result.stderr)
      for message in ("starting multi-platform build", "digest promotion", "release creation", "staging lookup"):
        self.assertNotIn("Release progress: " + message, result.stderr)
      self.assert_no_writes()
      self.assertFalse(any(e.startswith("registry:rt-") for e in self.events()))
      self.assertEqual(self.git("ls-remote", "--tags", "origin", "refs/tags/v1.0.0").split()[0], oid)

  def test_tag_only_startup_refuses_before_staging_or_build(self):
    self.change(fail_release=True)
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("Release creation not confirmed", result.stderr)
    self.assertIn("inspect exact remaining objects without rollback", result.stderr)
    self.assertIn("Do not blindly retry", result.stderr)
    self.assertTrue(self.state()["aliases"].get("latest"))
    self.assertEqual(self.events().count("tag-push"), 1)
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
    failed = self.release()
    self.assertNotEqual(failed.returncode, 0)
    self.assertIn("inspect exact remaining objects without rollback", failed.stderr)
    self.assertTrue(any(name.startswith("rt-") for name in self.state()["aliases"]))
    self.change(lose_build=False)
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(self.events().count("build"), 1)
    self.assert_progress_order(result, ("staging lookup", "reusing verified staging image", "registry login",
      "tag publication", "digest promotion", "release creation"))
    self.assertNotIn("starting multi-platform build", result.stderr)

  def test_preflight_refusals_do_not_write(self):
    for flag in ("wrong_remote", "wrong_main", "unsupported", "null_inventory", "malformed", "oversized", "realm_foreign"):
      with self.subTest(flag=flag):
        self.change(**{flag: True})
        self.assertNotEqual(self.release().returncode, 0)
        self.assert_no_writes()
        self.change(**{flag: False})
    for status in (401, 500):
      self.change(status=status)
      result = self.release()
      self.assertNotEqual(result.returncode, 0)
      self.assertIn("Release stopped (read-only startup classification)", result.stderr)
      self.assertIn("account permissions", result.stderr)
      self.assertIn("No publication writes were sent by this invocation", result.stderr)
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
    self.assertNotIn("Release progress:", result.stdout + result.stderr)
    self.assertFalse((self.root / ".template-operation.lock").exists())
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
    self.assertNotIn("staging build and immutable verification complete", result.stderr)
    self.assertNotIn("Publication verified", result.stdout + result.stderr)
    self.assertIn("inspect exact remaining objects without rollback", result.stderr)

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
    self.assert_setup_refusal(self.release(), "checkout locking", "non-symlink lock file")
    self.assertEqual(self.token.read_text(), "SENTINEL_PRIVATE_TOKEN\n")
    lock.unlink()
    import fcntl
    with lock.open("w") as held:
      fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
      self.assert_setup_refusal(self.release(), "checkout locking", "active checkout lock owner")
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
      self.assertIn("operation interrupted", stderr)
      self.assertIn("inspect exact remaining objects without rollback", stderr)
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


  def target_repository(self):
    return {"id": 17, "name": "application", "full_name": "fixtures/application", "owner": {"login": "fixtures"}}

  def reset_association(self):
    self.change(linked_repository=None, target_reads=0, package_reads=0, version_reads=0, association_fault={}, link_fault=None)
    (self.base / "events").write_text("")

  def assert_no_publication_writes(self):
    self.assertFalse(set(self.events()) & {"build", "tag-push", "promote", "release-post"}, self.events())
    self.assertFalse(any(event.startswith("registry:rt-") for event in self.events()))

  def test_fresh_release_links_only_configured_package_and_verifies_it(self):
    unrelated = {"foreign-package": {"repository": {"id": 999}}}
    self.change(unrelated_packages=unrelated)
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(self.state()["linked_repository"], self.target_repository())
    self.assertEqual(self.state()["unrelated_packages"], unrelated)
    events = self.events()
    self.assertEqual(events.count("package-link"), 1)
    self.assertLess(events.index("release-post"), events.index("package-link"))
    self.assertIn("http:GET:/api/v1/packages/fixtures/container/application-hello/latest", events[events.index("package-link") + 1:])
    self.assertFalse(any("unlink" in event or "DELETE" in event for event in events))

  def test_fresh_release_preserves_correct_link_without_post(self):
    self.change(linked_repository=self.target_repository())
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertNotIn("package-link", self.events())

  def test_fresh_release_refuses_conflicting_link_without_rollback(self):
    foreign = self.target_repository() | {"id": 99}
    self.change(linked_repository=foreign)
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertNotIn("Publication verified", result.stdout)
    self.assertNotIn("package-link", self.events())
    self.assertEqual(self.state()["linked_repository"], foreign)
    self.assertEqual(len(self.state()["releases"]), 1)
    self.assertEqual(self.state()["aliases"]["latest"], self.state()["prepared"])

  def test_completed_retry_finishes_only_missing_link_then_becomes_read_only(self):
    self.change(link_fault="denied")
    self.assertNotEqual(self.release().returncode, 0)
    before = self.state()
    self.reset_association()
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assert_no_publication_writes()
    self.assertEqual(self.events().count("package-link"), 1)
    self.assertEqual(self.state()["releases"], before["releases"])
    self.assertEqual(self.state()["aliases"], before["aliases"])
    (self.base / "events").write_text("")
    self.assertEqual(self.release().returncode, 0)
    self.assert_no_writes()

  def test_completed_retry_refuses_foreign_association_without_writes(self):
    self.assertEqual(self.release().returncode, 0)
    foreign = self.target_repository() | {"full_name": "fixtures/foreign", "name": "foreign"}
    self.change(linked_repository=foreign)
    (self.base / "events").write_text("")
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assert_no_writes()
    self.assertEqual(self.state()["linked_repository"], foreign)

  def test_lost_link_response_is_reconciled_without_repeating_post(self):
    self.change(link_fault="lost")
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(self.events().count("package-link"), 1)
    self.assertEqual(self.state()["linked_repository"], self.target_repository())

  def test_hidden_foreign_link_is_refused_by_supported_server_without_reassignment(self):
    foreign = self.target_repository() | {"id": 99, "full_name": "fixtures/private", "name": "private"}
    self.change(linked_repository=foreign, hide_link=True)
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertNotIn("Publication verified", result.stdout)
    self.assertEqual(self.state()["linked_repository"], foreign)
    self.assertEqual(self.events().count("package-link"), 1)
    self.assertEqual(self.state()["package_reads"], 2, "HTTP refusals must not reconcile")

  def test_unsupported_server_refuses_link_writes_but_allows_existing_correct_link(self):
    self.change(gitea_version="1.24.6")
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("stable Gitea 1.25.x or exact 28.2.0", result.stderr)
    self.assertNotIn("package-link", self.events())
    self.change(linked_repository=self.target_repository())
    (self.base / "events").write_text("")
    result = self.release()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assert_no_writes()
    self.assertNotIn("http:GET:/api/v1/version", self.events())

  def test_link_failures_preserve_publication_and_never_repeat_post(self):
    self.assertEqual(self.release().returncode, 0)
    publication = self.state()
    for fault in ("transport", "timeout", "denied", "missing", "server", "wrong_status", "ignore", "conflict_after", "overflow"):
      with self.subTest(fault=fault):
        self.reset_association()
        self.change(link_fault=fault)
        result = self.release()
        self.assertNotEqual(result.returncode, 0, fault)
        self.assertNotIn("Publication verified", result.stdout)
        self.assertEqual(self.events().count("package-link"), 1)
        self.assert_no_publication_writes()
        self.assertEqual(self.state()["releases"], publication["releases"])
        self.assertEqual(self.state()["aliases"], publication["aliases"])
        self.assertFalse(any("unlink" in event or "DELETE" in event for event in self.events()))
        if fault == "overflow":
          self.assertEqual(self.state()["linked_repository"], self.target_repository())
          self.assertEqual(self.state()["package_reads"], 2, "Resource refusals must not reconcile")

  def test_failed_association_prerequisite_never_authorizes_link(self):
    self.assertEqual(self.release().returncode, 0)
    for resource, kinds in (("target", ("missing", "unauthorized", "server", "redirect", "null", "wrong_name")),
                            ("version", ("missing", "unauthorized", "server", "redirect", "null", "malformed", "transport")),
                            ("package", ("missing", "unauthorized", "server", "redirect", "malformed", "null", "overflow",
                                         "absent_repository", "wrong_name", "wrong_version", "transport", "timeout"))):
      for kind in kinds:
        with self.subTest(resource=resource, kind=kind):
          self.reset_association()
          self.change(association_fault={"resource": resource, "kind": kind})
          result = self.release()
          self.assertNotEqual(result.returncode, 0)
          self.assertIn("association-read-injected:" + kind, self.events())
          self.assertNotIn("Publication verified", result.stdout)
          self.assert_no_writes()
          self.assertIsNone(self.state()["linked_repository"])

  def test_refreshed_identity_failure_blocks_link(self):
    self.assertEqual(self.release().returncode, 0)
    for resource, kind in (("target", "wrong_id"), ("package", "absent_repository")):
      with self.subTest(resource=resource):
        self.reset_association()
        self.change(association_fault={"resource": resource, "read": 2, "kind": kind})
        result = self.release()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("association-read-injected:" + kind, self.events())
        self.assert_no_writes()

  def test_post_link_verification_failure_does_not_undo_accepted_link(self):
    self.assertEqual(self.release().returncode, 0)
    for read, kind in ((3, "malformed"), (3, "transport"), (4, "null")):
      with self.subTest(read=read, kind=kind):
        self.reset_association()
        self.change(association_fault={"resource": "package", "read": read, "kind": kind})
        result = self.release()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Publication verified", result.stdout)
        self.assertEqual(self.events().count("package-link"), 1)
        self.assertEqual(self.state()["linked_repository"], self.target_repository())
        self.assert_no_publication_writes()

  def test_publication_change_after_link_prevents_success_without_rollback(self):
    self.change(association_fault={"resource": "package", "read": 3, "kind": "change_latest"})
    result = self.release()
    self.assertNotEqual(result.returncode, 0)
    self.assertNotIn("Publication verified", result.stdout)
    self.assertEqual(self.state()["linked_repository"], self.target_repository())
    self.assertNotEqual(self.state()["aliases"]["latest"], self.state()["prepared"])
    self.assertEqual(self.events().count("promote"), 1)


class BashDataTests(unittest.TestCase):
  def setUp(self):
    self.data = helper_module()

  def test_docker_plugin_directory_config_is_strict_and_bounded(self):
    with owned_temporary_directory() as directory:
      original = Path(directory)
      path = original / "config.json"
      expected = [str(original / "cli-plugins")]
      self.assertEqual(self.data.docker_plugin_dirs(original), expected)
      for config in ({}, {"cliPluginsExtraDirs": None}, {"cliPluginsExtraDirs": []}):
        path.write_text(json.dumps(config))
        self.assertEqual(self.data.docker_plugin_dirs(original), expected)
      path.write_text(json.dumps({"cliPluginsExtraDirs": ["extra plugins", "/owned/absolute"]}))
      with patch.object(self.data.os, "getcwd", return_value=directory):
        self.assertEqual(self.data.docker_plugin_dirs(original), [str(original / "extra plugins"), "/owned/absolute", *expected])
      invalid = [b"{broken", b"[]", b"null", b"\xff", b'{"cliPluginsExtraDirs":[],"cliPluginsExtraDirs":[]}',
                 *(json.dumps({"cliPluginsExtraDirs": value}).encode() for value in (True, "directory", {}, [None], [""], ["bad\x00path"]))]
      for raw in invalid:
        with self.subTest(raw=raw):
          path.write_bytes(raw)
          with self.assertRaises((self.data.Refusal, ValueError)):
            self.data.docker_plugin_dirs(original)
      path.write_bytes(b"{}" + b" " * (self.data.CONFIG_LIMIT - 2))
      self.assertEqual(self.data.docker_plugin_dirs(original), expected)
      with path.open("ab") as output:
        output.write(b" ")
      with self.assertRaisesRegex(self.data.Refusal, "byte limit"):
        self.data.docker_plugin_dirs(original)
      with patch.object(Path, "open", side_effect=PermissionError("PRIVATE_CONFIG_PATH")), self.assertRaises(PermissionError):
        self.data.docker_plugin_dirs(original)
      path.unlink()
      path.mkdir()
      with self.assertRaisesRegex(self.data.Refusal, "must be regular"):
        self.data.docker_plugin_dirs(original)

  def test_docker_plugin_field_aliases_are_rejected_before_defaults(self):
    field = "cliPluginsExtraDirs"
    with owned_temporary_directory() as directory:
      original = Path(directory)
      for alias in ("CLIPluginsExtraDirs", "clipluginsextradirs", "cliPluginſExtraDirs"):
        for value in (None, [], ["PRIVATE_CONFIG_PATH"]):
          for config in ({alias: value}, {field: [], alias: value}, {alias: value, field: []}):
            with self.subTest(config=config):
              (original / "config.json").write_text(json.dumps(config))
              with self.assertRaisesRegex(self.data.Refusal, "requires canonical cliPluginsExtraDirs spelling") as raised:
                self.data.docker_plugin_dirs(original)
              self.assertNotIn(alias, str(raised.exception))
              self.assertNotIn("PRIVATE_CONFIG_PATH", str(raised.exception))

  def test_lock_bootstrap_errors_close_descriptors_and_hide_os_details(self):
    with owned_temporary_directory() as directory:
      path = Path(directory) / ".template-operation.lock"
      with patch.object(self.data.os, "open", side_effect=PermissionError("PRIVATE_LOCK_PATH")), \
           patch.object(self.data.os, "close") as close:
        with self.assertRaises(self.data.SetupRefusal) as raised:
          self.data.locked(directory, "unused")
        self.assertEqual(raised.exception.phase, "checkout locking")
        self.assertIn("checkout access", raised.exception.advice)
        self.assertNotIn("PRIVATE_LOCK_PATH", str(raised.exception))
        close.assert_not_called()
      failures = (BlockingIOError(errno.EAGAIN, "PRIVATE_LOCK_PATH"), PermissionError("PRIVATE_LOCK_PATH"),
                  OSError(errno.ENOSPC, "PRIVATE_LOCK_PATH"))
      for failure in failures:
        with self.subTest(failure=type(failure).__name__):
          fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
          with patch.object(self.data.os, "open", return_value=fd), patch.object(self.data.fcntl, "flock", side_effect=failure):
            with self.assertRaises(self.data.SetupRefusal) as raised:
              self.data.locked(directory, "unused")
          self.assertEqual(raised.exception.phase, "checkout locking")
          self.assertNotIn("PRIVATE_LOCK_PATH", str(raised.exception))
          with self.assertRaises(OSError):
            os.fstat(fd)
      fd = os.open(path, os.O_RDWR)
      with patch.object(self.data.os, "open", return_value=fd), \
           patch.object(self.data.subprocess, "Popen", side_effect=OSError(errno.EAGAIN, "PRIVATE_CHILD_PATH")):
        with self.assertRaises(self.data.SetupRefusal) as raised:
          self.data.locked(directory, "unused")
      self.assertEqual(raised.exception.phase, "locked child startup")
      self.assertIn("Bash availability", raised.exception.advice)
      self.assertNotIn("PRIVATE_CHILD_PATH", str(raised.exception))
      with self.assertRaises(OSError):
        os.fstat(fd)
      with path.open() as available:
        self.data.fcntl.flock(available, self.data.fcntl.LOCK_EX | self.data.fcntl.LOCK_NB)

  def test_lock_bootstrap_retains_child_status_and_descriptor_inheritance(self):
    with owned_temporary_directory() as directory, patch.object(self.data.subprocess, "Popen") as start, \
         patch.object(self.data.signal, "signal"):
      start.return_value.wait.return_value = 7
      self.assertEqual(self.data.locked(directory, "fixture-release.sh"), 7)
      self.assertEqual(start.call_args.args[0], ["bash", "fixture-release.sh"])
      fd, = start.call_args.kwargs["pass_fds"]
      self.assertEqual(start.call_args.kwargs["env"]["RELEASE_LOCK_FD"], str(fd))
      self.assertTrue(start.call_args.kwargs["start_new_session"])
      with self.assertRaises(OSError):
        os.fstat(fd)

  def test_optional_temporary_parent_runs_real_bearer_and_publication_setup(self):
    real_directory = tempfile.TemporaryDirectory
    real_is_dir = Path.is_dir
    real_mkdir = os.mkdir
    with owned_temporary_directory() as directory:
      base = Path(directory)
      preferred, fallback = base / "preferred", base / "fallback"
      preferred.mkdir()
      fallback.mkdir()
      for present in (True, False):
        chosen = []
        def is_dir(path):
          return present if path == Path("/tmp/opencode") else real_is_dir(path)
        def create(*args, **kwargs):
          if kwargs.get("dir") == "/tmp/opencode":
            self.assertTrue(present, "Absent preferred parent must not be selected")
            kwargs["dir"] = str(preferred)
          result = real_directory(*args, **kwargs)
          chosen.append(Path(result.name).parent)
          return result
        def mkdir(path, *args, **kwargs):
          self.assertNotEqual(Path(path).parent, Path("/tmp/opencode"), "Do not create beneath the simulated missing global parent")
          return real_mkdir(path, *args, **kwargs)
        with self.subTest(present=present), patch.object(Path, "is_dir", is_dir), \
             patch.object(tempfile, "TemporaryDirectory", create), patch.object(tempfile, "tempdir", None), \
             patch.dict(os.environ, {"TMPDIR": str(fallback)}), patch.object(os, "mkdir", mkdir):
          self.test_same_origin_bearer_challenge_retries_with_private_token()
          publication = BashPublicationTests()
          try:
            publication.setUp()
            self.assertTrue(publication.root.is_dir())
            self.assertEqual(chosen, [preferred if present else fallback] * 2)
          finally:
            publication.doCleanups()

  def http_reply(self, status, body, headers=None):
    raw = "HTTP/1.1 " + str(status) + " Fixture\r\n"
    raw += "".join(key + ": " + value + "\r\n" for key, value in (headers or {}).items()) + "\r\n"
    return 0, {"stdout": str(status).encode(), "headers": raw.encode(), "body": body}

  def association_records(self):
    config = {"gitea": "https://fixture.invalid", "repository": "fixtures/application",
              "image": "fixture.invalid/fixtures/application-hello"}
    repository = {"id": 17, "name": "application", "full_name": "fixtures/application", "owner": {"login": "fixtures"}}
    package = {"id": 23, "name": "application-hello", "type": "container", "version": "latest",
               "owner": {"login": "fixtures"}, "repository": None}
    return config, repository, package

  def test_association_routes_distinguish_image_and_repository_and_quote_segments(self):
    config, _, _ = self.association_records()
    self.assertEqual(self.data.package_routes(config), (
      "https://fixture.invalid/api/v1/repos/fixtures/application",
      "https://fixture.invalid/api/v1/packages/fixtures/container/application-hello/latest",
      "https://fixture.invalid/api/v1/packages/fixtures/container/application-hello/-/link/application"))
    routes = self.data.package_routes(config | {"repository": "fixtures/a?b", "image": "fixture.invalid/fixtures/a#b"})
    self.assertTrue(routes[0].endswith("/a%3Fb"))
    self.assertTrue(routes[1].endswith("/a%23b/latest"))
    self.assertTrue(routes[2].endswith("/-/link/a%3Fb"))

  def test_association_requires_explicit_null_and_strict_package_identity(self):
    config, repository, package = self.association_records()
    invalid = [None, [], {}, package | {"owner": None}, package | {"owner": {"login": "foreign"}},
               package | {"type": "generic"}, package | {"name": "foreign"}, package | {"version": "other"},
               package | {"id": True}, package | {"repository": {}}, package | {"repository": False},
               {key: value for key, value in package.items() if key != "repository"}]
    for record in invalid:
      with self.subTest(record=record), patch.object(self.data, "api_document", return_value=record), self.assertRaises(self.data.Refusal):
        self.data.package_linked("unused", config, "unused", repository["id"])
    with patch.object(self.data, "api_document", return_value=package):
      self.assertFalse(self.data.package_linked("unused", config, "unused", repository["id"]))
    with patch.object(self.data, "api_document", return_value=package | {"repository": repository}):
      self.assertTrue(self.data.package_linked("unused", config, "unused", repository["id"]))

  def test_association_repository_identity_rejects_name_and_id_lookalikes(self):
    config, repository, package = self.association_records()
    for record in (repository | {"id": True}, repository | {"id": 0}, repository | {"id": "17"},
                   repository | {"full_name": "foreign/application"}, repository | {"name": "foreign"},
                   repository | {"owner": {"login": "foreign"}}, repository | {"id": 99}):
      with self.subTest(record=record), patch.object(self.data, "api_document", return_value=package | {"repository": record}), \
           self.assertRaises(self.data.Refusal):
        self.data.package_linked("unused", config, "unused", repository["id"])

  def test_package_check_is_read_only_and_refuses_unlinked(self):
    config, repository, package = self.association_records()
    for linked in (None, repository):
      with self.subTest(linked=linked), patch.object(self.data, "api_document", side_effect=[repository, package | {"repository": linked}]), \
           patch.object(self.data, "http") as http:
        if linked is None:
          with self.assertRaises(self.data.Refusal):
            self.data.package_association("unused", config)
        else:
          self.data.package_association("unused", config)
        http.assert_not_called()

  def test_association_empty_201_and_lost_transport_reconcile_exactly_once(self):
    config, repository, package = self.association_records()
    for version in ("1.25.0", "1.25.1", "1.25.123", "28.2.0"):
      for post in ((201, {}, b""), self.data.CommandFailed("HTTPS request failed")):
        replies = [(200, {}, self.data.canonical(record)) for record in (repository, package, {"version": version}, repository, package)]
        replies += [post, (200, {}, self.data.canonical(package | {"repository": repository}))]
        with self.subTest(version=version, post=post), patch.object(self.data, "http", side_effect=replies) as http:
          self.data.package_association("unused", config, ensure=True)
          self.assertEqual([call.args[1] for call in http.call_args_list], ["GET", "GET", "GET", "GET", "GET", "POST", "GET"])
          self.assertEqual(http.call_args_list[5].args[2], self.data.package_routes(config)[2])
          self.assertEqual(http.call_args_list[5].kwargs, {})

  def test_association_refusal_after_post_never_reconciles(self):
    config, repository, package = self.association_records()
    for failure in (self.data.Refusal("Command output exceeds byte limit"), (401, {}, b"PRIVATE_REMOTE_BODY"),
                    (404, {}, b"PRIVATE_REMOTE_BODY"), (200, {}, b"PRIVATE_REMOTE_BODY")):
      with self.subTest(failure=failure), \
           patch.object(self.data, "api_document", side_effect=[repository, package, {"version": "1.25.0"}, repository, package]) as read, \
           patch.object(self.data, "http", side_effect=[failure]) as http:
        with self.assertRaises(self.data.Refusal) as raised:
          self.data.package_association("unused", config, ensure=True)
        self.assertNotIn("PRIVATE_REMOTE_BODY", str(raised.exception))
        self.assertEqual(read.call_count, 5)
        self.assertEqual(http.call_count, 1)

  def test_package_link_http_accepts_empty_201_without_json_parsing(self):
    with patch.object(self.data, "capture", return_value=self.http_reply(201, b"")):
      self.assertEqual(self.data.http("unused", "POST", "https://fixture.invalid/link"), (201, {}, b""))

  def test_unknown_server_contract_cannot_authorize_link_writes(self):
    config, repository, package = self.association_records()
    versions = (None, True, 28.2, [], {}, "1.24.6", "1.26.0", "1.25.0-dev", "1.25.00",
                "28.2.1", "28.1.0", "28.3.0", "29.0.0", "28.2", "v28.2.0", "28.2.00",
                "28.2.0-dev", "28.2.0+custom", " 28.2.0", "28.2.0\n", "", "PRIVATE_REMOTE_BODY")
    for server in (None, [], {}, *({"version": version} for version in versions)):
      with self.subTest(server=server), patch.object(self.data, "api_document", side_effect=[repository, package, server]) as read, \
           patch.object(self.data, "http") as http:
        with self.assertRaises(self.data.Refusal) as raised:
          self.data.package_association("unused", config, ensure=True)
        self.assertNotIn("PRIVATE_REMOTE_BODY", str(raised.exception))
        self.assertEqual(str(raised.exception), "Package link writes require supported stable Gitea 1.25.x or exact 28.2.0; server association safety is unverified")
        self.assertEqual(read.call_count, 3)
        http.assert_not_called()

  def test_correct_association_needs_no_server_version_even_for_unknown_contracts(self):
    config, repository, package = self.association_records()
    for version in ("1.24.6", "28.2.1", "29.0.0", "28.2.0-dev", None):
      with self.subTest(version=version), \
           patch.object(self.data, "api_document", side_effect=[repository, package | {"repository": repository}, {"version": version}]) as read, \
           patch.object(self.data, "http") as http:
        self.data.package_association("unused", config, ensure=True)
        self.assertEqual([call.args[1] for call in read.call_args_list], list(self.data.package_routes(config)[:2]))
        http.assert_not_called()

  def test_lost_link_response_requires_exact_readback_not_another_post(self):
    config, repository, package = self.association_records()
    for record in (package, package | {"repository": repository | {"id": 99}}, None):
      replies = [(200, {}, self.data.canonical(value)) for value in (repository, package, {"version": "1.25.0"}, repository, package)]
      replies += [self.data.CommandFailed("HTTPS request failed"), (200, {}, self.data.canonical(record))]
      with self.subTest(record=record), patch.object(self.data, "http", side_effect=replies) as http, \
           self.assertRaises(self.data.Refusal):
        self.data.package_association("unused", config, ensure=True)
      self.assertEqual([call.args[1] for call in http.call_args_list].count("POST"), 1)
      self.assertEqual(http.call_count, 7)

  def test_refreshed_correct_link_skips_post_and_preserves_other_fields(self):
    config, repository, package = self.association_records()
    records = [repository, package, {"version": "1.25.0"}, repository,
               package | {"repository": repository, "html_url": "https://untrusted.invalid"}]
    with patch.object(self.data, "api_document", side_effect=records), patch.object(self.data, "http") as http:
      self.data.package_association("unused", config, ensure=True)
      http.assert_not_called()

  def test_same_origin_bearer_challenge_retries_with_private_token(self):
    body = b'{"schemaVersion":2}'
    digest = self.data.sha(body)
    replies = [self.http_reply(401, b"{}", {"WWW-Authenticate": 'Bearer realm="https://fixture.invalid/token",service="registry"'}),
               self.http_reply(200, b'{"token":"FIXTURE_BEARER_TOKEN"}'),
               self.http_reply(200, body, {"Docker-Content-Digest": digest})]
    with owned_temporary_directory(prefix="bash-release-bearer-") as work, patch.object(self.data, "capture", side_effect=replies) as capture:
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
root=unused work=unused commit=unused predecessor='' prepared=digest promotion_confirmed=false
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

  def test_alias_guard_confirmation_and_failures_in_conditional_callers(self):
    script = '''set -Eeuo pipefail
source "$1"
root=unused work=unused predecessor=old prepared=new
if [[ "$2" != unset ]]; then promotion_confirmed=$2; fi
observed=$3 status=$4
data() { printf '%s\\n' "$observed"; return "$status"; }
if alias_guard; then echo continued; fi
'''
    for phase in ("false", "true", "unset"):
      for observed in ("old", "new", "", "foreign"):
        for status in (0, 1, 2):
          with self.subTest(phase=phase, observed=observed, status=status):
            result = subprocess.run(["bash", "-c", script, "fixture", str(ROOT / "scripts/release-common.sh"), phase, observed, str(status)],
                                    capture_output=True, text=True)
            accepted = status == 0 and (observed == "new" or (phase != "true" and observed == "old"))
            self.assertEqual(result.returncode == 0, accepted, result.stdout + result.stderr)
            self.assertEqual("continued" in result.stdout, accepted)

  def test_bounded_capture_exact_limit_and_overflow(self):
    output = self.data.command([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x'*64)"], 64)
    self.assertEqual(len(output), 64)
    with self.assertRaisesRegex(self.data.Refusal, "byte limit"):
      self.data.command([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x'*65)"], 64)

  def test_association_guard_failures_remain_fatal_in_conditional_callers(self):
    script = '''set -Eeuo pipefail
source "$1"
root=unused work=$2 commit=commit prepared=digest
fault=$3 fault_status=$4
scan() { :; }
tag_state() { remote_oid=tag remote_commit=commit release_record='{}'; }
data() {
  if [[ "$1" == "$fault" ]]; then return "$fault_status"; fi
  case "$1" in
    image|resolve) echo digest ;;
    package-ensure) echo mutation ;;
    release-check|package-check) : ;;
    *) exit 10 ;;
  esac
}
if associate_package tag; then echo continued; fi
'''
    with tempfile.TemporaryDirectory() as work:
      for fault in ("release-check", "image", "resolve"):
        for status in (1, 2):
          with self.subTest(fault=fault, status=status):
            result = subprocess.run(["bash", "-c", script, "fixture", str(ROOT / "scripts/release-common.sh"), work, fault, str(status)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("mutation", result.stdout)
            self.assertNotIn("continued", result.stdout)

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


def association_on_gitea_28(test):
  """Repeat an existing scenario with its own unittest setUp/cleanup lifecycle."""
  def run(self):
    self.change(gitea_version="28.2.0")
    test(self)
  run.__name__ = test.__name__ + "_gitea_28_2_0"
  return run


# Originals retain the fixture's 1.25.0 default. Each generated case gets fresh Git,
# token, server state, and event files; fake behavior models the reviewed source.
for scenario in (
  "test_fresh_release_links_only_configured_package_and_verifies_it",
  "test_fresh_release_preserves_correct_link_without_post",
  "test_fresh_release_refuses_conflicting_link_without_rollback",
  "test_completed_retry_finishes_only_missing_link_then_becomes_read_only",
  "test_completed_retry_refuses_foreign_association_without_writes",
  "test_lost_link_response_is_reconciled_without_repeating_post",
  "test_hidden_foreign_link_is_refused_by_supported_server_without_reassignment",
  "test_link_failures_preserve_publication_and_never_repeat_post",
  "test_failed_association_prerequisite_never_authorizes_link",
  "test_refreshed_identity_failure_blocks_link",
  "test_post_link_verification_failure_does_not_undo_accepted_link",
  "test_publication_change_after_link_prevents_success_without_rollback",
):
  case = association_on_gitea_28(getattr(BashPublicationTests, scenario))
  setattr(BashPublicationTests, case.__name__, case)
