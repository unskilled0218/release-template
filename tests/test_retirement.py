import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from release_template import cleanup
from release_template.adapters import Registry
from release_template.cleanup import apply, plan
from release_template.core import ReleaseError, digest, load
from release_template.state import State
from tests.support import COMMIT, evidence, package
from tests import test_adapters


class RetirementPolicyTests(unittest.TestCase):
  def setUp(self):
    self.a, self.b, self.c = (digest(value) for value in (b"a", b"b", b"c"))

  def test_chains_and_transitive_dependencies_retire_referrers_first(self):
    graphs = {("image", self.c): {self.c}, ("image", self.b): {self.b, self.c},
              ("image", self.a): {self.a, self.b, self.c, digest(b"unlisted")}}
    self.assertEqual(cleanup.retirement_order(graphs), [("image", self.a), ("image", self.b), ("image", self.c)])

  def test_shared_children_wait_for_all_parents_and_ties_are_stable(self):
    graphs = {("image", self.b): {self.b, self.c}, ("image", self.a): {self.a, self.c}, ("image", self.c): {self.c}}
    order = cleanup.retirement_order(graphs)
    self.assertEqual(order[:-1], sorted([("image", self.a), ("image", self.b)]))
    self.assertEqual(order[-1], ("image", self.c))
    self.assertEqual(cleanup.retirement_order(dict(reversed(list(graphs.items())))), order)

  def test_same_digest_in_other_image_namespace_does_not_share_authority(self):
    graphs = {("z-first", self.a): {self.a, self.b}, ("a-second", self.b): {self.b},
              ("a-second", self.a): {self.a}}
    self.assertEqual(cleanup.retirement_order(graphs), sorted(graphs))
    self.assertEqual(cleanup.retirement_order({}), [])

  def test_cycles_missing_roots_duplicates_and_mutable_dependencies_are_rejected(self):
    for graphs in ({("image", self.a): {self.a, self.b}, ("image", self.b): {self.b, self.a}},
                   {("image", self.a): {self.b}}, {("image", self.a): [self.a, self.a]},
                   {("image", self.a): [self.a, "latest"]}, {("image", "latest"): ["latest"]}):
      with self.subTest(graphs=graphs), self.assertRaises(ReleaseError):
        cleanup.retirement_order(graphs)
    with patch.object(cleanup, "MAX_RETIREMENT_REFERENCES", 1), self.assertRaises(ReleaseError):
      cleanup.retirement_order({("image", self.a): {self.a, self.b}})

  def test_schedule_binding_ignores_progress_but_not_candidate_identity(self):
    candidate = {"kind": "package", "name": "image", "version": self.a, "digest": self.a}
    inventory = {"schema": 1, "run": "fixture", "candidates": [candidate], "skipped": []}
    inventory["retirement"] = cleanup.make_retirement(inventory, {("image", self.a): {"graph": {self.a}}})
    before = copy.deepcopy(inventory["retirement"])
    candidate["complete"] = True
    cleanup.validate_retirement(inventory)
    self.assertEqual(inventory["retirement"], before)
    candidate["name"] = "other"
    with self.assertRaises(ReleaseError):
      cleanup.validate_retirement(inventory)

  def test_unknown_or_incomplete_metadata_fails_closed(self):
    candidates = [{"kind": "package", "name": "image", "version": value, "digest": value} for value in (self.a, self.b)]
    inventory = {"schema": 1, "run": "fixture", "candidates": candidates, "skipped": []}
    rows = {("image", self.a): {"graph": {self.a, self.b}}, ("image", self.b): {"graph": {self.b}}}
    inventory["retirement"] = cleanup.make_retirement(inventory, rows)
    bad = []
    for field in inventory["retirement"]:
      changed = copy.deepcopy(inventory)
      del changed["retirement"][field]
      bad.append(changed)
    for field, value in (("schema", 2), ("run", "other"), ("fingerprint", "wrong"), ("order", [])):
      changed = copy.deepcopy(inventory)
      changed["retirement"][field] = value
      bad.append(changed)
    changed = copy.deepcopy(inventory)
    changed["retirement"]["order"].reverse()
    bad.append(changed)
    changed = copy.deepcopy(inventory)
    changed["retirement"]["graphs"].append(copy.deepcopy(changed["retirement"]["graphs"][0]))
    bad.append(changed)
    changed = copy.deepcopy(inventory)
    changed["retirement"]["graphs"].pop()
    bad.append(changed)
    changed = copy.deepcopy(inventory)
    changed["candidates"].append(copy.deepcopy(changed["candidates"][0]))
    bad.append(changed)
    for changed in bad:
      with self.subTest(metadata=changed), self.assertRaises(ReleaseError):
        cleanup.validate_retirement(changed)


