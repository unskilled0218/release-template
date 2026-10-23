"""Operation regressions traverse Gitea's real status/JSON boundary, without network I/O."""

import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

from release_template.adapters import Gitea
from release_template.cleanup import abandon, apply, plan, protected_graph
from release_template.core import ReleaseError, load, require, save
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
    data = value if isinstance(value, bytes) else json.dumps(value).encode()
    return status, {}, data if status != 204 else b""

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


class AbandonmentConfirmationTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.config = configuration()
    self.config["images"].append({"name": "sidecar", "platforms": ["linux/amd64"]})
    self.registry = FakeRegistry()
    self.runner = FakeRunner(self.registry)
    self.backend = FakeGitea(self.registry)
    self.api = Gitea(self.config, "private-fixture-token")
    self.transport = GiteaTransport(self.backend)
    self.api.http = self.transport
    self.current = self.reopen()
    self.current.publish()
    self.current_before = self.current.state.path.read_bytes()
    self.calls_before = len(self.runner.calls)
    self.evidence = evidence(self.root / "evidence.json")
    self.transport.requests.clear()

  def reopen(self):
    return Workflow(self.root, self.config, "1.0.0", REVISION, self.runner, self.registry, self.api, COMMIT)

  def old_run(self, version="0.9.0", names=("application",)):
    old = Workflow(self.root, self.config, version, REVISION, self.runner, self.registry, self.api, COMMIT)
    old.state.data["created"] -= 2 * 86400
    for name in names:
      tag = "rt-" + old.state.data["run"] + "-" + name
      root = self.registry.add(name, tag, version)
      old.state.intent("build:" + name, {"tag": tag})
      old.state.data["outputs"][name] = {"digest": root}
      old.state.data["staging"][name] = {"tag": tag, "digest": root}
      self.backend.package_records.append(package(name, tag))
    old.state.flush()
    return old

  def retire(self, *old_runs):
    abandon(self.reopen(), [old.state.data["run"] for old in old_runs], 86400, self.evidence)

  def package_path(self, old, name="application"):
    return self.api.package_path(name, old.state.data["staging"][name]["tag"])

  def assert_preserved(self, old, before, abandoned=False):
    saved = load(old.state.path)
    self.assertEqual(saved, before | ({"abandoned": True} if abandoned else {}))
    self.assertEqual(self.current.state.path.read_bytes(), self.current_before)
    self.current.verify_publication()
    protected = protected_graph(self.current)
    for name, output in before["outputs"].items():
      self.assertIn(output["digest"], protected[name])
    self.assertFalse(any(reference.startswith("sha256:") for kind, name, reference in self.backend.deleted))
    self.assertFalse(any(call[:3] == ["docker", "buildx", "build"] for call in self.runner.calls[self.calls_before:]))

  def test_success_requires_absence_and_repeated_invocation_does_not_delete_twice(self):
    old = self.old_run()
    before = load(old.state.path)
    self.retire(old)
    self.retire(old)
    self.assert_preserved(old, before, abandoned=True)
    tag = before["staging"]["application"]["tag"]
    self.assertIsNone(self.registry.resolve("application", tag))
    self.assertIsNone(self.backend.get(self.backend.package_path("application", tag), absent=True))
    self.assertEqual(self.backend.deleted, [("package", "application", tag)])
    self.assertEqual(self.transport.requests.count(("DELETE", self.package_path(old))), 1)

  def test_successful_no_op_delete_leaves_checkpoint_pending(self):
    old = self.old_run()
    before = load(old.state.path)
    with patch.object(self.backend, "delete_package", return_value=None):
      with self.assertRaisesRegex(ReleaseError, "not yet absent"):
        self.retire(old)
    self.assert_preserved(old, before)
    self.assertIsNotNone(self.registry.resolve("application", before["staging"]["application"]["tag"]))
    self.assertEqual(self.transport.requests.count(("DELETE", self.package_path(old))), 1)
    self.retire(old)
    self.assert_preserved(old, before, abandoned=True)

  def test_invalid_post_delete_confirmation_stops_and_verified_retry_skips_delete(self):
    responses = ((200, None), (200, []), (200, "wrong shape"), (200, b"not-json"),
                 (200, {"id": 99}), (401, {}), (403, {}), (500, {}))
    for index, response in enumerate(responses):
      with self.subTest(response=response):
        old = self.old_run("0.9." + str(index))
        before = load(old.state.path)
        path = self.package_path(old)
        delete = self.backend.delete_package
        def delete_then_override(name, reference):
          delete(name, reference)
          self.transport.overrides["GET", path] = response
        with patch.object(self.backend, "delete_package", side_effect=delete_then_override):
          with self.assertRaises(ReleaseError):
            self.retire(old)
        self.assert_preserved(old, before)
        self.assertIsNone(self.registry.resolve("application", before["staging"]["application"]["tag"]))
        self.transport.overrides.clear()
        self.retire(old)
        self.assert_preserved(old, before, abandoned=True)
        self.assertEqual(self.transport.requests.count(("DELETE", path)), 1)

  def test_connectivity_failure_after_delete_leaves_run_pending_and_retry_reconciles(self):
    old = self.old_run()
    before = load(old.state.path)
    path = self.package_path(old)
    request = self.transport.request
    def disconnected(method, target, *args, **kwargs):
      if method == "GET" and target == path and self.backend.deleted:
        raise ReleaseError("HTTPS operation failed; verify trust and connectivity")
      return request(method, target, *args, **kwargs)
    with patch.object(self.transport, "request", side_effect=disconnected):
      with self.assertRaisesRegex(ReleaseError, "connectivity"):
        self.retire(old)
    self.assert_preserved(old, before)
    self.retire(old)
    self.assert_preserved(old, before, abandoned=True)
    self.assertEqual(self.transport.requests.count(("DELETE", path)), 1)

  def test_package_404_with_still_visible_registry_alias_cannot_complete(self):
    old = self.old_run()
    before = load(old.state.path)
    tag = before["staging"]["application"]["tag"]
    delete = self.backend.delete_package
    def delete_with_stale_alias(name, reference):
      delete(name, reference)
      self.registry.aliases[name, reference] = before["outputs"][name]["digest"]
    with patch.object(self.backend, "delete_package", side_effect=delete_with_stale_alias):
      with self.assertRaisesRegex(ReleaseError, "registry alias is not yet absent"):
        self.retire(old)
    self.assert_preserved(old, before)
    self.registry.aliases.pop(("application", tag))
    self.retire(old)
    self.assert_preserved(old, before, abandoned=True)
    self.assertEqual(self.transport.requests.count(("DELETE", self.package_path(old))), 1)

  def test_disagreement_in_either_remote_view_cannot_authorize_delete(self):
    for index, missing in enumerate(("registry", "package")):
      with self.subTest(missing=missing):
        old = self.old_run("0.9." + str(index))
        before = load(old.state.path)
        tag = before["staging"]["application"]["tag"]
        if missing == "registry":
          self.registry.aliases.pop(("application", tag))
        else:
          self.backend.package_records = [item for item in self.backend.package_records if item["version"] != tag]
        with self.assertRaisesRegex(ReleaseError, "presence differs"):
          self.retire(old)
        self.assert_preserved(old, before)
        self.assertEqual(self.backend.deleted, [])
        self.assertEqual(self.transport.requests.count(("DELETE", self.package_path(old))), 0)
        self.assertIn(("GET", self.package_path(old)), self.transport.requests)

  def test_absent_registry_does_not_bypass_malformed_package_evidence(self):
    old = self.old_run()
    before = load(old.state.path)
    tag = before["staging"]["application"]["tag"]
    self.registry.aliases.pop(("application", tag))
    self.transport.overrides["GET", self.package_path(old)] = (200, None)
    with self.assertRaises(ReleaseError):
      self.retire(old)
    self.assert_preserved(old, before)
    self.assertEqual(self.backend.deleted, [])

  def test_changed_digest_or_foreign_association_cannot_authorize_delete(self):
    for index, change in enumerate(("digest", "association")):
      with self.subTest(change=change):
        old = self.old_run("0.9." + str(index))
        before = load(old.state.path)
        tag = before["staging"]["application"]["tag"]
        if change == "digest":
          self.registry.add("application", tag, "0.8.0")
        else:
          next(item for item in self.backend.package_records if item["version"] == tag)["repository"] = {"full_name": "foreign/project"}
        with self.assertRaisesRegex(ReleaseError, "identity conflict|association differs"):
          self.retire(old)
        self.assert_preserved(old, before)
        self.assertEqual(self.backend.deleted, [])

  def test_lost_delete_response_reopens_checkpoint_and_never_repeats_delete(self):
    for index, failure in enumerate((ReleaseError("Lost response"), SystemExit("Process stopped"))):
      with self.subTest(failure=type(failure).__name__):
        old = self.old_run("0.9." + str(index))
        before = load(old.state.path)
        delete = self.backend.delete_package
        def accepted_then_lost(name, reference):
          delete(name, reference)
          raise failure
        with patch.object(self.backend, "delete_package", side_effect=accepted_then_lost):
          with self.assertRaises(type(failure)):
            self.retire(old)
        self.assert_preserved(old, before)
        self.retire(old)
        self.assert_preserved(old, before, abandoned=True)
        self.assertEqual(self.transport.requests.count(("DELETE", self.package_path(old))), 1)

  def test_interruption_before_or_after_checkpoint_save_retries_without_delete(self):
    for index, boundary in enumerate(("before", "after")):
      with self.subTest(boundary=boundary):
        old = self.old_run("0.9." + str(index))
        before = load(old.state.path)
        def interrupted(path, value):
          if boundary == "after":
            save(path, value)
          raise SystemExit("Stopped at abandonment checkpoint boundary")
        with patch("release_template.core.save", side_effect=interrupted):
          with self.assertRaises(SystemExit):
            self.retire(old)
        self.assert_preserved(old, before, abandoned=boundary == "after")
        self.retire(old)
        self.assert_preserved(old, before, abandoned=True)
        self.assertEqual(self.transport.requests.count(("DELETE", self.package_path(old))), 1)

  def test_later_alias_failure_keeps_run_pending_and_retry_skips_prior_alias(self):
    old = self.old_run(names=("application", "sidecar"))
    before = load(old.state.path)
    path = self.package_path(old, "sidecar")
    delete = self.backend.delete_package
    def delete_then_null(name, reference):
      delete(name, reference)
      if name == "sidecar":
        self.transport.overrides["GET", path] = (200, None)
    with patch.object(self.backend, "delete_package", side_effect=delete_then_null):
      with self.assertRaises(ReleaseError):
        self.retire(old)
    self.assert_preserved(old, before)
    self.assertEqual(len(self.backend.deleted), 2)
    self.transport.overrides.clear()
    self.retire(old)
    self.assert_preserved(old, before, abandoned=True)
    self.assertEqual(len(self.backend.deleted), 2)

  def test_first_uncertain_alias_stops_before_later_alias(self):
    old = self.old_run(names=("application", "sidecar"))
    before = load(old.state.path)
    path = self.package_path(old)
    delete = self.backend.delete_package
    def delete_then_null(name, reference):
      delete(name, reference)
      self.transport.overrides["GET", path] = (200, None)
    with patch.object(self.backend, "delete_package", side_effect=delete_then_null):
      with self.assertRaises(ReleaseError):
        self.retire(old)
    self.assert_preserved(old, before)
    self.assertEqual(len(self.backend.deleted), 1)
    self.assertNotIn(("DELETE", self.package_path(old, "sidecar")), self.transport.requests)
    self.transport.overrides.clear()
    self.retire(old)
    self.assert_preserved(old, before, abandoned=True)
    self.assertEqual(len(self.backend.deleted), 2)

  def test_multiple_runs_keep_confirmed_progress_when_later_run_fails(self):
    old_runs = (self.old_run("0.8.0"), self.old_run("0.9.0"))
    # The directory scan, not requested-ID order, determines per-run processing order.
    by_path = {old.state.path: old for old in old_runs}
    first, second = [by_path[path] for path in self.current.state.path.parent.glob("*.json") if path in by_path]
    before_first, before_second = load(first.state.path), load(second.state.path)
    path = self.package_path(second)
    delete = self.backend.delete_package
    def delete_then_null(name, reference):
      delete(name, reference)
      if reference == before_second["staging"][name]["tag"]:
        self.transport.overrides["GET", path] = (200, None)
    with patch.object(self.backend, "delete_package", side_effect=delete_then_null):
      with self.assertRaises(ReleaseError):
        self.retire(*old_runs)
    self.assert_preserved(first, before_first, abandoned=True)
    self.assert_preserved(second, before_second)
    self.transport.overrides.clear()
    self.retire(*old_runs)
    self.assert_preserved(second, before_second, abandoned=True)
    self.assertEqual(len(self.backend.deleted), 2)

  def test_preexisting_abandoned_flag_does_not_skip_remote_validation(self):
    old = self.old_run()
    old.state.data["abandoned"] = True
    old.state.flush()
    before = load(old.state.path)
    with patch.object(self.backend, "delete_package", return_value=None):
      with self.assertRaisesRegex(ReleaseError, "not yet absent"):
        self.retire(old)
    self.assert_preserved(old, before)
    self.assertEqual(self.transport.requests.count(("DELETE", self.package_path(old))), 1)
