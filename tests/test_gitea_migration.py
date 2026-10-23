import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch

from release_template.adapters import Gitea, Runner
from release_template.cleanup import abandon, apply, deletion_environment
from release_template.config import CREDENTIAL_VARIABLES, UNSUPPORTED_CREDENTIAL_VARIABLES, credentials, server_version, validate
from release_template.core import ReleaseError
from release_template.policy import description, metadata
from release_template.workflow import Workflow
from tests.support import COMMIT, REVISION, FakeGitea, FakeRegistry, FakeRunner, configuration, evidence, package


class MigrationContractTests(unittest.TestCase):
  def test_schema_two_gitea_configuration_is_accepted(self):
    config = configuration()
    config.pop("forgejo", None)
    config.update({"schema": 2, "gitea": "https://gitea.invalid", "registry": "gitea.invalid"})
    self.assertEqual(validate(config, Path.cwd()), config)

  def test_legacy_release_prose_keeps_recognized_publication_identity(self):
    identity = {"schema": 1, "version": "1.0.0", "tag": "v1.0.0", "commit": COMMIT, "targets": {}}
    body = description(identity).replace("Gitea Packages", "Forgejo Packages")
    self.assertEqual(metadata({"tag_name": "v1.0.0", "body": body}), identity)

  def test_git_credentials_select_only_the_explicit_fixture_file(self):
    with tempfile.TemporaryDirectory() as temporary:
      token = Path(temporary) / "fixture-token"
      token.write_text("private-fixture-token\n")
      token.chmod(0o600)
      environment = {"HOME": temporary, "GIT_TOKEN": str(token), "GIT_USERNAME": "fixture"}
      self.assertEqual(credentials(environment), ("fixture", "private-fixture-token"))

  def test_old_and_mixed_origin_contracts_are_rejected(self):
    config = configuration()
    for changed in (config | {"schema": 1}, config | {"forgejo": config["gitea"]},
                    {key: value for key, value in config.items() if key != "gitea"} | {"forgejo": config["gitea"]}):
      with self.subTest(config=changed), self.assertRaisesRegex(ReleaseError, "migrate to schema 2"):
        validate(changed, Path.cwd())

  def test_unsupported_credentials_are_rejected_before_any_file_access(self):
    for name in UNSUPPORTED_CREDENTIAL_VARIABLES:
      for value in ("", "fixture-value"):
        with self.subTest(name=name, value=value), patch("release_template.config.Path.stat", side_effect=AssertionError("No token stat permitted")):
          with self.assertRaisesRegex(ReleaseError, "Unsupported credential settings"):
            credentials({"HOME": "/never-read-fixture-home", "GIT_USERNAME": "fixture", name: value})

  def test_missing_empty_or_invalid_login_is_not_an_owner_or_author_fallback(self):
    for values in ({}, {"GIT_USERNAME": ""}, {"GIT_USERNAME": "bad login"}, {"GIT_AUTHOR_NAME": "fixture"}):
      with self.subTest(values=values), patch("release_template.config.Path.stat", side_effect=AssertionError("No token stat permitted")):
        with self.assertRaisesRegex(ReleaseError, "GIT_USERNAME"):
          credentials({"HOME": "/never-read-fixture-home"} | values)

  def test_old_default_file_is_not_an_implicit_fallback(self):
    with tempfile.TemporaryDirectory() as temporary:
      old = Path(temporary) / ".config/forgejo/forgejo-token"
      old.parent.mkdir(parents=True)
      old.write_text("old-fixture-token")
      old.chmod(0o600)
      before = old.read_bytes()
      with self.assertRaisesRegex(ReleaseError, "Cannot read protected token"):
        credentials({"HOME": temporary, "GIT_USERNAME": "fixture"})
      self.assertEqual(old.read_bytes(), before)

  def test_unreadable_token_is_refused_without_relaying_its_content(self):
    with tempfile.TemporaryDirectory() as temporary:
      token = Path(temporary) / "token"
      token.write_text("private-fixture-token")
      token.chmod(0o000)
      with self.assertRaises(ReleaseError) as caught:
        credentials({"HOME": temporary, "GIT_USERNAME": "fixture", "GIT_TOKEN": str(token)})
      self.assertNotIn("private-fixture-token", str(caught.exception))

  def test_runner_isolates_exact_credential_names_but_preserves_native_git_settings(self):
    credentials_environment = dict.fromkeys(CREDENTIAL_VARIABLES + UNSUPPORTED_CREDENTIAL_VARIABLES, "fixture-setting")
    native = {"GIT_SSH_COMMAND": "ssh -F /fixture/config", "GIT_AUTHOR_NAME": "Fixture Author",
              "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
    with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, credentials_environment | native):
      runner = Runner(temporary, "private-fixture-token")
      self.assertTrue(all(name not in runner.environment for name in credentials_environment))
      output = runner.run([sys.executable, "-B", "-c", "import json,os; print(json.dumps({key:os.environ.get(key) for key in " +
                           repr(list(credentials_environment) + list(native)) + "}))"])
      environment = json.loads(output)
      self.assertTrue(all(environment[name] is None for name in credentials_environment))
      self.assertEqual({name: environment[name] for name in native}, native)

  def test_full_server_versions_preserve_identity_and_reject_lossy_inputs(self):
    for value in ("1.26.4", "28.2.0", "29.0.0+dev-160-g55186ca39b", "28.2.0-rc.1+build.7"):
      self.assertEqual(server_version(value), value)
    for value in (None, 17, "17", "1.26", "01.26.4", "1.26.4\n", " 1.26.4", "1.26.4-01", "1.26.4+", "x" * 129):
      with self.subTest(value=value), self.assertRaises(ReleaseError):
        server_version(value)