class RemovalGitea:
  """Scoped deletion really removes fixture content; no synthetic graph recovery."""

  def __init__(self, server):
    self.server = server
    self.records, self.deleted = [], []
    self.before_delete = self.after_delete = None

  def packages(self):
    return copy.deepcopy(self.records)

  def releases(self):
    return []

  def package_path(self, name, reference):
    return name + ":" + reference

  def get(self, path, absent=False):
    if path == "/api/v1/version":
      return {"version": "28.2.0"}
    name, reference = path.split(":", 1)
    return next((copy.deepcopy(item) for item in self.records if
                 (item["name"], item["version"]) == (name, reference)), None)

  def delete_package(self, name, reference):
    if self.before_delete:
      self.before_delete(name, reference)
    self.records = [item for item in self.records if (item["name"], item["version"]) != (name, reference)]
    self.server.content.pop(reference, None)
    self.deleted.append((name, reference))
    if self.after_delete:
      self.after_delete(name, reference)


class RetirementIntegrationTests(unittest.TestCase):
  def setUp(self):
    self.server = test_adapters.AdapterTests()
    self.server.setUp()
    self.addCleanup(self.server.doCleanups)
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.config = self.server.config()
    self.config["images"][0]["platforms"] = ["linux/amd64"]
    self.registry = Registry(self.config, "fixture", "fixture-token")
    self.gitea = RemovalGitea(self.server)
    self.current = self.server.image(labels=self.server.labels() | {"org.opencontainers.image.version": "2.0.0"})
    self.identity = {"repository": self.config["repository"], "template": "fixture-revision"}
    self.path = self.root / "checkpoints/v2.0.0.json"
    self.workflow = SimpleNamespace(config=self.config, registry=self.registry, gitea=self.gitea,
      release_version="2.0.0", tag="v2.0.0", state=State(self.path, self.identity))
    self.workflow.state.data["outputs"] = {"application": {"digest": self.current}}
    self.workflow.state.data["published"] = True
    self.workflow.state.flush()
    self.workflow.verify_publication = lambda: self.registry.verify("application", self.current,
      ["linux/amd64"], COMMIT, "2.0.0", self.server.labels()["org.opencontainers.image.source"])
    self.evidence = evidence(self.root / "evidence.json")
    self.evidence.write_text(json.dumps(json.loads(self.evidence.read_text()) | {"origin": self.server.origin}))

  def inventory(self, references):
    self.gitea.records = [package("application", reference) for reference in references]

  def resume(self):
    self.workflow.state = State(self.path, self.identity)
    apply(self.workflow, self.evidence)

  def test_child_first_inventory_completes_and_keeps_current_publication(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    self.resume()
    self.assertEqual(self.gitea.deleted, [("application", parent), ("application", child)])
    self.assertTrue(self.workflow.state.data["cleanup_complete"])
    self.workflow.verify_publication()

  def test_fixture_does_not_recreate_a_deleted_dependency(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    self.gitea.delete_package("application", child)
    with self.assertRaisesRegex(ReleaseError, "absent"):
      self.registry.graph("application", parent)

  def nested_candidates(self):
    child = self.server.image()
    nested = self.server.index([{"digest": child}])
    outer = self.server.index([{"digest": nested}])
    other = self.server.put(self.server.content[nested] | {"annotations": {"fixture": "second parent"}})
    return child, nested, outer, other

  def test_nested_and_shared_dependencies_complete_in_shuffled_inventory_orders(self):
    child, nested, outer, other = self.nested_candidates()
    content = copy.deepcopy(self.server.content)
    initial = copy.deepcopy(self.workflow.state.data)
    references = [child, outer, other, nested]
    for order in (references, list(reversed(references)), [nested, child, other, outer]):
      with self.subTest(order=order):
        self.server.content = copy.deepcopy(content)
        self.workflow.state.data = copy.deepcopy(initial)
        self.workflow.state.flush()
        self.gitea.deleted.clear()
        self.inventory(order)
        self.resume()
        deleted = [reference for _, reference in self.gitea.deleted]
        self.assertLess(deleted.index(outer), deleted.index(nested))
        self.assertLess(deleted.index(nested), deleted.index(child))
        self.assertLess(deleted.index(other), deleted.index(child))
        self.assertEqual(set(deleted), set(references))
        self.workflow.verify_publication()

  def test_transitive_dependency_through_unlisted_intermediate_is_ordered(self):
    child = self.server.image()
    intermediate = self.server.index([{"digest": child}])
    outer = self.server.index([{"digest": intermediate}])
    self.inventory([child, outer])
    self.resume()
    self.assertEqual(self.gitea.deleted, [("application", outer), ("application", child)])
    self.assertIn(intermediate, self.server.content)

  def test_subject_dependencies_retire_referring_image_first(self):
    subject = self.server.image()
    referrer = self.server.put(self.server.content[subject] | {"subject": {"digest": subject}})
    self.inventory([subject, referrer])
    self.resume()
    self.assertEqual(self.gitea.deleted, [("application", referrer), ("application", subject)])

  def test_ineligible_attestation_subject_root_preserves_its_dependency(self):
    subject = self.server.image()
    attestation = self.server.attestation(subject)
    self.inventory([subject, attestation["digest"]])
    with self.assertRaisesRegex(ReleaseError, "ambiguous"):
      self.resume()
    self.assertEqual(self.gitea.deleted, [])
    self.registry.graph("application", attestation["digest"])
    self.workflow.verify_publication()

  def test_read_only_plan_has_complete_schedule_without_checkpoint_writes(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    before = self.path.read_bytes()
    result = plan(self.workflow)
    self.assertEqual(result["retirement"]["order"], [["application", parent], ["application", child]])
    self.assertEqual(self.path.read_bytes(), before)
    self.assertEqual(self.gitea.deleted, [])

  def test_schedule_is_durable_before_first_delete_and_is_not_replanned(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    snapshots = []
    def assert_approval(name, reference):
      inventory = load(self.path)["cleanup"]
      cleanup.validate_retirement(inventory)
      snapshots.append(copy.deepcopy(inventory["retirement"]))
    self.gitea.before_delete = assert_approval
    self.resume()
    self.assertEqual(len(snapshots), 2)
    self.assertEqual(snapshots[0], snapshots[1])

  def test_restart_at_each_digest_deletion_and_completion_boundary(self):
    references = self.nested_candidates()
    content = copy.deepcopy(self.server.content)
    initial = copy.deepcopy(self.workflow.state.data)
    for stage in ("lost response", "before completion flush", "after completion flush"):
      for boundary in range(1, len(references) + 1):
        with self.subTest(stage=stage, boundary=boundary):
          self.server.content = copy.deepcopy(content)
          self.workflow.state.data = copy.deepcopy(initial)
          self.workflow.state.flush()
          self.gitea.deleted.clear()
          self.inventory(references)
          original = self.workflow.state.flush
          def interrupted_flush():
            completed = sum(bool(item.get("complete")) for item in
              self.workflow.state.data.get("cleanup", {}).get("candidates", []))
            interrupt = completed == boundary and len(self.gitea.deleted) == boundary
            if stage == "before completion flush" and interrupt:
              raise SystemExit("Termination before completion flush")
            original()
            if stage == "after completion flush" and interrupt:
              raise SystemExit("Termination after completion flush")
          def lost_response(name, reference):
            if stage == "lost response" and len(self.gitea.deleted) == boundary:
              raise SystemExit("Accepted deletion, response lost")
          self.gitea.after_delete = lost_response
          with patch.object(self.workflow.state, "flush", side_effect=interrupted_flush), self.assertRaises(SystemExit):
            apply(self.workflow, self.evidence)
          approved = copy.deepcopy(load(self.path)["cleanup"]["retirement"])
          self.gitea.after_delete = None
          self.resume()
          self.assertEqual(len(self.gitea.deleted), len(references))
          self.assertEqual({reference for _, reference in self.gitea.deleted}, set(references))
          self.assertEqual(self.workflow.state.data["cleanup"]["retirement"], approved)
          self.assertTrue(self.workflow.state.data["cleanup_complete"])
          self.workflow.verify_publication()

  def test_interrupted_schedule_persistence_performs_no_deletion(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    before = self.path.read_bytes()
    with patch.object(self.workflow.state, "flush", side_effect=SystemExit("Before durable approval")):
      with self.assertRaises(SystemExit):
        apply(self.workflow, self.evidence)
    self.assertEqual(self.gitea.deleted, [])
    self.assertEqual(self.path.read_bytes(), before)
    self.resume()
    self.assertTrue(self.workflow.state.data["cleanup_complete"])

  def test_survivors_introduced_between_parent_and_child_block_dependency_deletion(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    content = copy.deepcopy(self.server.content)
    initial = copy.deepcopy(self.workflow.state.data)
    for survivor in ("custom", "v0.9.0", "foreign root", "recreated parent"):
      with self.subTest(survivor=survivor):
        self.server.content = copy.deepcopy(content)
        self.workflow.state.data = copy.deepcopy(initial)
        self.workflow.state.flush()
        self.gitea.deleted.clear()
        self.inventory([child, parent])
        def introduce(name, reference):
          if reference != parent:
            return
          if survivor == "recreated parent":
            self.server.content[parent] = copy.deepcopy(content[parent])
            self.gitea.records.append(package("application", parent))
          elif survivor == "foreign root":
            root = self.server.index([{"digest": child}])
            self.gitea.records.append(package("application", root, "foreign/repository"))
          else:
            self.server.content[survivor] = copy.deepcopy(content[child])
            self.gitea.records.append(package("application", survivor))
        self.gitea.after_delete = introduce
        with self.assertRaises(ReleaseError):
          apply(self.workflow, self.evidence)
        self.gitea.after_delete = None
        self.assertEqual(self.gitea.deleted, [("application", parent)])
        self.assertIn(child, self.server.content)
        self.workflow.verify_publication()

  def test_authentication_failure_during_absence_reconciliation_stops_progress(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    original = self.gitea.get
    def get(path, absent=False):
      if path == "application:" + parent and ("application", parent) in self.gitea.deleted:
        raise ReleaseError("Remote operation failed with HTTP 401")
      return original(path, absent)
    with patch.object(self.gitea, "get", side_effect=get), self.assertRaisesRegex(ReleaseError, "401"):
      apply(self.workflow, self.evidence)
    self.assertEqual(self.gitea.deleted, [("application", parent)])
    self.assertIn(child, self.server.content)
    self.resume()
    self.assertTrue(self.workflow.state.data["cleanup_complete"])

  def test_changed_candidate_association_after_parent_deletion_is_not_authority(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    def change(name, reference):
      if reference == parent:
        self.gitea.records[0]["repository"] = {"full_name": "other/repository"}
    self.gitea.after_delete = change
    with self.assertRaises(ReleaseError):
      self.resume()
    self.assertEqual(self.gitea.deleted, [("application", parent)])
    self.assertIn(child, self.server.content)

  def test_intact_matching_identity_legacy_inventory_can_acquire_schedule(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    inventory = plan(self.workflow)
    del inventory["retirement"]
    self.workflow.state.data["cleanup"] = inventory
    self.workflow.state.flush()
    self.resume()
    self.assertEqual(self.gitea.deleted, [("application", parent), ("application", child)])
    self.assertIn("retirement", self.workflow.state.data["cleanup"])

  def test_legacy_partial_or_completed_raw_inventory_is_not_adopted(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    inventory = plan(self.workflow)
    del inventory["retirement"]
    for partial in ("completed flag", "missing child"):
      with self.subTest(partial=partial):
        saved = copy.deepcopy(inventory)
        if partial == "completed flag":
          saved["candidates"][0]["complete"] = True
        else:
          self.gitea.records = [package("application", parent)]
          self.server.content.pop(child)
        self.workflow.state.data["cleanup"] = saved
        self.workflow.state.flush()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ReleaseError, "operator recovery"):
          self.resume()
        self.assertEqual(self.gitea.deleted, [])
        self.assertEqual(self.path.read_bytes(), before)

  def test_alias_only_legacy_inventory_uses_empty_digest_schedule(self):
    old = self.server.image()
    self.server.content["v0.9.0"] = self.server.content[old]
    self.inventory(["v0.9.0"])
    inventory = plan(self.workflow)
    del inventory["retirement"]
    self.workflow.state.data["cleanup"] = inventory
    self.workflow.state.flush()
    self.resume()
    self.assertEqual(self.workflow.state.data["cleanup"]["retirement"]["order"], [])
    self.assertEqual(self.gitea.deleted, [("application", "v0.9.0")])

  def test_validly_bound_but_incomplete_graph_evidence_cannot_override_live_graph(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    inventory = plan(self.workflow)
    inventory["retirement"] = cleanup.make_retirement(inventory,
      {("application", child): {"graph": {child}}, ("application", parent): {"graph": {parent}}})
    self.workflow.state.data["cleanup"] = inventory
    self.workflow.state.flush()
    with self.assertRaisesRegex(ReleaseError, "topology differs"):
      self.resume()
    self.assertEqual(self.gitea.deleted, [])

  def test_completed_parent_reappearance_is_a_survivor_not_renewed_authority(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    parent_content = copy.deepcopy(self.server.content[parent])
    self.inventory([child, parent])
    original = self.workflow.state.flush
    recreated = False
    def recreate_after_completion():
      nonlocal recreated
      original()
      candidates = self.workflow.state.data.get("cleanup", {}).get("candidates", [])
      if not recreated and any(item.get("version") == parent and item.get("complete") for item in candidates):
        self.server.content[parent] = copy.deepcopy(parent_content)
        self.gitea.records.append(package("application", parent))
        recreated = True
    with patch.object(self.workflow.state, "flush", side_effect=recreate_after_completion):
      with self.assertRaisesRegex(ReleaseError, "required"):
        apply(self.workflow, self.evidence)
    self.assertTrue(recreated)
    self.assertEqual(self.gitea.deleted, [("application", parent)])
    self.assertIn(child, self.server.content)

  def test_approved_schedule_survives_termination_before_first_delete(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    original = self.workflow.state.flush
    def persist_then_stop():
      original()
      raise SystemExit("Approval persisted, no deletion started")
    with patch.object(self.workflow.state, "flush", side_effect=persist_then_stop), self.assertRaises(SystemExit):
      apply(self.workflow, self.evidence)
    approved = copy.deepcopy(load(self.path)["cleanup"]["retirement"])
    self.assertEqual(self.gitea.deleted, [])
    self.resume()
    self.assertEqual(self.workflow.state.data["cleanup"]["retirement"], approved)
    self.assertTrue(self.workflow.state.data["cleanup_complete"])

  def test_malformed_approved_metadata_stops_before_delete(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    inventory = plan(self.workflow)
    for field, value in (("schema", 2), ("order", []), ("graphs", []), ("fingerprint", "wrong")):
      with self.subTest(field=field):
        changed = copy.deepcopy(inventory)
        changed["retirement"][field] = value
        self.workflow.state.data["cleanup"] = changed
        self.workflow.state.flush()
        before = self.path.read_bytes()
        with self.assertRaises(ReleaseError):
          self.resume()
        self.assertEqual(self.gitea.deleted, [])
        self.assertEqual(self.path.read_bytes(), before)

  def test_inconsistent_absence_evidence_stops_before_dependent_delete(self):
    child = self.server.image()
    parent = self.server.index([{"digest": child}])
    self.inventory([child, parent])
    original = self.gitea.get
    def stale_get(path, absent=False):
      if path == "application:" + parent and ("application", parent) in self.gitea.deleted:
        return package("application", parent)
      return original(path, absent)
    with patch.object(self.gitea, "get", side_effect=stale_get), self.assertRaisesRegex(ReleaseError, "not yet absent"):
      apply(self.workflow, self.evidence)
    self.assertEqual(self.gitea.deleted, [("application", parent)])
    self.assertIn(child, self.server.content)
    self.resume()
    self.assertEqual(self.gitea.deleted, [("application", parent), ("application", child)])
