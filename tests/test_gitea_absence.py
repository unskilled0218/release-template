"""Operation regressions traverse Gitea's real status/JSON boundary, without network I/O."""

import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

from release_template.adapters import Gitea
from release_template.cleanup import abandon, apply, plan
from release_template.core import ReleaseError, load, require
from release_template.workflow import Workflow
from tests.support import COMMIT, REVISION, FakeGitea, FakeRegistry, FakeRunner, configuration, evidence, package


class GiteaTransport:
  """Only replace HTTP transport; all API methods still decode status and JSON bytes."""

  def __init__(self, backend):
    self.backend = backend
    self.requests, self.overrides = [], {}
    self.base = "/api/v1/repos/fixtures/application/releases"
    self.packages = "/api/v1/packages/fixtures"

  def request(self, method, path, headers=None, body=None, allowed=(200,)):
    self.requests.append((method, path))
    if (method, path) in self.overrides:
      status, value = self.overrides[method, path]
    else:
      status, value = self.response(method, path, body)
    require(status in allowed, f"Remote operation failed with HTTP {status}; no response body logged")
    return status, {}, json.dumps(value).encode() if status != 204 else b""

  def response(self, method, path, body):
    parsed = urlsplit(path)
    if method == "GET" and parsed.path in (self.base, self.packages):
      page = int(parse_qs(parsed.query)["page"][0])
      values = self.backend.releases() if parsed.path == self.base else self.backend.packages()
      return 200, values if page == 1 else []
    if method == "GET" and path == "/api/v1/version":
      return 200, self.backend.get(path)
    if method == "GET" and path.startswith(self.base + "/tags/"):
      record = self.backend.release(unquote(path.removeprefix(self.base + "/tags/")))
      return (404, {}) if record is None else (200, record)
    if method == "POST" and path == self.base:
      payload = json.loads(body)
      self.backend.publish(payload["tag_name"], payload["target_commitish"], payload["body"])
      return 201, self.backend.release(payload["tag_name"])
    if method == "DELETE" and path.startswith(self.base + "/"):
      self.backend.delete_release(int(path.rsplit("/", 1)[1]))
      return 204, None
    if path.startswith(self.packages + "/container/"):
      name, reference = map(unquote, path.removeprefix(self.packages + "/container/").split("/"))
      record = self.backend.get(self.backend.package_path(name, reference), absent=True)
      if method == "GET":
        return (404, {}) if record is None else (200, record)
      if method == "DELETE":
        if record is None:
          return 404, {}
        self.backend.delete_package(name, reference)
        return 204, None
    raise AssertionError("Unexpected fixture request: " + repr((method, path)))


class GiteaAbsenceOperationTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.config = configuration()
    self.registry = FakeRegistry()
    self.runner = FakeRunner(self.registry)
    self.backend = FakeGitea(self.registry)
    self.api = Gitea(self.config, "private-fixture-token")
    self.transport = GiteaTransport(self.backend)
    self.api.http = self.transport
    self.workflow = self.reopen()
    self.evidence = evidence(self.root / "evidence.json")

  def reopen(self):
    return Workflow(self.root, self.config, "1.0.0", REVISION, self.runner, self.registry, self.api, COMMIT)

  def published_staging(self):
    self.workflow.publish()
    staging = self.workflow.state.data["staging"]["application"]["tag"]
    self.backend.package_records.append(package("application", staging))
    self.transport.requests.clear()
    return staging

  def assert_pending_cleanup(self, kind, reference):
    saved = self.reopen().state.data
    candidate = next(item for item in saved["cleanup"]["candidates"] if item["kind"] == kind and
                     item.get("version", item.get("tag")) == reference)
    self.assertFalse(candidate.get("complete", False))
    self.assertFalse(saved["cleanup_complete"])
    self.assertTrue(saved["published"])

  def assert_no_mutations(self):
    self.assertFalse(any(method in ("POST", "DELETE") for method, _ in self.transport.requests), self.transport.requests)

  def test_null_publication_lookup_stops_post_and_valid_404_retry_does_not_rebuild(self):
    path = self.api.base + "/releases/tags/v1.0.0"
    self.transport.overrides["GET", path] = (200, None)
    with self.assertRaises(ReleaseError):
      self.workflow.publish()
    saved = self.reopen().state.data
    self.assertFalse(saved["published"])
    self.assertEqual(saved["operations"]["release"]["status"], "pending")
    self.assertTrue(saved["outputs"])
    self.assertEqual(self.backend.records, [])
    self.assert_no_mutations()
    self.transport.overrides.clear()
    self.reopen().publish()
    self.assertTrue(self.reopen().state.data["published"])
    self.assertEqual(len([call for call in self.runner.calls if call[:3] == ["docker", "buildx", "build"]]), 1)
    self.assertEqual(self.transport.requests.count(("POST", self.transport.base)), 1)
    self.assertEqual(len(self.backend.records), 1)

  def test_null_listed_package_lookup_keeps_staging_and_durable_candidate_pending(self):
    staging = self.published_staging()
    self.transport.overrides["GET", self.api.package_path("application", staging)] = (200, None)
    with self.assertRaises(ReleaseError):
      apply(self.workflow, self.evidence)
    self.assert_no_mutations()
    self.assert_pending_cleanup("package", staging)
    self.assertIsNotNone(self.registry.resolve("application", staging))
    self.assertEqual(self.backend.package_records, [package("application", staging)])

  def test_null_omitted_package_lookup_cannot_reconcile_saved_candidate_absence(self):
    staging = self.published_staging()
    self.workflow.state.data["cleanup"] = plan(self.workflow)
    self.workflow.state.flush()
    before = self.workflow.state.path.read_bytes()
    approval = copy.deepcopy(self.workflow.state.data["cleanup"]["retirement"])
    self.backend.package_records.clear()
    self.transport.overrides["GET", self.api.package_path("application", staging)] = (200, None)
    with self.assertRaises(ReleaseError):
      apply(self.workflow, self.evidence)
    self.assert_no_mutations()
    self.assert_pending_cleanup("package", staging)
    self.assertEqual(self.workflow.state.path.read_bytes(), before)
    self.assertEqual(self.reopen().state.data["cleanup"]["retirement"], approval)

  def test_null_older_release_lookup_stops_retirement_without_affecting_publication(self):
    self.workflow.publish()
    self.backend.records.append({"id": 99, "tag_name": "v0.9.0", "draft": False, "prerelease": False})
    self.transport.requests.clear()
    self.transport.overrides["GET", self.api.base + "/releases/tags/v0.9.0"] = (200, None)
    with self.assertRaises(ReleaseError):
      apply(self.workflow, self.evidence)
    self.assert_no_mutations()
    self.assert_pending_cleanup("release", "v0.9.0")
    self.assertEqual(len(self.backend.records), 2)

  def test_null_abandoned_package_lookup_preserves_selected_checkpoint_and_alias(self):
    old = Workflow(self.root, self.config, "0.9.0", REVISION, self.runner, self.registry, self.api, COMMIT)
    tag = "rt-" + old.state.data["run"] + "-application"
    root = self.registry.add("application", tag, "0.9.0")
    old.state.data["created"] = time.time() - 2 * 86400
    old.state.data["outputs"] = {"application": {"digest": root}}
    old.state.data["staging"] = {"application": {"tag": tag, "digest": root}}
    old.state.flush()
    before = old.state.path.read_bytes()
    self.backend.package_records.append(package("application", tag))
    self.workflow.publish()
    self.transport.requests.clear()
    self.transport.overrides["GET", self.api.package_path("application", tag)] = (200, None)
    with self.assertRaises(ReleaseError):
      abandon(self.workflow, [old.state.data["run"]], 86400, self.evidence)
    self.assert_no_mutations()
    self.assertEqual(old.state.path.read_bytes(), before)
    self.assertFalse(load(old.state.path).get("abandoned", False))
    self.assertEqual(self.registry.resolve("application", tag), root)
    self.assertTrue(self.reopen().state.data["published"])
