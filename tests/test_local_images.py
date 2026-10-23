"""Removal-aware Docker fixtures; no tests delete real host images or contact a daemon."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from release_template.core import ReleaseError, canonical, load, save
from release_template.local import DockerLocal, LocalImages
from release_template.workflow import Workflow
from tests.support import COMMIT, REVISION, FakeGitea, FakeRegistry, FakeRunner, configuration


ROOT = "sha256:" + "c" * 64
LOCAL_ID = "sha256:" + "d" * 64
PARENT_ID = "sha256:" + "e" * 64
REFERENCE = "gitea.invalid/fixtures/application@" + ROOT


class LocalStore:
  def __init__(self):
    self.rows, self.removed, self.in_use = [], [], set()
    self.daemon = {"context": "fixture", "endpoint": "connection-hash", "daemon": "fixture-daemon"}
    self.lose = self.noop = self.fail = False

  def binding(self):
    return copy.deepcopy(self.daemon)

  def inventory(self):
    if self.fail:
      raise ReleaseError("Unavailable daemon")
    return copy.deepcopy(self.rows)

  def used(self, reference):
    return reference in self.in_use

  def remove(self, reference):
    self.removed.append(reference)
    if not self.noop:
      remaining = []
      for row in self.rows:
        if reference not in row["tags"] + row["digests"]:
          remaining.append(row)
          continue
        row = copy.deepcopy(row)
        row["tags"] = [item for item in row["tags"] if item != reference]
        row["digests"] = [item for item in row["digests"] if item != reference]
        if row["tags"] or row["digests"]:
          remaining.append(row)
      self.rows = remaining
    if self.lose:
      self.lose = False
      raise SystemExit("Lost removal response")


class LocalImageTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.config = configuration() | {"remove_local_images": True}
    self.registry = FakeRegistry()
    self.runner = FakeRunner(self.registry)
    self.api = FakeGitea(self.registry)
    self.store = LocalStore()
    self.workflow = self.reopen()

  def reopen(self):
    workflow = Workflow(self.root, self.config, "1.0.0", REVISION, self.runner, self.registry, self.api, COMMIT)
    workflow.local = LocalImages(workflow, self.store)
    return workflow

  def pulled(self, observed=True):
    self.workflow.local.start()
    declaration = self.workflow.local.declare(REFERENCE, ["linux/amd64", "linux/arm64"])
    self.store.rows.append({"id": LOCAL_ID, "tags": [], "digests": [REFERENCE]})
    if observed:
      save(declaration["journal"], {"schema": 1, "run": declaration["run"], "reference": REFERENCE,
                                   "observations": {"linux/amd64": LOCAL_ID, "linux/arm64": LOCAL_ID}})
      self.workflow.local.observe(declaration)
    self.workflow.state.data["outputs"] = {"application": {"digest": ROOT}}
    self.workflow.state.data["published"] = True
    self.workflow.state.flush()
    # Unit seam: full publication verification belongs to the workflow/CLI tests.
    self.workflow.publication_verified = True
    return declaration

  def test_owned_reference_removed_once_and_baseline_identity_preserved(self):
    self.store.rows = [{"id": PARENT_ID, "tags": [], "digests": []}]
    self.pulled()
    before = load(self.workflow.state.path)
    outcomes = self.workflow.local.finalize()
    self.assertEqual(outcomes, [{"reference": REFERENCE, "result": "removed"}])
    self.assertEqual(self.store.rows, [{"id": PARENT_ID, "tags": [], "digests": []}])
    reopened = self.reopen()
    reopened.local.start()
    reopened.publication_verified = True
    self.assertEqual(reopened.local.finalize()[0]["result"], "already absent")
    self.assertEqual(self.store.removed, [REFERENCE])
    after = load(self.workflow.state.path)
    self.assertEqual(canonical(after["local_finalization"]["baseline"]), canonical(before["local_finalization"]["baseline"]))
    self.assertEqual(after["identity"], before["identity"])

  def test_preexisting_reference_and_id_are_protected(self):
    for preexisting in ([{"id": LOCAL_ID, "tags": [], "digests": [REFERENCE]}],
                        [{"id": LOCAL_ID, "tags": ["ubuntu:24.04"], "digests": []}]):
      with self.subTest(preexisting=preexisting):
        self.workflow.state.data.pop("local_finalization", None)
        self.workflow.state.data["outputs"] = {}
        self.store.rows = preexisting
        self.pulled()
        self.assertIn("pre-existing", self.workflow.local.finalize()[0]["result"])
        self.assertEqual(self.store.removed, [])

  def test_shared_and_container_used_images_are_protected(self):
    self.pulled()
    self.store.rows[0]["tags"] = ["other/project:keep"]
    self.assertIn("shared", self.workflow.local.finalize()[0]["result"])
    self.store.rows[0]["tags"] = []
    self.store.in_use.add(REFERENCE)
    self.assertIn("container", self.workflow.local.finalize()[0]["result"])
    self.assertEqual(self.store.removed, [])

  def test_changed_and_unobserved_images_are_safe_skips(self):
    self.pulled(observed=False)
    self.assertIn("uncertain", self.workflow.local.finalize()[0]["result"])
    entry = self.workflow.local.record()["references"][REFERENCE]
    entry["observations"] = {"linux/amd64": LOCAL_ID}
    self.store.rows[0]["id"] = PARENT_ID
    self.assertIn("changed", self.workflow.local.finalize()[0]["result"])
    self.assertEqual(self.store.removed, [])

  def test_opaque_hook_missing_journal_does_not_gain_authority(self):
    declaration = self.pulled(observed=False)
    self.workflow.local.observe(declaration)
    self.assertIn("opaque hook", self.workflow.local.finalize()[0]["result"])
    self.assertEqual(self.store.removed, [])

  def test_restart_after_pull_before_observation_keeps_original_baseline(self):
    declaration = self.pulled(observed=False)
    baseline = canonical(self.workflow.local.record()["baseline"])
    # A hook may have flushed its private journal just before the parent process died.
    save(declaration["journal"], {"schema": 1, "run": declaration["run"], "reference": REFERENCE,
                                 "observations": {"linux/amd64": LOCAL_ID}})
    reopened = self.reopen()
    reopened.local.start()
    reopened.local.observe(declaration)
    reopened.publication_verified = True
    self.assertEqual(canonical(reopened.local.record()["baseline"]), baseline)
    self.assertEqual(reopened.local.finalize()[0]["result"], "removed")

  def test_lost_removal_response_and_completion_flush_resume_without_delete(self):
    self.pulled()
    self.store.lose = True
    with self.assertRaises(SystemExit):
      self.workflow.local.finalize()
    self.assertEqual(self.reopen().local.record()["references"][REFERENCE]["status"], "removing")
    reopened = self.reopen()
    reopened.local.start()
    reopened.publication_verified = True
    self.assertEqual(reopened.local.finalize()[0]["result"], "already absent")
    self.assertEqual(self.store.removed, [REFERENCE])

  def test_noop_removal_is_failure_and_retry_does_not_republish(self):
    self.pulled()
    self.store.noop = True
    self.assertTrue(self.workflow.local.finalize()[0]["result"].startswith("failed:"))
    self.store.noop = False
    self.assertEqual(self.workflow.local.finalize()[0]["result"], "removed")
    self.assertEqual(self.api.records, [])
    self.assertEqual(self.runner.calls, [])

  def test_daemon_failure_is_never_absence(self):
    self.pulled()
    self.store.fail = True
    self.assertTrue(all(item["result"].startswith("failed:") for item in self.workflow.local.finalize()))
    saved = load(self.workflow.state.path)
    self.assertTrue(saved["local_finalization"]["references"][REFERENCE]["status"].startswith("failed:"))
    self.assertEqual(self.store.removed, [])

  def test_same_context_different_daemon_refuses_start_and_removal(self):
    self.pulled()
    self.store.daemon["daemon"] = "replaced-daemon"
    reopened = self.reopen()
    with self.assertRaisesRegex(ReleaseError, "differs"):
      reopened.local.start()
    reopened.publication_verified = True
    with self.assertRaisesRegex(ReleaseError, "differs"):
      reopened.local.finalize()
    self.assertEqual(self.store.removed, [])

  def test_missing_or_malformed_baseline_after_operations_cannot_be_adopted(self):
    self.workflow.state.intent("source", {"commit": COMMIT})
    with self.assertRaisesRegex(ReleaseError, "baseline missing"):
      self.workflow.local.start()
    self.workflow.state.data["local_finalization"] = {"schema": 1}
    with self.assertRaisesRegex(ReleaseError, "malformed"):
      self.workflow.local.start()
    self.assertEqual(self.store.removed, [])

  def test_persisted_publication_flag_is_not_current_verification(self):
    self.pulled()
    reopened = self.reopen()
    with self.assertRaisesRegex(ReleaseError, "this invocation"):
      reopened.local.finalize()
    self.assertEqual(self.store.removed, [])

  def test_false_optin_performs_no_daemon_operations(self):
    self.workflow.local.enabled = False
    self.store.fail = True
    self.workflow.local.start()
    self.assertIsNone(self.workflow.local.declare(REFERENCE, ["linux/amd64"]))
    self.assertEqual(self.workflow.local.finalize(), [])

  def test_journal_rejects_foreign_scope_unknown_platform_and_invalid_ids(self):
    declaration = self.pulled(observed=False)
    base = {"schema": 1, "run": declaration["run"], "reference": REFERENCE, "observations": {"linux/amd64": LOCAL_ID}}
    for change in ({"run": "foreign"}, {"reference": "foreign"}, {"observations": {"linux/386": LOCAL_ID}},
                   {"observations": {"linux/amd64": ROOT + "invalid"}}):
      save(declaration["journal"], base | change)
      with self.subTest(change=change), self.assertRaises(ReleaseError):
        self.workflow.local.observe(declaration)
    self.assertEqual(self.store.removed, [])

  def test_new_external_verification_pull_can_be_journaled_and_removed_again(self):
    declaration = self.pulled()
    self.workflow.local.finalize()
    self.workflow.local.declare(REFERENCE, ["linux/amd64", "linux/arm64"])
    self.store.rows.append({"id": LOCAL_ID, "tags": [], "digests": [REFERENCE]})
    self.workflow.local.observe(declaration)
    self.workflow.local.finalize()
    self.assertEqual(self.store.removed, [REFERENCE, REFERENCE])
    self.assertEqual(self.store.rows, [])

  def test_partial_removal_survives_restart_and_failed_reference_is_retryable(self):
    self.root = self.root / "multi"
    self.config["images"].append({"name": "other", "platforms": ["linux/amd64"]})
    self.workflow = self.reopen()
    declaration = self.pulled()
    second = REFERENCE.replace("application@", "other@")
    self.workflow.state.data["outputs"]["other"] = {"digest": ROOT}
    next_declaration = self.workflow.local.declare(second, ["linux/amd64"])
    self.store.rows.append({"id": PARENT_ID, "tags": [], "digests": [second]})
    save(next_declaration["journal"], {"schema": 1, "run": declaration["run"], "reference": second,
                                      "observations": {"linux/amd64": PARENT_ID}})
    self.workflow.local.observe(next_declaration)
    original = self.store.remove
    def remove(reference):
      if reference == second:
        raise ReleaseError("Injected second-reference failure")
      original(reference)
    with patch.object(self.store, "remove", side_effect=remove):
      outcomes = self.workflow.local.finalize()
    self.assertEqual(outcomes[0]["result"], "removed")
    self.assertTrue(outcomes[1]["result"].startswith("failed:"))
    # Reopen the exact approved configuration, without changing publication identity.
    self.config = self.workflow.config
    reopened = self.reopen()
    reopened.publication_verified = True
    outcomes = reopened.local.finalize()
    self.assertEqual([item["result"] for item in outcomes], ["already absent", "removed"])
    self.assertEqual(self.store.removed, [REFERENCE, second])

  def test_undeclared_new_alias_is_reported_but_never_removed(self):
    self.pulled()
    self.store.rows.append({"id": PARENT_ID, "tags": ["gitea.invalid/fixtures/application:latest"], "digests": []})
    outcomes = self.workflow.local.finalize()
    self.assertIn("undeclared", outcomes[-1]["result"])
    self.assertEqual(self.store.rows[0]["tags"], ["gitea.invalid/fixtures/application:latest"])

  def containerd_build_and_pull(self):
    self.workflow.local.start()
    staging = "gitea.invalid/fixtures/application:rt-" + self.workflow.state.data["run"] + "-application"
    platforms = self.config["images"][0]["platforms"]
    self.workflow.local.build_intent(staging, platforms)
    self.store.rows.append({"id": ROOT, "tags": [staging, REFERENCE], "digests": [REFERENCE]})
    self.workflow.local.build_observe(staging, ROOT)
    declaration = self.workflow.local.declare(REFERENCE, platforms)
    save(declaration["journal"], {"schema": 1, "run": declaration["run"], "reference": REFERENCE,
      "observations": {platform: ROOT for platform in platforms},
      "platform_ids": {"linux/amd64": LOCAL_ID, "linux/arm64": PARENT_ID}})
    self.workflow.local.observe(declaration)
    self.workflow.state.data["outputs"] = {"application": {"digest": ROOT}}
    self.workflow.state.data["published"] = True
    self.workflow.state.flush()
    self.workflow.publication_verified = True
    return staging

  def test_containerd_index_and_member_ids_are_distinct_and_owned_staging_untags_first(self):
    staging = self.containerd_build_and_pull()
    record = self.workflow.local.record()
    self.assertNotEqual(record["references"][REFERENCE]["observations"], record["references"][REFERENCE]["platform_ids"])
    outcomes = self.workflow.local.finalize()
    self.assertEqual([item["result"] for item in outcomes], ["removed", "removed"])
    self.assertEqual(self.store.removed, [staging, REFERENCE])
    self.assertEqual(self.store.rows, [])

  def test_containerd_proven_group_does_not_override_a_shared_user_alias(self):
    self.containerd_build_and_pull()
    self.store.rows[0]["tags"].append("other/project:keep")
    outcomes = self.workflow.local.finalize()
    self.assertTrue(all("shared" in item["result"] for item in outcomes))
    self.assertEqual(self.store.removed, [])

  def test_containerd_interruption_after_staging_untag_reconciles_before_index_removal(self):
    staging = self.containerd_build_and_pull()
    self.store.lose = True
    with self.assertRaises(SystemExit):
      self.workflow.local.finalize()
    reopened = self.reopen()
    reopened.local.start()
    reopened.publication_verified = True
    outcomes = reopened.local.finalize()
    self.assertEqual([item["result"] for item in outcomes], ["already absent", "removed"])
    self.assertEqual(self.store.removed, [staging, REFERENCE])

  def test_unobserved_build_reference_cannot_borrow_pull_ownership(self):
    staging = self.containerd_build_and_pull()
    self.workflow.local.record()["references"][staging]["observations"] = {}
    outcomes = self.workflow.local.finalize()
    self.assertIn("uncertain", outcomes[0]["result"])
    self.assertIn("shared", outcomes[1]["result"])
    self.assertEqual(self.store.removed, [])


class DockerLocalBoundaryTests(unittest.TestCase):
  def test_exact_nonforce_no_parent_pruning_command(self):
    runner = Mock()
    DockerLocal(runner).remove(REFERENCE)
    runner.run.assert_called_once_with(["docker", "image", "rm", "--no-prune", REFERENCE])

  def test_all_containers_are_checked_including_stopped(self):
    runner = Mock()
    runner.run.return_value = "stopped-container\n"
    self.assertTrue(DockerLocal(runner).used(REFERENCE))
    runner.run.assert_called_once_with(["docker", "ps", "--all", "--filter", "ancestor=" + REFERENCE,
                                       "--format", "{{.ID}}"])

  def test_inventory_successful_empty_list_and_errors_are_distinct(self):
    runner = Mock()
    runner.run.return_value = ""
    self.assertEqual(DockerLocal(runner).inventory(), [])
    runner.run.side_effect = ReleaseError("daemon unavailable")
    with self.assertRaises(ReleaseError):
      DockerLocal(runner).inventory()

  def test_inventory_preserves_untagged_ids_and_rejects_malformed_inspection(self):
    runner = Mock()
    runner.run.side_effect = [PARENT_ID + "\n", json.dumps([{"Id": PARENT_ID, "RepoTags": None, "RepoDigests": []}])]
    self.assertEqual(DockerLocal(runner).inventory(), [{"id": PARENT_ID, "tags": [], "digests": []}])
    runner.run.side_effect = [LOCAL_ID + "\n", "null"]
    with self.assertRaises(ReleaseError):
      DockerLocal(runner).inventory()
