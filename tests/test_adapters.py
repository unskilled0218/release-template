import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from release_template.adapters import Forgejo, HTTP, Registry, Runner, git_identity, preflight
from release_template.core import ReleaseError, canonical, digest
from tests.support import COMMIT, FakeRegistry, FakeRunner, configuration


class AdapterTests(unittest.TestCase):
  def setUp(self):
    self.requests = []
    self.pages = [[{"id": 1}], [{"id": 2}], []]
    self.content = {}
    self.bad_digest = False
    self.challenge = False
    case = self

    class Handler(BaseHTTPRequestHandler):
      def log_message(self, *_):
        pass

      def do_GET(self):
        case.requests.append((self.path, self.headers.get("Authorization")))
        if self.path == "/redirect":
          self.send_response(302)
          self.send_header("Location", "https://other.invalid/")
          self.end_headers()
          return
        if self.path.startswith("/token?"):
          self.send_response(200)
          self.end_headers()
          self.wfile.write(b'{"token":"fixture-bearer"}')
          return
        if self.path.startswith("/api/v1/"):
          from urllib.parse import parse_qs, urlsplit
          page = int(parse_qs(urlsplit(self.path).query).get("page", [1])[0])
          self.send_response(200)
          self.end_headers()
          self.wfile.write(canonical(case.pages[min(page - 1, len(case.pages) - 1)]))
          return
        if case.challenge and self.headers.get("Authorization") != "Bearer fixture-bearer":
          self.send_response(401)
          self.send_header("WWW-Authenticate", 'Bearer realm="' + case.origin + '/token",service="fixture"')
          self.end_headers()
          return
        from urllib.parse import unquote
        reference = unquote(self.path.rsplit("/", 1)[-1])
        if reference not in case.content:
          self.send_response(404)
          self.end_headers()
          return
        data = canonical(case.content[reference])
        self.send_response(200)
        self.send_header("Docker-Content-Digest", "sha256:bad" if case.bad_digest else digest(data))
        self.end_headers()
        self.wfile.write(data)

    self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    self.origin = "http://127.0.0.1:" + str(self.server.server_port)
    self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
    self.thread.start()
    self.addCleanup(self.stop)

  def stop(self):
    self.server.shutdown()
    self.server.server_close()
    self.thread.join()

  def config(self):
    return configuration() | {"forgejo": self.origin, "registry": self.origin.removeprefix("http://"), "test_http": True}

  def put(self, value):
    reference = digest(canonical(value))
    self.content[reference] = value
    return reference

  def test_capped_page_size_does_not_stop_enumeration(self):
    api = Forgejo(self.config(), "fixture-token")
    self.assertEqual([item["id"] for item in api.releases()], [1, 2])
    self.assertEqual(len(self.requests), 3)
    self.assertTrue(all(auth == "token fixture-token" for _, auth in self.requests))

  def test_repeated_pagination_fails_instead_of_looping_or_deleting(self):
    self.pages = [[{"id": 1}]]
    with self.assertRaisesRegex(ReleaseError, "advance"):
      Forgejo(self.config(), "fixture").releases()

  def test_no_redirects_forward_authorization(self):
    with self.assertRaisesRegex(ReleaseError, "302"):
      HTTP(self.origin, True).request("GET", "/redirect", {"Authorization": "secret"})
    self.assertEqual(len(self.requests), 1)

  def test_package_paths_encode_nested_names_and_digest_versions(self):
    api = Forgejo(self.config(), "fixture")
    self.assertEqual(api.package_path("nested/name", "sha256:abc"),
                     "/api/v1/packages/fixtures/container/nested%2Fname/sha256%3Aabc")

  def test_nested_index_and_attestation_graph_verify_labels_platforms_and_bearer_auth(self):
    self.challenge = True
    labels = {"org.opencontainers.image.revision": COMMIT, "org.opencontainers.image.version": "1.0.0",
              "org.opencontainers.image.source": self.origin + "/fixtures/application"}
    manifests = []
    for architecture in ("amd64", "arm64", "unknown"):
      config = self.put({"architecture": architecture, "os": "linux", "config": {"Labels": labels}})
      manifests.append(self.put({"schemaVersion": 2, "config": {"digest": config}, "layers": []}))
    nested = self.put({"schemaVersion": 2, "manifests": [{"digest": reference} for reference in manifests]})
    root = self.put({"schemaVersion": 2, "manifests": [{"digest": nested}]})
    self.content["latest"] = self.content[root]
    registry = Registry(self.config(), "fixture", "token")
    self.assertEqual(registry.resolve("application", "latest"), root)
    self.assertEqual(registry.verify("application", root, ["linux/amd64", "linux/arm64"], COMMIT, "1.0.0",
                                    self.origin + "/fixtures/application"), set(manifests) | {root, nested})
    self.assertTrue(any(path.startswith("/token?") for path, _ in self.requests))
    with self.assertRaisesRegex(ReleaseError, "labels"):
      registry.verify("application", root, ["linux/amd64", "linux/arm64"], "wrong", "1.0.0", "wrong")

  def test_registry_absence_is_not_auth_or_digest_failure(self):
    registry = Registry(self.config(), "fixture", "token")
    self.assertIsNone(registry.resolve("application", "absent"))
    self.content["latest"] = {"schemaVersion": 2}
    self.bad_digest = True
    with self.assertRaisesRegex(ReleaseError, "digest"):
      registry.resolve("application", "latest")

  def test_manifest_graph_refuses_mutable_child_descriptors(self):
    root = self.put({"schemaVersion": 2, "manifests": [{"digest": "latest"}]})
    with self.assertRaisesRegex(ReleaseError, "immutable"):
      Registry(self.config(), "fixture", "token").graph("application", root)

  def test_preflight_diagnostics_name_builder_and_missing_platforms(self):
    runner = FakeRunner(FakeRegistry())
    preflight(runner, configuration()["images"])
    with patch.object(runner, "run", return_value="Name: unavailable-arm\nPlatforms: linux/amd64\n"):
      with self.assertRaisesRegex(ReleaseError, "unavailable-arm.*arm64"):
        preflight(runner, configuration()["images"])

  def test_git_checks_both_effective_remotes_and_separates_ssh_registry_ports(self):
    runner = FakeRunner(FakeRegistry())
    original = runner.run
    def run(arguments, **kwargs):
      if arguments[:3] == ["git", "remote", "get-url"]:
        return "ssh://git@forgejo.invalid:2222/fixtures/application.git\n"
      return original(arguments, **kwargs)
    runner.run = run
    config = configuration() | {"forgejo": "https://forgejo.invalid:8443", "registry": "forgejo.invalid:8443"}
    self.assertEqual(git_identity(runner, config), COMMIT)
    for invalid in ("https://token@forgejo.invalid/fixtures/application.git", "https://other.invalid/fixtures/application.git"):
      def bad_fetch(arguments, **kwargs):
        if arguments[:3] == ["git", "remote", "get-url"] and "--push" not in arguments:
          return invalid
        return original(arguments, **kwargs)
      runner.run = bad_fetch
      with self.subTest(invalid=invalid), self.assertRaises(ReleaseError):
        git_identity(runner, configuration())

  def test_runner_redacts_stdout_and_does_not_echo_failed_command_output(self):
    import sys
    with tempfile.TemporaryDirectory() as temporary:
      runner = Runner(temporary, "private-fixture-token")
      output = runner.run([sys.executable, "-c", 'print("private-fixture-token")'])
      self.assertNotIn("private-fixture-token", output)
      with self.assertRaises(ReleaseError) as caught:
        runner.run([sys.executable, "-c", 'print("private-fixture-token"); raise SystemExit(2)'])
      self.assertNotIn("private-fixture-token", str(caught.exception))

  def test_build_snapshot_uses_captured_commit_and_excludes_ignored_files_and_git_state(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      source, snapshot = root / "source", root / "snapshot"
      source.mkdir()
      snapshot.mkdir()
      def git(*arguments):
        return subprocess.check_output(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                                        *arguments], cwd=source, stderr=subprocess.DEVNULL).decode().strip()
      git("init", "-b", "main")
      (source / ".gitignore").write_text(".env\n.release-template/\n")
      (source / "application.txt").write_text("captured version")
      git("add", ".")
      git("commit", "-m", "Fixture source")
      commit = git("rev-parse", "HEAD")
      (source / "application.txt").write_text("later worktree version")
      (source / ".env").write_text("ignored fixture secret")
      Runner(source).archive(commit, snapshot)
      self.assertEqual((snapshot / "application.txt").read_text(), "captured version")
      self.assertFalse((snapshot / ".env").exists())
      self.assertFalse((snapshot / ".git").exists())
      (source / "escape").symlink_to("../outside")
      git("add", "escape")
      git("commit", "-m", "Fixture escaping symlink")
      with self.assertRaisesRegex(ReleaseError, "symlink"):
        Runner(source).archive(git("rev-parse", "HEAD"), snapshot)

  def test_external_fake_docker_preserves_host_and_builder_and_uses_private_auth(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      executable = root / "docker"
      executable.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args=sys.argv[1:]
if args==["context", "show"]:
  print("default")
elif args[:1]==["login"]:
  assert sys.stdin.read()=="fixture-token"
  p=Path(os.environ["DOCKER_CONFIG"])
  assert json.loads((p/"config.json").read_text())=={"auths":{"forgejo.invalid":{}}}
  assert os.environ["DOCKER_HOST"]=="unix:///fixture.sock"
  assert os.environ["BUILDX_BUILDER"]=="fixture-builder"
else:
  raise SystemExit(3)
''')
      executable.chmod(0o755)
      runner = Runner(root, "fixture-token")
      runner.environment.update({"PATH": str(root) + os.pathsep + os.environ["PATH"],
                                 "DOCKER_HOST": "unix:///fixture.sock", "BUILDX_BUILDER": "fixture-builder"})
      original = runner.environment.copy()
      with runner.docker_auth("forgejo.invalid", "fixture", "fixture-token"):
        auth_directory = Path(runner.environment["DOCKER_CONFIG"])
        self.assertTrue(auth_directory.is_dir())
      self.assertFalse(auth_directory.exists())
      self.assertEqual(runner.environment, original)
