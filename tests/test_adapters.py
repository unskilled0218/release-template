import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import subprocess
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from release_template.adapters import Gitea, HTTP, Registry, Runner, git_identity, preflight
from release_template.core import ReleaseError, canonical, digest
from release_template.cleanup import plan, digest_owned
from release_template.oci import OCI_MANIFEST, INDEX_TYPES, IMAGE_CONFIGS, EMPTY_CONFIG, ATTESTATION_LAYER, runnable
from tests.support import COMMIT, FakeRegistry, FakeRunner, configuration, package


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
    return configuration() | {"gitea": self.origin, "registry": self.origin.removeprefix("http://"), "test_http": True}

  def put(self, value):
    reference = digest(canonical(value))
    self.content[reference] = value
    return reference

  def image(self, architecture="amd64", os_name="linux", labels=None):
    labels = self.labels() if labels is None else labels
    config = self.put({"architecture": architecture, "os": os_name, "config": {"Labels": labels}})
    return self.put({"schemaVersion": 2, "mediaType": OCI_MANIFEST,
      "config": {"mediaType": IMAGE_CONFIGS[0], "digest": config}, "layers": []})

  def labels(self):
    return {"org.opencontainers.image.revision": COMMIT, "org.opencontainers.image.version": "1.0.0",
            "org.opencontainers.image.source": self.origin + "/fixtures/application"}

  def index(self, descriptors):
    return self.put({"schemaVersion": 2, "mediaType": INDEX_TYPES[0], "manifests": descriptors})

  def verify(self, root, platforms=("linux/amd64", "linux/arm64")):
    return Registry(self.config(), "fixture", "token").verify("application", root, platforms,
      COMMIT, "1.0.0", self.labels()["org.opencontainers.image.source"])

  def attestation(self, subject):
    config = self.put({"architecture": "unknown", "os": "unknown"})
    manifest = self.put({"schemaVersion": 2, "mediaType": OCI_MANIFEST,
      "config": {"mediaType": IMAGE_CONFIGS[0], "digest": config},
      "layers": [{"mediaType": ATTESTATION_LAYER, "digest": digest(b"attestation")}],
      "subject": {"digest": subject}})
    return {"digest": manifest, "platform": {"os": "unknown", "architecture": "unknown"},
      "annotations": {"vnd.docker.reference.type": "attestation-manifest", "vnd.docker.reference.digest": subject}}

  def test_capped_page_size_does_not_stop_enumeration(self):
    api = Gitea(self.config(), "fixture-token")
    self.assertEqual([item["id"] for item in api.releases()], [1, 2])
    self.assertEqual(len(self.requests), 3)
    self.assertTrue(all(auth == "token fixture-token" for _, auth in self.requests))

  def test_repeated_pagination_fails_instead_of_looping_or_deleting(self):
    self.pages = [[{"id": 1}]]
    with self.assertRaisesRegex(ReleaseError, "advance"):
      Gitea(self.config(), "fixture").releases()

  def test_no_redirects_forward_authorization(self):
    with self.assertRaisesRegex(ReleaseError, "302"):
      HTTP(self.origin, True).request("GET", "/redirect", {"Authorization": "secret"})
    self.assertEqual(len(self.requests), 1)

  def test_package_paths_encode_nested_names_and_digest_versions(self):
    api = Gitea(self.config(), "fixture")
    self.assertEqual(api.package_path("nested/name", "sha256:abc"),
                     "/api/v1/packages/fixtures/container/nested%2Fname/sha256%3Aabc")

  def test_nested_index_and_attestation_graph_verify_labels_platforms_and_bearer_auth(self):
    self.challenge = True
    labels = {"org.opencontainers.image.revision": COMMIT, "org.opencontainers.image.version": "1.0.0",
              "org.opencontainers.image.source": self.origin + "/fixtures/application"}
    manifests = [self.image(architecture) for architecture in ("amd64", "arm64")]
    attestation = self.attestation(manifests[0])
    manifests.append(attestation["digest"])
    nested = self.index([{"digest": reference} for reference in manifests[:2]] + [attestation])
    root = self.index([{"digest": nested}])
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

  def test_extra_runnable_architecture_is_not_an_attestation(self):
    labels = {"org.opencontainers.image.revision": COMMIT, "org.opencontainers.image.version": "1.0.0",
              "org.opencontainers.image.source": self.origin + "/fixtures/application"}
    manifests = []
    for architecture in ("amd64", "arm64", "riscv64"):
      config = self.put({"architecture": architecture, "os": "linux", "config": {"Labels": labels}})
      manifests.append(self.put({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": config}, "layers": []}))
    root = self.put({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json",
      "manifests": [{"digest": reference} for reference in manifests]})
    with self.assertRaises(ReleaseError):
      Registry(self.config(), "fixture", "token").verify("application", root, ["linux/amd64", "linux/arm64"],
        COMMIT, "1.0.0", labels["org.opencontainers.image.source"])

  def test_extra_unlabeled_image_and_malformed_platforms_fail_closed(self):
    required = [{"digest": self.image(architecture)} for architecture in ("amd64", "arm64")]
    for architecture, os_name, labels in (("riscv64", "linux", {}), ("unknown", "linux", {}),
                                           (None, "linux", {}), ("amd64", None, {})):
      with self.subTest(architecture=architecture, os_name=os_name):
        root = self.index(required + [{"digest": self.image(architecture, os_name, labels)}])
        with self.assertRaises(ReleaseError):
          self.verify(root)

  def test_missing_or_conflicting_runnable_labels_fail(self):
    for labels in ({}, self.labels() | {"org.opencontainers.image.revision": "wrong"},
                   self.labels() | {"org.opencontainers.image.version": "wrong"},
                   self.labels() | {"org.opencontainers.image.source": "wrong"}):
      with self.subTest(labels=labels), self.assertRaisesRegex(ReleaseError, "labels"):
        self.verify(self.image(labels=labels), ["linux/amd64"])

  def test_duplicate_platforms_and_conflicting_shared_descriptors_fail(self):
    first = self.image()
    second = self.image(labels=self.labels() | {"unrelated": "different content"})
    for descriptors in ([{"digest": first}, {"digest": first}],
                        [{"digest": first}, {"digest": second}],
                        [{"digest": first, "platform": {"os": "linux", "architecture": "arm64"}}],
                        [{"digest": first, "mediaType": INDEX_TYPES[0]}]):
      with self.subTest(descriptors=descriptors), self.assertRaises(ReleaseError):
        self.verify(self.index(descriptors), ["linux/amd64"])
    left = self.index([{"digest": first, "platform": {"os": "linux", "architecture": "amd64"}}])
    right = self.index([{"digest": first, "platform": {"os": "linux", "architecture": "arm64"}}])
    with self.assertRaises(ReleaseError):
      self.verify(self.index([{"digest": left}, {"digest": right}]), ["linux/amd64"])

  def test_explicit_oci_artifact_preserves_subject_without_counting_its_platform(self):
    subject = self.image("riscv64")
    artifact = self.put({"schemaVersion": 2, "mediaType": OCI_MANIFEST,
      "artifactType": "application/vnd.example.verification+json",
      "config": {"mediaType": EMPTY_CONFIG, "digest": self.put({})},
      "layers": [{"mediaType": "application/vnd.example.verification+json", "digest": digest(b"report")}],
      "subject": {"digest": subject}})
    required = [self.image(architecture) for architecture in ("amd64", "arm64")]
    root = self.index([{"digest": item} for item in required + [artifact]])
    graph = self.verify(root)
    self.assertTrue({root, artifact, subject, *required} <= graph)
    _, evidence = Registry(self.config(), "fixture", "token").graph("application", root)
    self.assertEqual(len(runnable(evidence)), 2)
    self.assertEqual(len(runnable(evidence, include_subjects=True)), 3)

  def test_artifact_marker_cannot_hide_a_runnable_image(self):
    image = self.image("riscv64")
    for descriptor in ({"digest": image, "annotations": {"vnd.docker.reference.type": "attestation-manifest"}},
                       {"digest": image, "platform": {"os": "unknown", "architecture": "unknown"},
                        "annotations": {"vnd.docker.reference.type": "attestation-manifest",
                                        "vnd.docker.reference.digest": self.image()}}):
      with self.subTest(descriptor=descriptor), self.assertRaises(ReleaseError):
        self.verify(self.index([{"digest": self.image()}, descriptor]), ["linux/amd64"])
    contradictory = self.content[image] | {"artifactType": "application/vnd.example.artifact"}
    with self.assertRaises(ReleaseError):
      self.verify(self.put(contradictory), ["linux/riscv64"])

  def test_incomplete_attestation_evidence_and_mixed_roles_fail(self):
    subject = self.image()
    valid = self.attestation(subject)
    malformed = [valid | {"annotations": {}}, valid | {"platform": {"os": "linux", "architecture": "amd64"}},
                 valid | {"annotations": valid["annotations"] | {"vnd.docker.reference.digest": digest(b"missing")}}]
    for descriptor in malformed:
      with self.subTest(descriptor=descriptor), self.assertRaises(ReleaseError):
        self.verify(self.index([{"digest": subject}, descriptor]), ["linux/amd64"])
    left = self.index([valid])
    right = self.index([{"digest": valid["digest"]}])
    with self.assertRaises(ReleaseError):
      self.verify(self.index([{"digest": subject}, {"digest": left}, {"digest": right}]), ["linux/amd64"])

  def test_real_nested_graph_protects_preserved_alias_and_attestation_dependencies(self):
    child = self.image()
    attestation = self.attestation(child)
    nested = self.index([{"digest": child}, attestation])
    old = self.index([{"digest": nested}])
    current = self.image(labels=self.labels() | {"org.opencontainers.image.version": "2.0.0"})
    self.content["custom"] = self.content[old]
    registry = Registry(self.config(), "fixture", "token")
    records = [package("application", reference) for reference in (child, nested, old, attestation["digest"], "custom")]
    with tempfile.TemporaryDirectory() as temporary:
      workflow = SimpleNamespace(config=self.config(), release_version="2.0.0", tag="v2.0.0", registry=registry,
        state=SimpleNamespace(path=Path(temporary) / "v2.0.0.json",
          data={"run": "fixture", "outputs": {"application": {"digest": current}}, "staging": {}}),
        gitea=SimpleNamespace(packages=lambda: records, releases=lambda: []))
      # The publication precondition is checked through the real registry, not a no-op.
      workflow.verify_publication = lambda: registry.verify("application", current, ["linux/amd64"], COMMIT,
        "2.0.0", self.labels()["org.opencontainers.image.source"])
      self.assertFalse(plan(workflow)["candidates"])
      _, old_evidence = registry.graph("application", old)
      self.assertTrue(digest_owned(workflow, old_evidence))

  def test_docker_schema_two_image_is_supported(self):
    reference = self.image()
    manifest = self.content[reference] | {"mediaType": "application/vnd.docker.distribution.manifest.v2+json"}
    manifest["config"] = manifest["config"] | {"mediaType": IMAGE_CONFIGS[1]}
    self.verify(self.put(manifest), ["linux/amd64"])

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
        return "ssh://git@gitea.invalid:2222/fixtures/application.git\n"
      return original(arguments, **kwargs)
    runner.run = run
    config = configuration() | {"gitea": "https://gitea.invalid:8443", "registry": "gitea.invalid:8443"}
    self.assertEqual(git_identity(runner, config), COMMIT)
    for invalid in ("https://token@gitea.invalid/fixtures/application.git", "https://other.invalid/fixtures/application.git"):
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
  assert json.loads((p/"config.json").read_text())=={"auths":{"gitea.invalid":{}}}
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
      with runner.docker_auth("gitea.invalid", "fixture", "fixture-token"):
        auth_directory = Path(runner.environment["DOCKER_CONFIG"])
        self.assertTrue(auth_directory.is_dir())
      self.assertFalse(auth_directory.exists())
      self.assertEqual(runner.environment, original)
