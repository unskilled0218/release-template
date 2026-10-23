"""Scoped association evidence, explicit concurrency prerequisites, and lost-response recovery."""

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from release_template.adapters import Gitea
from release_template.core import ReleaseError, canonical, digest, load
from release_template.linking import association, link_packages, verify_links, window
from release_template.workflow import Workflow
from tests.support import COMMIT, REVISION, FakeGitea, FakeRegistry, FakeRunner, configuration, package


class LinkingAPI(FakeGitea):
  def __init__(self, registry):
    super().__init__(registry)
    self.links, self.lose, self.noop = [], False, False

  def link_package(self, name):
    self.links.append(name)
    if not self.noop:
      for item in self.package_records:
        if item["name"] == name:
          item["repository"] = {"full_name": "fixtures/application"}
    if self.lose:
      self.lose = False
      raise SystemExit("Lost accepted link response")


class PackageLinkTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.config = configuration() | {"link_packages": True}
    self.registry = FakeRegistry()
    self.runner = FakeRunner(self.registry)
    self.api = LinkingAPI(self.registry)
    self.path = self.root / "window.json"
    now = datetime.now(timezone.utc)
    self.authority = {"schema": 1, "origin": self.config["gitea"], "server_version": "28.2.0", "owner": "fixtures",
      "packages": ["application"], "repository": "fixtures/application", "operator": "fixture operator",
      "starts_at": (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
      "expires_at": (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
      "exclusion_procedure": "Synthetic exclusion of all UI/API/CI and other-checkout writers",
      "exclusion_confirmed": True}
    self.path.write_text(json.dumps(self.authority))
    self.api.package_records = [package("application", "prepared") | {"repository": None}]
    self.workflow = self.reopen()
    self.workflow.state.data["outputs"] = {"application": {"digest": "sha256:" + "c" * 64}}
    self.workflow.state.data["staging"] = {"application": {"tag": "prepared", "digest": "sha256:" + "c" * 64}}
    self.workflow.state.flush()

  def reopen(self):
    return Workflow(self.root, self.config, "1.0.0", REVISION, self.runner, self.registry, self.api, COMMIT, self.path)

  def test_unlinked_package_is_confirmed_and_already_linked_retry_has_no_post(self):
    identity = copy.deepcopy(self.workflow.state.data["identity"])
    link_packages(self.workflow, self.path)
    self.assertEqual(self.api.links, ["application"])
    self.assertEqual(association(self.workflow, "application"), self.config["repository"])
    self.path.unlink()
    link_packages(self.reopen())
    self.assertEqual(self.api.links, ["application"])
    self.assertEqual(self.reopen().state.data["identity"], identity)
    self.assertEqual(self.api.deleted, [])

  def test_default_off_never_reads_window_or_mutates(self):
    self.workflow.config["link_packages"] = False
    link_packages(self.workflow)
    verify_links(self.workflow)
    self.assertEqual(self.api.links, [])
    self.assertNotIn("link:application", self.workflow.state.data["operations"])

  def test_foreign_missing_malformed_and_disagreeing_associations_fail(self):
    original = copy.deepcopy(self.api.package_records)
    records = [[], [package("application", "prepared", "foreign/project")],
               [dict(type="container", name="application", version="prepared")],
               [original[0] | {"owner": {"login": "foreign"}}],
               [original[0] | {"repository": {}}], [original[0] | {"type": "generic"}],
               [original[0], package("application", "other")]]
    for values in records:
      with self.subTest(values=values):
        self.api.package_records = values
        with self.assertRaises(ReleaseError):
          link_packages(self.workflow, self.path)
        self.assertEqual(self.api.links, [])

  def test_window_scope_time_schema_and_confirmation_are_checked(self):
    changes = [{"schema": 2}, {"origin": "https://other.invalid"}, {"owner": "other"},
               {"repository": "fixtures/other"}, {"packages": ["other"]}, {"server_version": "28.2.1"},
               {"exclusion_confirmed": False}, {"exclusion_procedure": ""}, {"operator": ""},
               {"expires_at": "2020-01-01T00:00:00Z"}, {"starts_at": "2099-01-01T00:00:00Z"},
               {"expires_at": "2026-10-23"}, {"unknown": True}]
    for change in changes:
      self.path.write_text(json.dumps(self.authority | change))
      with self.subTest(change=change), self.assertRaises(ReleaseError):
        link_packages(self.workflow, self.path)
      self.assertEqual(self.api.links, [])
    with self.assertRaisesRegex(ReleaseError, "requires"):
      link_packages(self.workflow)

  def test_window_expiry_immediately_before_post_stops_mutation(self):
    expires = datetime.fromisoformat(self.authority["expires_at"]).timestamp()
    clock = [expires - 1]
    original = self.api.get
    def get(path, absent=False):
      result = original(path, absent=absent)
      if path == "/api/v1/version":
        clock[0] = expires
      return result
    with patch("release_template.linking.time.time", side_effect=lambda: clock[0]), patch.object(self.api, "get", side_effect=get):
      with self.assertRaises(ReleaseError):
        link_packages(self.workflow, self.path)
    self.assertEqual(self.api.links, [])
    self.assertEqual(load(self.workflow.state.path)["operations"]["link:application"]["status"], "pending")

  def test_expiry_during_final_association_lookup_stops_post(self):
    expires = datetime.fromisoformat(self.authority["expires_at"]).timestamp()
    clock = [expires - 1]
    original = self.api.get
    version_seen = [False]
    def get(path, absent=False):
      result = original(path, absent=absent)
      if path == "/api/v1/version":
        version_seen[0] = True
      elif version_seen[0]:
        clock[0] = expires
      return result
    with patch("release_template.linking.time.time", side_effect=lambda: clock[0]), patch.object(self.api, "get", side_effect=get):
      with self.assertRaises(ReleaseError):
        link_packages(self.workflow, self.path)
    self.assertEqual(self.api.links, [])

  def test_window_validation_rechecks_time_after_version_lookup(self):
    expires = datetime.fromisoformat(self.authority["expires_at"]).timestamp()
    clock = [expires - 1]
    original = self.api.get
    def get(path, absent=False):
      result = original(path, absent=absent)
      if path == "/api/v1/version":
        clock[0] = expires
      return result
    with patch("release_template.linking.time.time", side_effect=lambda: clock[0]), patch.object(self.api, "get", side_effect=get):
      with self.assertRaises(ReleaseError):
        window(self.workflow, "application", self.path)

  def test_expiry_during_authority_flush_stops_post(self):
    expires = datetime.fromisoformat(self.authority["expires_at"]).timestamp()
    clock = [expires - 1]
    original = self.workflow.state.flush
    def flush():
      original()
      if self.workflow.state.data.get("link_windows"):
        clock[0] = expires
    with patch("release_template.linking.time.time", side_effect=lambda: clock[0]), patch.object(self.workflow.state, "flush", side_effect=flush):
      with self.assertRaises(ReleaseError):
        link_packages(self.workflow, self.path)
    self.assertEqual(self.api.links, [])
    self.assertEqual(load(self.workflow.state.path)["operations"]["link:application"]["status"], "pending")

  def test_authority_snapshot_is_used_even_if_file_is_replaced_during_validation(self):
    original = self.api.get
    first = copy.deepcopy(self.authority)
    def get(path, absent=False):
      if path == "/api/v1/version":
        self.path.write_text(json.dumps(first | {"operator": "replacement operator", "repository": "fixtures/other"}))
      return original(path, absent=absent)
    with patch.object(self.api, "get", side_effect=get):
      link_packages(self.workflow, self.path)
    self.assertEqual(self.api.links, ["application"])
    evidence = load(self.workflow.state.path)["link_windows"]["application"]
    self.assertEqual(evidence, [{"digest": digest(canonical(first)), "scope": first}])

  def test_replacement_file_cannot_renew_expired_captured_authority(self):
    expires = datetime.fromisoformat(self.authority["expires_at"]).timestamp()
    clock = [expires - 1]
    original = self.workflow.state.flush
    def flush():
      original()
      if self.workflow.state.data.get("link_windows"):
        renewed = self.authority | {"expires_at": datetime.fromtimestamp(expires + 600, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        self.path.write_text(json.dumps(renewed))
        clock[0] = expires
    with patch("release_template.linking.time.time", side_effect=lambda: clock[0]), patch.object(self.workflow.state, "flush", side_effect=flush):
      with self.assertRaises(ReleaseError):
        link_packages(self.workflow, self.path)
    self.assertEqual(self.api.links, [])
    before = load(self.workflow.state.path)["operations"]["link:application"]["details"]
    with patch("release_template.linking.time.time", side_effect=lambda: clock[0]):
      link_packages(self.reopen(), self.path)
    self.assertEqual(self.api.links, ["application"])
    self.assertEqual(load(self.workflow.state.path)["operations"]["link:application"]["details"], before)

  def test_authority_start_is_inclusive_and_expiry_exclusive(self):
    starts = datetime.fromisoformat(self.authority["starts_at"]).timestamp()
    expires = datetime.fromisoformat(self.authority["expires_at"]).timestamp()
    self.assertEqual(window(self.workflow, "application", self.path, now=starts)["scope"], self.authority)
    self.assertEqual(window(self.workflow, "application", self.path, now=expires - 0.001)["scope"], self.authority)
    for now in (starts - 0.001, expires, expires + 1):
      with self.subTest(now=now), self.assertRaises(ReleaseError):
        window(self.workflow, "application", self.path, now=now)

  def test_valid_dispatch_can_be_confirmed_after_expiry_without_rollback(self):
    expires = datetime.fromisoformat(self.authority["expires_at"]).timestamp()
    clock = [expires - 1]
    original = self.api.link_package
    def link(name):
      original(name)
      clock[0] = expires + 1
    with patch("release_template.linking.time.time", side_effect=lambda: clock[0]), patch.object(self.api, "link_package", side_effect=link):
      link_packages(self.workflow, self.path)
    self.assertEqual(self.api.links, ["application"])
    self.assertEqual(self.api.deleted, [])
    self.assertEqual(load(self.workflow.state.path)["operations"]["link:application"]["status"], "complete")

  def test_lost_response_after_valid_dispatch_and_expiry_reconciles_without_authority(self):
    expires = datetime.fromisoformat(self.authority["expires_at"]).timestamp()
    clock = [expires - 1]
    original = self.api.link_package
    def link(name):
      original(name)
      clock[0] = expires + 1
      raise SystemExit("Lost response after valid dispatch")
    with patch("release_template.linking.time.time", side_effect=lambda: clock[0]), patch.object(self.api, "link_package", side_effect=link):
      with self.assertRaises(SystemExit):
        link_packages(self.workflow, self.path)
    self.path.unlink()
    with patch("release_template.linking.time.time", side_effect=lambda: clock[0]):
      link_packages(self.reopen())
    self.assertEqual(self.api.links, ["application"])
    self.assertEqual(load(self.workflow.state.path)["operations"]["link:application"]["status"], "complete")

  def test_expired_dispatch_stops_later_publication_writes_and_retry_reuses_build(self):
    self.workflow.state.data["outputs"] = {}
    self.workflow.state.data["staging"] = {}
    self.workflow.state.flush()
    self.api.package_records = []
    original_add = self.registry.add
    def add(name, tag, *args, **kwargs):
      root = original_add(name, tag, *args, **kwargs)
      self.api.package_records.append(package(name, tag) | {"repository": None})
      return root
    self.registry.add = add
    expires = datetime.fromisoformat(self.authority["expires_at"]).timestamp()
    clock = [expires - 1]
    original_flush = self.workflow.state.flush
    def flush():
      original_flush()
      if self.workflow.state.data.get("link_windows"):
        clock[0] = expires
    with patch("release_template.linking.time.time", side_effect=lambda: clock[0]), patch.object(self.workflow.state, "flush", side_effect=flush):
      with self.assertRaises(ReleaseError):
        self.workflow.publish()
    self.assertEqual(self.api.links, [])
    self.assertEqual(self.runner.tags, {})
    self.assertIsNone(self.registry.resolve("application", "latest"))
    self.assertEqual(self.api.records, [])
    pending = load(self.workflow.state.path)
    self.assertEqual(pending["operations"]["link:application"]["status"], "pending")
    renewed = self.authority | {"expires_at": datetime.fromtimestamp(expires + 600, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    self.path.write_text(json.dumps(renewed))
    with patch("release_template.linking.time.time", side_effect=lambda: clock[0]):
      self.reopen().publish()
    self.assertEqual(sum(call[:3] == ["docker", "buildx", "build"] for call in self.runner.calls), 1)
    self.assertEqual(self.api.links, ["application"])
    self.assertEqual(len(self.api.records), 1)
    self.assertEqual(load(self.workflow.state.path)["identity"], pending["identity"])

  def test_final_lookup_detects_foreign_change_without_post(self):
    original = association
    calls = []
    def changed(workflow, name, required_version=None):
      calls.append(name)
      if len(calls) == 2:
        self.api.package_records[0]["repository"] = {"full_name": "foreign/project"}
      return original(workflow, name, required_version)
    with patch("release_template.linking.association", side_effect=changed), self.assertRaises(ReleaseError):
      link_packages(self.workflow, self.path)
    self.assertEqual(self.api.links, [])

  def test_lost_accepted_response_reconciles_after_reopen_without_post(self):
    self.api.lose = True
    with self.assertRaises(SystemExit):
      link_packages(self.workflow, self.path)
    self.assertEqual(self.reopen().state.data["operations"]["link:application"]["status"], "pending")
    self.path.unlink()
    reopened = self.reopen()
    link_packages(reopened)
    self.assertEqual(self.api.links, ["application"])
    self.assertEqual(reopened.state.data["operations"]["link:application"]["status"], "complete")

  def test_noop_response_is_not_confirmation_and_window_renewal_preserves_intent(self):
    self.api.noop = True
    with self.assertRaisesRegex(ReleaseError, "not confirmed"):
      link_packages(self.workflow, self.path)
    saved = load(self.workflow.state.path)["operations"]["link:application"]["details"]
    self.authority["operator"] = "renewed fixture coordinator"
    self.path.write_text(json.dumps(self.authority))
    self.api.noop = False
    link_packages(self.reopen(), self.path)
    self.assertEqual(load(self.workflow.state.path)["operations"]["link:application"]["details"], saved)
    self.assertEqual(len(load(self.workflow.state.path)["link_windows"]["application"]), 2)

  def test_final_verification_refuses_missing_or_changed_link(self):
    link_packages(self.workflow, self.path)
    verify_links(self.workflow)
    self.api.package_records[0]["repository"] = None
    with self.assertRaises(ReleaseError):
      verify_links(self.workflow)
    self.assertEqual(self.api.links, ["application"])

  def test_missing_prepared_version_cannot_link_an_older_package_instead(self):
    self.api.package_records[0]["version"] = "older-version"
    with self.assertRaisesRegex(ReleaseError, "Prepared package version missing"):
      link_packages(self.workflow, self.path)
    self.assertEqual(self.api.links, [])

  def test_completion_flush_crash_recovers_matching_link_without_second_post(self):
    with patch.object(self.workflow.state, "complete", side_effect=SystemExit("before completion save")):
      with self.assertRaises(SystemExit):
        link_packages(self.workflow, self.path)
    link_packages(self.reopen())
    self.assertEqual(self.api.links, ["application"])
    self.assertEqual(load(self.workflow.state.path)["operations"]["link:application"]["status"], "complete")

  def test_link_failure_stops_tag_promotion_release_and_reuses_staging(self):
    # Exercise the full ordering rather than only the helper.
    self.workflow.state.data["outputs"] = {}
    self.workflow.state.flush()
    original_add = self.registry.add
    def add(name, tag, *args, **kwargs):
      root = original_add(name, tag, *args, **kwargs)
      self.api.package_records.append(package(name, tag) | {"repository": None})
      return root
    self.registry.add = add
    self.path.unlink()
    with self.assertRaises(ReleaseError):
      self.workflow.publish()
    self.assertEqual(self.runner.tags, {})
    self.assertIsNone(self.registry.resolve("application", "latest"))
    self.assertEqual(self.api.records, [])
    self.path.write_text(json.dumps(self.authority))
    self.reopen().publish()
    self.assertEqual(len([c for c in self.runner.calls if c[:3] == ["docker", "buildx", "build"]]), 1)
    self.assertEqual(len(self.api.records), 1)
    self.assertEqual(self.api.links, ["application"])

  def test_multiple_images_are_individually_linked(self):
    self.workflow.config["images"].append({"name": "other", "platforms": ["linux/amd64"]})
    self.workflow.state.data["outputs"]["other"] = {"digest": "sha256:" + "d" * 64}
    self.workflow.state.data["staging"]["other"] = {"tag": "prepared", "digest": "sha256:" + "d" * 64}
    self.api.package_records.append(package("other", "prepared") | {"repository": None})
    self.authority["packages"].append("other")
    self.path.write_text(json.dumps(self.authority))
    link_packages(self.workflow, self.path)
    self.assertEqual(self.api.links, ["application", "other"])

  def test_adapter_uses_encoded_route_and_201_only(self):
    api = Gitea(configuration() | {"repository": "fixtures/application"}, "fixture-token")
    transport = unittest.mock.Mock()
    api.http = transport
    api.link_package("nested/name")
    args, kwargs = transport.request.call_args
    self.assertEqual(args[0:2], ("POST", "/api/v1/packages/fixtures/container/nested%2Fname/-/link/application"))
    self.assertEqual(kwargs["allowed"], (201,))
    self.assertEqual(len(transport.request.call_args_list), 1)
