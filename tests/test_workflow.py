import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from release_template.cleanup import abandon, apply, plan, protected_graph
from release_template.core import ReleaseError, load
from release_template.policy import description, metadata
from release_template.workflow import Workflow
from tests.support import COMMIT, REVISION, FakeForgejo, FakeRegistry, FakeRunner, configuration, evidence, package


class WorkflowTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.config = configuration()
    self.registry = FakeRegistry()
    self.forgejo = FakeForgejo(self.registry)
    self.runner = FakeRunner(self.registry)

  def workflow(self, release_version="1.0.0"):
    self.runner.release_version = release_version
    return Workflow(self.root, self.config, release_version, REVISION, self.runner, self.registry, self.forgejo, COMMIT)

  def builds(self):
    return [call for call in self.runner.calls if call[:3] == ["docker", "buildx", "build"]]

  def test_publish_is_text_only_latest_only_and_resume_does_not_rebuild(self):
    workflow = self.workflow()
    workflow.publish()
    identity = metadata(self.forgejo.release("v1.0.0"))
    self.assertEqual(identity["targets"], workflow.targets())
    self.assertEqual(set(workflow.targets()), {"application:latest"})
    self.assertEqual(self.forgejo.records[0]["assets"], [])
    self.assertEqual(len(self.builds()), 1)
    self.workflow().publish()
    self.assertEqual(len(self.builds()), 1)
    self.assertEqual(self.forgejo.deleted, [])

  def test_lost_build_promotion_tag_and_release_responses_reconcile(self):
    for fault in ("kill_build", "kill_tag", "kill_promote", "fail_publish"):
      with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
        self.root = Path(temporary)
        self.registry = FakeRegistry()
        self.forgejo = FakeForgejo(self.registry)
        self.runner = FakeRunner(self.registry)
        owner = self.forgejo if fault == "fail_publish" else self.runner
        setattr(owner, fault, True)
        with self.assertRaises(SystemExit):
          self.workflow().publish()
        self.assertEqual(self.forgejo.deleted, [], "Publication failure must never delete history")
        self.workflow().publish()
        self.assertEqual(len(self.builds()), 1, "Resume must reconcile existing staged output without rebuilding")
        self.assertEqual(len(self.forgejo.records), 1)

  def test_uncertain_build_without_digest_requires_explicit_recovery(self):
    workflow = self.workflow()
    workflow.snapshot()
    image = self.config["images"][0]
    name = image["name"]
    workflow.state.intent("build:" + name, {"tag": "rt-" + workflow.state.data["run"] + "-" + name,
      "image": "forgejo.invalid/fixtures/application", "commit": COMMIT, "platforms": image["platforms"]})
    with self.assertRaisesRegex(ReleaseError, "explicit recovery"):
      workflow.prepare_image(image)
    self.assertFalse(self.builds())

  def test_lost_source_push_response_is_reconciled_without_second_push(self):
    self.config["source_push"] = True
    self.runner.remote_commit = "c" * 40
    self.runner.kill_source = True
    with self.assertRaises(SystemExit):
      self.workflow().publish()
    self.assertFalse(self.builds())
    self.workflow().publish()
    pushes = [call for call in self.runner.calls if call[:2] == ["git", "push"] and call[-1] == "HEAD:refs/heads/main"]
    self.assertEqual(len(pushes), 1)
    self.assertEqual(len(self.builds()), 1)

  def test_failed_image_verification_preserves_prepared_remote_output_for_retry(self):
    with patch.object(self.registry, "verify", side_effect=ReleaseError("Injected image verification failure")):
      with self.assertRaisesRegex(ReleaseError, "verification"):
        self.workflow().publish()
    self.assertEqual(self.forgejo.deleted, [])
    self.assertIsNone(self.registry.resolve("application", "latest"))
    self.workflow().publish()
    self.assertEqual(len(self.builds()), 1)

  def test_conflicting_local_tag_stops_before_builds(self):
    original = self.runner.run
    def run(arguments, **kwargs):
      if arguments[:3] == ["git", "tag", "--list"]:
        return "v1.0.0"
      if arguments[:3] == ["git", "rev-parse", "--verify"]:
        return "c" * 40
      return original(arguments, **kwargs)
    self.runner.run = run
    with self.assertRaisesRegex(ReleaseError, "Local version tag"):
      self.workflow().publish()
    self.assertFalse(self.builds())
    self.assertFalse(self.forgejo.records)

  def test_old_checkpoint_after_new_publication_never_writes_alias_or_release(self):
    old = self.workflow()
    self.runner.kill_promote = True
    with self.assertRaises(SystemExit):
      old.publish()
    # Simulate a later authorized publisher that completed a newer release.
    newer_root = self.registry.add("application", "latest", "2.0.0")
    new_identity = old.release_identity() | {"version": "2.0.0", "tag": "v2.0.0", "targets": {"application:latest": newer_root}}
    self.forgejo.publish("v2.0.0", COMMIT, description(new_identity))
    start = len(self.runner.calls)
    with self.assertRaises(ReleaseError):
      self.workflow().publish()
    self.assertFalse(any(call[:4] == ["docker", "buildx", "imagetools", "create"] for call in self.runner.calls[start:]))
    self.assertEqual(len(self.forgejo.records), 1)
    self.assertEqual(self.forgejo.deleted, [])

  def test_first_publication_refuses_unowned_existing_latest(self):
    self.registry.add("application", "latest", "0.5.0")
    with self.assertRaisesRegex(ReleaseError, "predecessor"):
      self.workflow().publish()
    self.assertFalse(self.builds())

  def test_equal_version_conflict_and_unknown_publication_fail_closed(self):
    workflow = self.workflow()
    workflow.publish()
    self.forgejo.records[0]["body"] = description(workflow.release_identity() | {"commit": "c" * 40})
    with self.assertRaisesRegex(ReleaseError, "conflicting"):
      self.workflow().publish()
    self.forgejo.records[0]["tag_name"] = "unknown"
    with self.assertRaisesRegex(ReleaseError, "Unrecognized"):
      self.workflow().publish()

  def test_source_drift_prevents_build(self):
    self.runner.drift = True
    with self.assertRaisesRegex(ReleaseError, "clean"):
      self.workflow().publish()
    self.assertFalse(self.builds())

  def test_dependency_hook_receives_parent_digest_and_suite_promotes_after_all_builds(self):
    self.config["images"].append({"name": "child", "dependencies": ["application"],
      "platforms": ["linux/amd64"], "build": ["fixture-build"]})
    workflow = self.workflow()
    workflow.publish()
    self.assertEqual(self.runner.last_build_inputs["dependencies"], {"application":
      "forgejo.invalid/fixtures/application@" + workflow.state.data["outputs"]["application"]["digest"]})
    calls = self.runner.calls
    first_promotion = next(index for index, call in enumerate(calls) if call[:4] == ["docker", "buildx", "imagetools", "create"])
    self.assertLess(calls.index(["fixture-build"]), first_promotion)
    self.assertEqual(set(workflow.targets()), {"application:latest", "child:latest"})

  def test_partial_suite_promotion_resumes_only_its_recorded_transition(self):
    self.config["images"].append({"name": "child", "dependencies": ["application"],
      "platforms": ["linux/amd64"], "build": ["fixture-build"]})
    self.runner.kill_promote = True
    with self.assertRaises(SystemExit):
      self.workflow().publish()
    self.assertIsNotNone(self.registry.resolve("application", "latest"))
    self.assertIsNone(self.registry.resolve("child", "latest"))
    self.workflow().publish()
    self.assertEqual(len(self.forgejo.records), 1)
    self.assertEqual(len(self.builds()), 1)
    self.assertIsNotNone(self.registry.resolve("child", "latest"))

  def test_repeated_successful_releases_retire_own_staging_and_delete_only_old_complete_digests(self):
    evidence_path = evidence(self.root / "evidence.json")
    old = self.workflow()
    old.publish()
    self.add_staging_packages(old)
    apply(old, evidence_path)
    new = self.workflow("2.0.0")
    new.publish()
    self.add_staging_packages(new)
    old_digest = old.state.data["outputs"]["application"]["digest"]
    self.forgejo.package_records.append(package("application", old_digest))
    apply(new, evidence_path)
    self.assertEqual({item["tag_name"] for item in self.forgejo.records}, {"v2.0.0"})
    self.assertTrue(all(not tag.startswith("rt-") for _, tag in self.registry.aliases))
    self.assertIn(("package", "application", old_digest), self.forgejo.deleted)

  def test_missing_deletion_evidence_blocks_all_deletions_but_keeps_publication(self):
    workflow = self.workflow()
    workflow.publish()
    with self.assertRaisesRegex(ReleaseError, "disabled"):
      apply(workflow, None)
    self.assertTrue(load(workflow.state.path)["published"])
    self.assertEqual(self.forgejo.deleted, [])

  def add_staging_packages(self, workflow):
    for name, staging in workflow.state.data["staging"].items():
      self.forgejo.package_records.append(package(name, staging["tag"]))

  def test_successful_staging_retirement_preserves_current_manifest_and_is_idempotent(self):
    workflow = self.workflow()
    workflow.publish()
    self.add_staging_packages(workflow)
    staging = workflow.state.data["staging"]["application"]["tag"]
    current = self.registry.resolve("application", "latest")
    apply(workflow, evidence(self.root / "evidence.json"))
    self.assertIsNone(self.registry.resolve("application", staging))
    self.assertEqual(self.registry.resolve("application", "latest"), current)
    self.assertTrue(workflow.state.data["cleanup_complete"])
    self.workflow().publish()
    self.assertEqual(len(self.builds()), 1)
    apply(workflow, self.root / "evidence.json")
    self.assertEqual(len(self.forgejo.deleted), 1)

  def test_cleanup_preserves_unknown_cross_repository_draft_and_current_digest(self):
    first = self.workflow()
    first.publish()
    second = self.workflow("2.0.0")
    second.publish()
    old_digest = first.state.data["outputs"]["application"]["digest"]
    self.registry.aliases["application", "v1.0.0"] = old_digest
    current = second.state.data["outputs"]["application"]["digest"]
    self.registry.aliases["application", "custom"] = current
    self.registry.aliases["application", "v0.2.0"] = current
    self.forgejo.package_records = [package("application", "v1.0.0"), package("application", "latest"),
      package("application", current), package("application", "custom"),
      package("other", "v0.1.0"), package("application", "v0.2.0", "other/repo")]
    self.forgejo.records.append({"id": 99, "tag_name": "v0.1.0", "draft": True, "assets": []})
    inventory = plan(second)
    self.assertEqual({candidate.get("version") for candidate in inventory["candidates"] if candidate["kind"] == "package"}, {"v1.0.0"})
    self.assertNotIn(99, {candidate.get("id") for candidate in inventory["candidates"]})
    self.assertEqual(len(inventory["skipped"]), 1)

  def test_unfinished_checkpoint_graph_remains_protected(self):
    interrupted = self.workflow()
    interrupted.snapshot()
    interrupted.prepare_image(self.config["images"][0])
    second = self.workflow("2.0.0")
    second.publish()
    old_digest = interrupted.state.data["outputs"]["application"]["digest"]
    self.assertIn(old_digest, protected_graph(second)["application"])
    self.forgejo.package_records = [package("application", old_digest)]
    self.assertFalse(plan(second)["candidates"])

  def test_lost_build_response_protects_uncheckpointed_staging_graph(self):
    self.runner.kill_build = True
    first = self.workflow()
    with self.assertRaises(SystemExit):
      first.publish()
    self.assertFalse(first.state.data["outputs"])
    old_tag = first.state.data["staging"]["application"]["tag"]
    old_digest = self.registry.resolve("application", old_tag)
    second = self.workflow("2.0.0")
    second.publish()
    self.assertIn(old_digest, protected_graph(second)["application"])
    self.forgejo.package_records = [package("application", old_digest)]
    self.assertFalse(plan(second)["candidates"])

  def test_failed_cleanup_can_retry_without_rebuilding(self):
    workflow = self.workflow()
    workflow.publish()
    self.add_staging_packages(workflow)
    self.forgejo.fail_delete = True
    evidence_path = evidence(self.root / "evidence.json")
    with self.assertRaisesRegex(ReleaseError, "deletion"):
      apply(workflow, evidence_path)
    self.assertTrue(workflow.state.data["published"])
    apply(self.workflow(), evidence_path)
    self.assertEqual(len(self.builds()), 1)
    self.assertEqual(len(self.forgejo.deleted), 1)

  def test_changed_latest_or_staging_identity_aborts_cleanup(self):
    workflow = self.workflow()
    workflow.publish()
    self.add_staging_packages(workflow)
    self.registry.add("application", "latest", "9.0.0")
    with self.assertRaises(ReleaseError):
      apply(workflow, evidence(self.root / "evidence.json"))
    self.assertEqual(self.forgejo.deleted, [])

  def test_abandoned_cleanup_requires_selected_inventory_and_age(self):
    interrupted = self.workflow()
    interrupted.snapshot()
    interrupted.prepare_image(self.config["images"][0])
    self.add_staging_packages(interrupted)
    second = self.workflow("2.0.0")
    second.publish()
    evidence_path = evidence(self.root / "evidence.json")
    with self.assertRaisesRegex(ReleaseError, "threshold"):
      abandon(second, [interrupted.state.data["run"]], 86400, evidence_path)
    interrupted.state.data["created"] -= 86401
    interrupted.state.flush()
    abandon(second, [interrupted.state.data["run"]], 86400, evidence_path)
    self.assertTrue(load(interrupted.state.path)["abandoned"])
    self.assertEqual(len(self.forgejo.deleted), 1)

  def test_preserved_alias_protects_completed_older_graph_in_either_inventory_order(self):
    old = self.workflow()
    old.publish()
    apply(old, evidence(self.root / "evidence.json"))
    current = self.workflow("2.0.0")
    current.publish()
    digest = old.state.data["outputs"]["application"]["digest"]
    for alias in ("custom", "v1.0.0-rc.1", "v9.0.0", "rt-external-application"):
      self.registry.aliases["application", alias] = digest
      for reverse in (False, True):
        with self.subTest(alias=alias, reverse=reverse):
          records = [package("application", alias), package("application", digest)]
          self.forgejo.package_records = list(reversed(records)) if reverse else records
          self.assertFalse(any(item.get("version") == digest for item in plan(current)["candidates"]))
      self.registry.aliases.pop(("application", alias))

  def test_saved_digest_candidate_cannot_ignore_new_unscheduled_older_alias(self):
    old = self.workflow()
    old.publish()
    apply(old, evidence(self.root / "evidence.json"))
    current = self.workflow("2.0.0")
    current.publish()
    digest = old.state.data["outputs"]["application"]["digest"]
    self.forgejo.package_records = [package("application", digest)]
    current.state.data["cleanup"] = plan(current)
    current.state.flush()
    self.registry.aliases["application", "v0.9.0"] = digest
    self.forgejo.package_records.append(package("application", "v0.9.0"))
    self.forgejo.deleted.clear()
    with self.assertRaises(ReleaseError):
      apply(current, self.root / "evidence.json")
    self.assertNotIn(("package", "application", digest), self.forgejo.deleted)

  def completed_history(self):
    old = self.workflow()
    old.publish()
    evidence_path = evidence(self.root / "evidence.json")
    apply(old, evidence_path)
    current = self.workflow("2.0.0")
    current.publish()
    return current, old.state.data["outputs"]["application"]["digest"], evidence_path

  def test_preserved_nested_graph_survives_apply_while_unreferenced_digest_is_deleted(self):
    current, old_digest, evidence_path = self.completed_history()
    old_image = self.registry.images["application", old_digest]
    child = next(item for item in old_image["graph"] if item != old_digest)
    self.registry.aliases["application", "custom"] = old_digest
    orphan = self.registry.add("application", "unlisted", "0.5.0")
    self.registry.aliases.pop(("application", "unlisted"))
    self.forgejo.package_records = [package("application", child), package("application", old_digest),
      package("application", "custom"), package("application", orphan)]
    with self.assertRaisesRegex(ReleaseError, "ambiguous"):
      apply(current, evidence_path)
    self.assertIn(("package", "application", orphan), self.forgejo.deleted)
    self.assertNotIn(("package", "application", old_digest), self.forgejo.deleted)
    self.assertNotIn(("package", "application", child), self.forgejo.deleted)
    self.assertTrue(self.registry.graph("application", old_digest)[0] >= {old_digest, child})
    self.assertEqual(self.registry.resolve("application", "custom"), old_digest)

  def test_same_name_foreign_or_missing_association_protects_shared_content(self):
    current, old_digest, _ = self.completed_history()
    self.registry.aliases["application", "v0.9.0"] = old_digest
    for association in ({"full_name": "other/repo"}, None, {}):
      with self.subTest(association=association):
        reference = package("application", "v0.9.0") | {"repository": association}
        self.forgejo.package_records = [package("application", old_digest), reference]
        self.assertFalse(any(item.get("kind") == "package" for item in plan(current)["candidates"]))

  def test_ambiguous_digest_root_protects_separately_listed_children(self):
    current, old_digest, _ = self.completed_history()
    image = self.registry.images["application", old_digest]
    child = next(item for item in image["graph"] if item != old_digest)
    _, evidence_record = self.registry.graph("application", old_digest)
    evidence_record = copy.deepcopy(evidence_record)
    configuration = next(node["configuration"] for node in evidence_record["nodes"].values() if node["configuration"])
    configuration["config"]["Labels"]["org.opencontainers.image.source"] = "https://foreign.invalid/source"
    # Only the index is uncertain; the separately listed child still has owned labels.
    self.registry.images["application", old_digest] = image | {"evidence": evidence_record}
    self.forgejo.package_records = [package("application", child), package("application", old_digest)]
    self.assertFalse(any(item.get("kind") == "package" for item in plan(current)["candidates"]))

  def test_unavailable_preserved_evidence_blocks_all_deletions(self):
    current, old_digest, evidence_path = self.completed_history()
    self.forgejo.package_records = [package("application", old_digest), package("application", "custom")]
    for mode in ("unresolved", "graph failure"):
      with self.subTest(mode=mode):
        if mode == "graph failure":
          self.registry.aliases["application", "custom"] = old_digest
        self.forgejo.deleted.clear()
        failure = ReleaseError("Graph unavailable") if mode == "graph failure" else None
        with patch.object(self.registry, "graph", wraps=self.registry.graph, side_effect=failure):
          with self.assertRaises(ReleaseError):
            apply(current, evidence_path)
        self.assertEqual(self.forgejo.deleted, [])

  def test_old_shaped_inventory_and_recreated_completed_alias_are_rechecked(self):
    current, old_digest, evidence_path = self.completed_history()
    self.registry.aliases["application", "v0.9.0"] = old_digest
    self.forgejo.package_records = [package("application", old_digest), package("application", "v0.9.0")]
    raw = {"kind": "package", "name": "application", "version": old_digest, "digest": old_digest}
    alias = {"kind": "package", "name": "application", "version": "v0.9.0", "digest": old_digest, "complete": True}
    for candidates in ([raw], [alias, raw]):
      with self.subTest(candidates=candidates):
        current.state.data["cleanup"] = {"schema": 1, "run": current.state.data["run"],
          "candidates": copy.deepcopy(candidates), "skipped": []}
        current.state.flush()
        with self.assertRaisesRegex(ReleaseError, "required"):
          apply(current, evidence_path)
        self.assertEqual(self.forgejo.deleted, [])
        self.assertFalse(current.state.data["cleanup"]["candidates"][-1].get("complete", False))

  def test_alias_is_retired_before_its_digest_in_reverse_ordered_saved_inventory(self):
    current, old_digest, evidence_path = self.completed_history()
    self.registry.aliases["application", "v0.9.0"] = old_digest
    self.forgejo.package_records = [package("application", old_digest), package("application", "v0.9.0")]
    current.state.data["cleanup"] = plan(current)
    self.assertEqual(current.state.data["cleanup"]["candidates"][1]["version"], old_digest)
    apply(current, evidence_path)
    packages = [item for item in self.forgejo.deleted if item[0] == "package"]
    self.assertEqual(packages, [("package", "application", "v0.9.0"), ("package", "application", old_digest)])

  def test_new_unscheduled_older_alias_between_digest_deletions_stops_retry(self):
    current, old_digest, evidence_path = self.completed_history()
    first = self.registry.add("application", "unlisted", "0.5.0")
    self.registry.aliases.pop(("application", "unlisted"))
    self.forgejo.package_records = [package("application", first), package("application", old_digest)]
    current.state.data["cleanup"] = plan(current)
    original = self.forgejo.delete_package
    def introduce_alias(name, reference):
      original(name, reference)
      if reference == first:
        self.registry.aliases["application", "v0.9.0"] = old_digest
        self.forgejo.package_records.append(package("application", "v0.9.0"))
    with patch.object(self.forgejo, "delete_package", side_effect=introduce_alias):
      with self.assertRaisesRegex(ReleaseError, "required"):
        apply(current, evidence_path)
    self.assertIn(("package", "application", first), self.forgejo.deleted)
    self.assertNotIn(("package", "application", old_digest), self.forgejo.deleted)
    self.assertTrue(next(item for item in current.state.data["cleanup"]["candidates"] if item.get("version") == first)["complete"])

  def test_changed_pending_alias_stops_before_any_deletion(self):
    current, old_digest, evidence_path = self.completed_history()
    self.registry.aliases["application", "v0.9.0"] = old_digest
    self.forgejo.package_records = [package("application", "v0.9.0"), package("application", old_digest)]
    current.state.data["cleanup"] = plan(current)
    self.registry.add("application", "v0.9.0", "0.7.0")
    with self.assertRaisesRegex(ReleaseError, "changed"):
      apply(current, evidence_path)
    self.assertEqual(self.forgejo.deleted, [])

  def test_cleanup_checks_all_architectures_for_ownership_and_version(self):
    current, old_digest, _ = self.completed_history()
    image = self.registry.images["application", old_digest]
    for labels in ({}, {"org.opencontainers.image.source": "foreign", "org.opencontainers.image.version": "0.1.0"},
                   {"org.opencontainers.image.source": current.source, "org.opencontainers.image.version": "9.0.0"}):
      with self.subTest(labels=labels):
        self.registry.images["application", old_digest] = image
        _, record = self.registry.graph("application", old_digest)
        record = copy.deepcopy(record)
        node = next(node for node in record["nodes"].values() if node["configuration"])
        node["configuration"]["architecture"] = "riscv64"
        node["configuration"]["config"]["Labels"] = labels
        node["incoming"][0]["descriptor"]["platform"]["architecture"] = "riscv64"
        self.registry.images["application", old_digest] = image | {"evidence": record}
        self.forgejo.package_records = [package("application", old_digest)]
        self.assertFalse(any(item.get("kind") == "package" for item in plan(current)["candidates"]))

  def test_lost_alias_deletion_response_reconciles_before_digest_deletion(self):
    current, old_digest, evidence_path = self.completed_history()
    self.registry.aliases["application", "v0.9.0"] = old_digest
    self.forgejo.package_records = [package("application", old_digest), package("application", "v0.9.0")]
    original = self.forgejo.delete_package
    def lost_response(name, reference):
      original(name, reference)
      raise SystemExit("Lost deletion response")
    with patch.object(self.forgejo, "delete_package", side_effect=lost_response):
      with self.assertRaises(SystemExit):
        apply(current, evidence_path)
    self.assertEqual([item for item in self.forgejo.deleted if item[0] == "package"],
      [("package", "application", "v0.9.0")])
    apply(self.workflow("2.0.0"), evidence_path)
    self.assertEqual([item for item in self.forgejo.deleted if item[0] == "package"],
      [("package", "application", "v0.9.0"), ("package", "application", old_digest)])

  def test_malformed_or_unavailable_inventory_does_not_grant_deletion_authority(self):
    current, old_digest, evidence_path = self.completed_history()
    self.forgejo.package_records = [package("application", old_digest)]
    current.state.data["cleanup"] = plan(current)
    for response in (None, [None], [package("application", None)]):
      with self.subTest(response=response), patch.object(self.forgejo, "packages", return_value=response):
        with self.assertRaises(ReleaseError):
          apply(current, evidence_path)
        self.assertEqual(self.forgejo.deleted, [])
    with patch.object(self.forgejo, "packages", side_effect=ReleaseError("Remote operation failed with HTTP 401")):
      with self.assertRaisesRegex(ReleaseError, "401"):
        apply(current, evidence_path)
    self.assertEqual(self.forgejo.deleted, [])