class GiteaHTTPContractTests(unittest.TestCase):
  def setUp(self):
    self.routes, self.requests = {}, []
    case = self
    class Handler(BaseHTTPRequestHandler):
      def log_message(self, *_):
        pass

      def operation(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        payload = json.loads(data) if data else None
        case.requests.append((self.command, self.path, self.headers.get("Authorization"), payload))
        status, response = case.routes.get((self.command, self.path), (404, {}))
        self.send_response(status)
        self.end_headers()
        if status != 204:
          self.wfile.write(response if isinstance(response, bytes) else json.dumps(response).encode())

      do_GET = do_POST = do_DELETE = operation

    self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
    self.thread.start()
    self.addCleanup(self.stop)
    self.origin = "http://127.0.0.1:" + str(self.server.server_port)
    self.config = configuration() | {"gitea": self.origin, "registry": self.origin.removeprefix("http://"), "test_http": True}
    self.api = Gitea(self.config, "private-fixture-token")
    self.base = "/api/v1/repos/fixtures/application"

  def stop(self):
    self.server.shutdown()
    self.server.server_close()
    self.thread.join()

  def test_release_creation_uses_gitea_payload_header_and_no_attachment_operations(self):
    self.routes["POST", self.base + "/releases"] = (201, {"id": 7})
    self.api.publish("v1.2.3", COMMIT, "Gitea package release")
    self.assertEqual(self.requests, [("POST", self.base + "/releases", "token private-fixture-token",
      {"tag_name": "v1.2.3", "target_commitish": COMMIT, "name": "v1.2.3", "body": "Gitea package release",
       "draft": False, "prerelease": False})])
    self.assertNotIn("private-fixture-token", self.requests[0][1])

  def test_release_lookup_and_deletion_distinguish_absence_from_auth_failure(self):
    path = self.base + "/releases/tags/v1.2.3%2Fnotes"
    record = {"id": 7, "tag_name": "v1.2.3/notes", "body": "text", "assets": [], "draft": False, "prerelease": False}
    self.routes["GET", path] = (200, record)
    self.assertEqual(self.api.release("v1.2.3/notes"), record)
    for status in (204, 404):
      self.routes["DELETE", self.base + "/releases/7"] = (status, {})
      self.api.delete_release(7)
    self.routes["GET", path] = (404, {})
    self.assertIsNone(self.api.release("v1.2.3/notes"))
    for status in (401, 403, 500):
      self.routes["GET", path] = (status, {"message": "private-fixture-token"})
      with self.subTest(status=status), self.assertRaises(ReleaseError) as caught:
        self.api.release("v1.2.3/notes")
      self.assertNotIn("private-fixture-token", str(caught.exception))

  def test_package_lookup_and_delete_use_owner_scope_and_encoded_version(self):
    path = "/api/v1/packages/fixtures/container/nested%2Fimage/sha256%3Aabc"
    record = package("nested/image", "sha256:abc")
    self.routes["GET", path] = (200, record)
    self.assertEqual(self.api.package_path("nested/image", "sha256:abc"), path)
    self.assertEqual(self.api.get(path), record)
    for status in (204, 404):
      self.routes["DELETE", path] = (status, {})
      self.api.delete_package("nested/image", "sha256:abc")
    self.assertTrue(all(request[2] == "token private-fixture-token" for request in self.requests))

  def test_capped_package_pages_are_exhausted_with_container_filter(self):
    path = "/api/v1/packages/fixtures?type=container&page={}\u0026limit=100"
    for page, records in enumerate(([package("application", "v1.0.0")], [package("application", "latest")], []), 1):
      self.routes["GET", path.format(page)] = (200, records)
    self.assertEqual(len(self.api.packages()), 2)
    self.assertEqual(len(self.requests), 3)

  def test_malformed_release_json_records_and_pages_fail_closed(self):
    path = self.base + "/releases/tags/v1.0.0"
    for response in ([], "wrong shape", b"not-json"):
      self.routes["GET", path] = (200, response)
      with self.subTest(response=response), self.assertRaises(ReleaseError):
        self.api.release("v1.0.0")
    self.routes["GET", self.base + "/releases?page=1&limit=100"] = (200, {"message": "not a page"})
    with self.assertRaisesRegex(ReleaseError, "array"):
      self.api.releases()

  def test_version_response_shape_can_be_consumed_by_the_exact_version_gate(self):
    version = "29.0.0+dev-160-g55186ca39b"
    self.routes["GET", "/api/v1/version"] = (200, {"version": version})
    with tempfile.TemporaryDirectory() as temporary:
      path = evidence(Path(temporary) / "evidence.json")
      path.write_text(json.dumps(json.loads(path.read_text()) | {"origin": self.origin, "server_version": version}))
      workflow = type("VersionFixture", (), {"config": self.config, "gitea": self.api})()
      self.assertEqual(deletion_environment(workflow, path)["server_version"], version)


class DeletionGateMigrationTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.config = configuration()
    self.registry = FakeRegistry()
    self.gitea = FakeGitea(self.registry)
    self.runner = FakeRunner(self.registry)
    self.workflow = Workflow(self.root, self.config, "1.0.0", REVISION, self.runner, self.registry, self.gitea, COMMIT)
    self.workflow.publish()
    self.gitea.package_records.append(package("application", self.workflow.state.data["staging"]["application"]["tag"]))
    self.path = evidence(self.root / "evidence.json")

  def test_forgejo_or_invalid_gitea_evidence_never_authorizes_deletion(self):
    valid = json.loads(self.path.read_text())
    changes = [{"schema": 1, "server_major": 17}, {"product": "forgejo"}, {"product": None},
      {"origin": "https://other.invalid"}, {"server_major": 17}, {"server_version": "17"},
      {"server_version": "28.2.1"}, {"disposable_repository": self.config["repository"]},
      {"disposable_repository": "/"}, {"operator": ""}, {"verified_at": " "},
      {"alias_preserves_shared_manifest": False}, {"digest_deletion_is_scoped": False},
      {"retained_platforms_pullable": False}]
    invalid = [valid | change for change in changes] + [[], None]
    for field in valid:
      invalid.append({key: value for key, value in valid.items() if key != field})
    before = self.workflow.state.path.read_bytes()
    for record in invalid:
      with self.subTest(record=record):
        self.path.write_text(json.dumps(record))
        with self.assertRaises(ReleaseError):
          apply(self.workflow, self.path)
        self.assertEqual(self.gitea.deleted, [])
        self.assertEqual(self.workflow.state.path.read_bytes(), before)
        self.assertTrue(self.workflow.state.data["published"])

  def test_version_gate_preserves_full_exact_identity_across_version_formats(self):
    valid = json.loads(self.path.read_text())
    for version in ("1.26.4", "28.2.0", "29.0.0+dev-160-g55186ca39b", "28.2.0-rc.1+build.7"):
      with self.subTest(version=version), patch.object(self.gitea, "get", return_value={"version": version}):
        self.path.write_text(json.dumps(valid | {"server_version": version}))
        self.assertEqual(deletion_environment(self.workflow, self.path)["server_version"], version)
    self.assertEqual(self.gitea.deleted, [])

  def test_bad_or_unavailable_runtime_version_prevents_cleanup_and_abandonment(self):
    for response in (None, [], {}, {"version": 28}, {"version": "17"}, {"version": "28.2.0+other-build"},
                     {"version": "28.2.0\n"}):
      with self.subTest(response=response), patch.object(self.gitea, "get", return_value=response):
        with self.assertRaises(ReleaseError):
          apply(self.workflow, self.path)
        with self.assertRaises(ReleaseError):
          abandon(self.workflow, ["selected-run"], 86400, self.path)
        self.assertEqual(self.gitea.deleted, [])
    for status in (401, 403, 500):
      with patch.object(self.gitea, "get", side_effect=ReleaseError(f"Remote operation failed with HTTP {status}")):
        with self.assertRaises(ReleaseError):
          apply(self.workflow, self.path)
        self.assertEqual(self.gitea.deleted, [])

  def test_missing_or_foreign_repository_link_is_visible_and_keeps_publication(self):
    original = copy.deepcopy(self.gitea.package_records[0])
    current = self.workflow.state.data["outputs"]["application"]["digest"]
    for association in (None, {}, {"full_name": "other/repository"}):
      with self.subTest(association=association):
        self.gitea.package_records = [original | {"repository": association},
          package("application", current) | {"repository": association}]
        with self.assertRaisesRegex(ReleaseError, "ambiguous"):
          apply(self.workflow, self.path)
        self.assertEqual(self.gitea.deleted, [])
        self.assertFalse(self.workflow.state.data["cleanup_complete"])
        self.assertEqual(len(self.workflow.state.data["cleanup"]["skipped"]), 2)
        self.assertTrue(all("not linked" in item["reason"] for item in self.workflow.state.data["cleanup"]["skipped"]))
        self.assertTrue(self.workflow.state.data["published"])
