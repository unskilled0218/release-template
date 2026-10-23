"""Real Git object boundaries plus publication identity and recovery behavior."""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from release_template.adapters import Runner
from release_template.config import validate
from release_template.core import ReleaseError, canonical, digest, git_path, load
from release_template.git import Git
from release_template.policy import TAG_MARKER, annotation, notes_text, tag_identity, validate_identity
from release_template.workflow import Workflow
from tests.support import COMMIT, REVISION, FakeGitea, FakeRegistry, FakeRunner, configuration


def identity(commit=COMMIT, notes=None):
  notes = notes or b"# Release v1.0.0\n\nProject changes.\n"
  return {"schema": 2, "version": "1.0.0", "tag": "v1.0.0", "commit": commit, "template": REVISION,
          "repository": "fixtures/application", "targets": {"application:latest": "sha256:" + "c" * 64},
          "platforms": {"application": ["linux/amd64", "linux/arm64"]},
          "notes": {"path": "notes.md", "digest": digest(notes)}}


class NotesPolicyTests(unittest.TestCase):
  def test_committed_paths_are_lexical_and_preserve_exact_text(self):
    with patch.object(Path, "resolve", side_effect=AssertionError("Git paths must not resolve the worktree")):
      for path in ("notes.md", "docs/notes with space.md", ":(glob)literal*.md"):
        self.assertEqual(git_path(path), path)
      for path in (None, 1, "", "/notes.md", "../notes.md", "docs/../notes.md", "bad\x00.md"):
        with self.subTest(path=path), self.assertRaises(ReleaseError):
          git_path(path)

  def test_notes_normalization_is_narrow(self):
    self.assertEqual(notes_text(b"# Release v1.0.0\r\n\r\nProject fixes.\r\n\r\n", "1.0.0"),
                     "# Release v1.0.0\n\nProject fixes.\n")
    for data in (b"", b"\xff", b"# Release v2.0.0\n\nChanges.\n", b"x" * 65537, b"# Release v1.0.0\n"):
      with self.subTest(data=data[:24]), self.assertRaises(ReleaseError):
        notes_text(data, "1.0.0")

  def test_canonical_identity_roundtrip_preserves_platform_order_and_multiple_images(self):
    value = identity()
    value["targets"]["application:v1.0.0"] = value["targets"]["application:latest"]
    value["targets"]["other:latest"] = "sha256:" + "d" * 64
    value["platforms"]["other"] = ["linux/arm64", "linux/amd64"]
    self.assertEqual(tag_identity(annotation(value), value["tag"]), value)

  def test_missing_unknown_duplicate_and_contradictory_fields_fail(self):
    mutations = [lambda v: v.pop("notes"), lambda v: v.update(extra=True), lambda v: v.update(schema=1),
                 lambda v: v.update(commit="branch"), lambda v: v.update(template=""),
                 lambda v: v.update(repository="missing-owner"), lambda v: v.update(tag="v2.0.0"),
                 lambda v: v["notes"].update(path="../notes"), lambda v: v["notes"].update(digest="bad"),
                 lambda v: v["targets"].update({"other:latest": "sha256:" + "a" * 64}),
                 lambda v: v["targets"].update({"application:v1.0.0": "sha256:" + "a" * 64}),
                 lambda v: v["platforms"].update(application=["linux/amd64", "linux/amd64"])]
    for mutate in mutations:
      value = copy.deepcopy(identity())
      mutate(value)
      with self.subTest(value=value), self.assertRaises(ReleaseError):
        validate_identity(value, "v1.0.0")
    duplicate = annotation(identity()).replace('"schema":2', '"schema":2,"schema":2')
    with self.assertRaisesRegex(ReleaseError, "Duplicate"):
      tag_identity(duplicate, "v1.0.0")
    for message in (TAG_MARKER + "{", annotation(identity()) + "\n", "unrecognized\n"):
      with self.assertRaises(ReleaseError):
        tag_identity(message, "v1.0.0")

  def test_configuration_requires_safe_notes_and_boolean_optins(self):
    with tempfile.TemporaryDirectory() as root:
      original = configuration()
      self.assertIs(validate(original, root), original)
      missing = dict(original)
      missing.pop("release_notes")
      for bad in (missing, original | {"release_notes": "../notes"}, original | {"release_notes": "/notes"},
                  original | {"link_packages": 1}, original | {"remove_local_images": "yes"}):
        with self.subTest(bad=bad), self.assertRaises(ReleaseError):
          validate(bad, root)


class GitNotesTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name) / "source"
    self.root.mkdir()
    self.remote = self.root.parent / "remote.git"
    self.run_git("init", "--bare", "--quiet", str(self.remote))
    self.run_git("init", "--quiet", "--initial-branch=main")
    self.run_git("config", "user.name", "Fixture")
    self.run_git("config", "user.email", "fixture@localhost")
    self.notes = b"# Release v1.0.0\n\nProject fixes.\n"
    (self.root / "notes.md").write_bytes(self.notes)
    (self.root / "notes with space.md").write_bytes(self.notes)
    (self.root / "link.md").symlink_to("notes.md")
    self.run_git("add", ".")
    self.run_git("commit", "--quiet", "-m", "Fixture")
    self.commit = self.run_git("rev-parse", "HEAD").strip()
    self.run_git("remote", "add", "origin", str(self.remote))
    self.run_git("push", "--quiet", "origin", "HEAD:main")
    self.runner = Runner(self.root)
    self.git = Git(self.runner)
    self.value = identity(self.commit, self.notes)

  def run_git(self, *arguments):
    return subprocess.run(["git", *arguments], cwd=self.root, check=True, capture_output=True, text=True).stdout

  def push_annotation(self):
    oid = self.git.create(self.value)
    self.run_git("push", "--quiet", "origin", oid + ":refs/tags/v1.0.0")
    return oid

  def test_notes_come_from_regular_committed_blob_not_worktree(self):
    (self.root / "notes.md").write_text("mutable worktree text")
    self.assertEqual(self.git.notes(self.commit, "notes.md", "1.0.0"), self.notes.decode())
    self.assertEqual(self.git.notes(self.commit, "notes with space.md", "1.0.0"), self.notes.decode())
    for path in ("missing.md", "link.md", "../notes.md"):
      with self.subTest(path=path), self.assertRaises(ReleaseError):
        self.git.notes(self.commit, path, "1.0.0")

  def test_real_annotation_is_deterministic_pushes_and_reads_without_local_tag(self):
    oid = self.push_annotation()
    self.assertEqual(self.git.create(self.value), oid)
    self.assertEqual(self.git.remote("v1.0.0"), {"object": oid, "commit": self.commit, "annotated": True})
    self.assertEqual(self.git.resolve({"tag_name": "v1.0.0", "body": self.notes.decode()}), self.value)
    self.assertEqual(self.run_git("tag", "--list"), "")

  def test_fetch_does_not_replace_local_tag_or_worktree(self):
    self.push_annotation()
    self.run_git("tag", "v1.0.0", self.commit)
    local = self.run_git("rev-parse", "refs/tags/v1.0.0")
    (self.root / "notes.md").write_text("local edits\n")
    self.git.resolve({"tag_name": "v1.0.0", "body": self.notes.decode()})
    self.assertEqual(self.run_git("rev-parse", "refs/tags/v1.0.0"), local)
    self.assertEqual((self.root / "notes.md").read_text(), "local edits\n")

  def test_body_hash_and_local_tag_conflicts_fail_closed(self):
    self.push_annotation()
    for text in (self.notes.decode() + "Edited", "", None):
      with self.subTest(text=text), self.assertRaises(ReleaseError):
        self.git.resolve({"tag_name": "v1.0.0", "body": text})
    self.run_git("tag", "v1.0.0", self.commit)
    with self.assertRaisesRegex(ReleaseError, "Local.*conflicts"):
      self.git.create(self.value)

  def test_lightweight_new_release_and_malformed_annotation_never_gain_legacy_authority(self):
    self.run_git("push", "--quiet", "origin", self.commit + ":refs/tags/v1.0.0")
    with self.assertRaises(ReleaseError):
      self.git.resolve({"tag_name": "v1.0.0", "body": self.notes.decode()})
    self.run_git("tag", "-a", "v2.0.0", "-m", TAG_MARKER + "{}")
    self.run_git("push", "--quiet", "origin", "refs/tags/v2.0.0")
    with self.assertRaises(ReleaseError):
      self.git.resolve({"tag_name": "v2.0.0", "body": "\nRelease identity:\n{}"})

  def test_nested_annotation_target_is_rejected(self):
    oid = self.git.create(self.value)
    content = ("object " + oid + "\ntype tag\ntag v1.0.0\ntagger Fixture <fixture@localhost> 0 +0000\n\n" +
               annotation(self.value))
    nested = self.runner.run(["git", "mktag"], input_text=content).strip()
    with self.assertRaisesRegex(ReleaseError, "direct"):
      self.git.inspect(nested, "v1.0.0")

  def tag_workflow(self):
    config = configuration() | {"release_notes": "notes.md"}
    registry = FakeRegistry()
    workflow = Workflow(self.root, config, "1.0.0", REVISION, self.runner, registry, FakeGitea(registry), self.commit)
    workflow.snapshot()
    workflow.state.data["outputs"].setdefault("application", {"digest": "sha256:" + "c" * 64})
    workflow.state.flush()
    return workflow

  def interrupted_tag(self, accepted=False):
    workflow = self.tag_workflow()
    original = self.runner.run
    def run(arguments, **kwargs):
      if arguments[:2] == ["git", "push"]:
        if accepted:
          original(arguments, **kwargs)
        raise SystemExit("Interrupted tag push")
      return original(arguments, **kwargs)
    with patch.object(self.runner, "run", side_effect=run), self.assertRaises(SystemExit):
      workflow.tag_source()
    return workflow

  def prune_pending_annotation(self, workflow):
    details = copy.deepcopy(workflow.state.data["operations"]["tag"]["details"])
    # Prune only this fixture's newly created source repository, never a user checkout.
    self.run_git("prune", "--expire=now")
    result = subprocess.run(["git", "cat-file", "-e", details["object"]], cwd=self.root, capture_output=True)
    self.assertNotEqual(result.returncode, 0, "The annotation must actually be absent before retry")
    return details

  def test_pending_annotation_is_recreated_after_pruning_before_push(self):
    workflow = self.interrupted_tag()
    details = self.prune_pending_annotation(workflow)
    before = canonical(workflow.state.data["identity"])
    reopened = self.tag_workflow()
    reopened.tag_source()
    self.assertEqual(reopened.state.data["operations"]["tag"]["details"], details)
    self.assertEqual(self.git.remote("v1.0.0")["object"], details["object"])
    self.assertEqual(self.git.inspect(details["object"], "v1.0.0"), self.value)
    self.assertEqual(canonical(reopened.state.data["identity"]), before)

  def test_pruned_annotation_with_accepted_remote_tag_needs_no_second_push(self):
    workflow = self.interrupted_tag(accepted=True)
    details = self.prune_pending_annotation(workflow)
    calls = []
    original = self.runner.run
    def run(arguments, **kwargs):
      calls.append(arguments)
      return original(arguments, **kwargs)
    with patch.object(self.runner, "run", side_effect=run):
      reopened = self.tag_workflow()
      reopened.tag_source()
    self.assertFalse(any(call[:2] == ["git", "push"] for call in calls))
    self.assertEqual(reopened.state.data["operations"]["tag"]["details"], details)
    self.assertEqual(reopened.state.data["operations"]["tag"]["status"], "complete")

  def test_annotation_pruned_before_intent_persistence_replays_identical_bytes(self):
    workflow = self.tag_workflow()
    approved = self.git.create(self.value)
    original = workflow.state.intent
    def intent(name, details):
      if name == "tag":
        raise SystemExit("Before tag intent persistence")
      return original(name, details)
    with patch.object(workflow.state, "intent", side_effect=intent), self.assertRaises(SystemExit):
      workflow.tag_source()
    self.assertNotIn("tag", load(workflow.state.path)["operations"])
    self.run_git("prune", "--expire=now")
    self.assertNotEqual(subprocess.run(["git", "cat-file", "-e", approved], cwd=self.root, capture_output=True).returncode, 0)
    reopened = self.tag_workflow()
    reopened.tag_source()
    self.assertEqual(reopened.state.data["operations"]["tag"]["details"]["object"], approved)

  def test_conflicting_pending_tag_intent_is_never_rewritten_or_pushed(self):
    workflow = self.interrupted_tag()
    approved = copy.deepcopy(workflow.state.data["operations"]["tag"])
    variants = [approved | {"status": "unknown"}, approved | {"id": "malformed"},
                {key: value for key, value in approved.items() if key != "id"}]
    for change in ({"object": "not-a-hash"}, {"object": "0" * 40}, {"commit": "a" * 40},
                   {"identity": self.value | {"template": "c" * 40}}, {"extra": True}):
      variants.append(approved | {"details": approved["details"] | change})
    original = self.runner.run
    for operation in variants:
      workflow.state.data["operations"]["tag"] = operation
      workflow.state.flush()
      before = workflow.state.path.read_bytes()
      calls = []
      def run(arguments, **kwargs):
        calls.append(arguments)
        return original(arguments, **kwargs)
      with self.subTest(operation=operation), patch.object(self.runner, "run", side_effect=run):
        with self.assertRaises(ReleaseError):
          self.tag_workflow().tag_source()
      self.assertFalse(any(call[:2] == ["git", "push"] for call in calls))
      self.assertEqual(workflow.state.path.read_bytes(), before)

  def test_completed_remote_tag_disappearance_is_not_automatic_repair_authority(self):
    workflow = self.tag_workflow()
    workflow.tag_source()
    self.run_git("--git-dir", str(self.remote), "update-ref", "-d", "refs/tags/v1.0.0")
    original = self.runner.run
    calls = []
    def run(arguments, **kwargs):
      calls.append(arguments)
      return original(arguments, **kwargs)
    with patch.object(self.runner, "run", side_effect=run), self.assertRaisesRegex(ReleaseError, "disappeared"):
      self.tag_workflow().tag_source()
    self.assertFalse(any(call[:2] == ["git", "push"] for call in calls))

  def test_object_creation_failure_stops_with_pending_intent_and_unchanged_outputs(self):
    workflow = self.interrupted_tag()
    before = workflow.state.path.read_bytes()
    original = self.runner.run
    def run(arguments, **kwargs):
      if arguments[:2] == ["git", "mktag"]:
        raise ReleaseError("Injected unavailable Git object store")
      return original(arguments, **kwargs)
    with patch.object(self.runner, "run", side_effect=run), self.assertRaisesRegex(ReleaseError, "unavailable"):
      self.tag_workflow().tag_source()
    self.assertEqual(workflow.state.path.read_bytes(), before)

  def test_pending_local_tag_conflict_preserves_local_ref_and_intent(self):
    workflow = self.interrupted_tag()
    self.run_git("tag", "v1.0.0", self.commit)
    before = workflow.state.path.read_bytes()
    with self.assertRaisesRegex(ReleaseError, "Local.*conflicts"):
      self.tag_workflow().tag_source()
    self.assertEqual(self.run_git("rev-parse", "refs/tags/v1.0.0").strip(), self.commit)
    self.assertEqual(workflow.state.path.read_bytes(), before)
    self.assertIsNone(self.git.remote("v1.0.0"))

  def test_pending_remote_lightweight_conflict_is_not_reassigned(self):
    workflow = self.interrupted_tag()
    self.run_git("push", "--quiet", "origin", self.commit + ":refs/tags/v1.0.0")
    remote_before = self.git.remote("v1.0.0")
    before = workflow.state.path.read_bytes()
    original = self.runner.run
    calls = []
    def run(arguments, **kwargs):
      calls.append(arguments)
      return original(arguments, **kwargs)
    with patch.object(self.runner, "run", side_effect=run), self.assertRaisesRegex(ReleaseError, "conflicts"):
      self.tag_workflow().tag_source()
    self.assertFalse(any(call[:2] == ["git", "push"] for call in calls))
    self.assertEqual(self.git.remote("v1.0.0"), remote_before)
    self.assertEqual(workflow.state.path.read_bytes(), before)

  def test_historical_regular_notes_survive_current_clean_symlink(self):
    self.push_annotation()
    old = {"tag_name": "v1.0.0", "body": self.notes.decode()}
    (self.root / "notes.md").unlink()
    (self.root / "notes.md").symlink_to("notes with space.md")
    (self.root / "next.md").write_text("# Release v2.0.0\n\nNew project fixes.\n")
    self.run_git("add", ".")
    self.run_git("commit", "--quiet", "-m", "Move current notes independently of history")
    self.assertEqual(self.run_git("status", "--porcelain"), "")
    self.assertEqual(self.git.resolve(old), self.value)
    self.assertEqual(self.git.notes(self.run_git("rev-parse", "HEAD").strip(), "next.md", "2.0.0"),
                     "# Release v2.0.0\n\nNew project fixes.\n")

  def test_successor_publication_accepts_history_with_changed_current_notes_path(self):
    old_object = self.push_annotation()
    old = {"tag_name": "v1.0.0", "body": self.notes.decode()}
    (self.root / "notes.md").unlink()
    (self.root / "notes.md").symlink_to("notes with space.md")
    (self.root / "next.md").write_text("# Release v2.0.0\n\nNew project fixes.\n")
    (self.root / ".gitignore").write_text(".release-template/\n")
    (self.root / "Dockerfile").write_text("FROM scratch\n")
    self.run_git("add", ".")
    self.run_git("commit", "--quiet", "-m", "Next release with independent notes")
    self.run_git("push", "--quiet", "origin", "HEAD:main")
    commit = self.run_git("rev-parse", "HEAD").strip()
    config = configuration() | {"release_notes": "next.md", "checks": []}
    registry = FakeRegistry()
    registry.aliases["application", "latest"] = self.value["targets"]["application:latest"]
    api = FakeGitea(registry)
    api.publish("v1.0.0", self.commit, old["body"])
    calls = []
    original = self.runner.run
    def run(arguments, **kwargs):
      if arguments[:3] == ["docker", "buildx", "build"]:
        calls.append("build")
        staging = arguments[arguments.index("--tag") + 1].rsplit(":", 1)[1]
        registry.add("application", staging, "2.0.0", commit=commit)
        return ""
      if arguments[:4] == ["docker", "buildx", "imagetools", "create"]:
        calls.append("promote")
        registry.aliases["application", "latest"] = arguments[-1].split("@", 1)[1]
        return ""
      return original(arguments, **kwargs)
    workflow = Workflow(self.root, config, "2.0.0", REVISION, self.runner, registry, api, commit)
    # Only Git destination/cleanliness entry checks are injected; all object/blob/push operations are real local Git.
    with patch("release_template.workflow.git_identity", return_value=commit), patch.object(self.runner, "run", side_effect=run):
      workflow.publish()
    self.assertTrue(workflow.state.data["published"])
    self.assertEqual(calls, ["build", "promote"])
    self.assertEqual(api.records[0]["body"], old["body"])
    self.assertEqual(self.git.remote("v1.0.0")["object"], old_object)
    self.assertEqual(self.run_git("status", "--porcelain"), "")

  def test_historical_blob_ignores_current_parent_symlink_and_external_target(self):
    directory = self.root / "history"
    directory.mkdir()
    (directory / "notes.md").write_bytes(self.notes)
    self.run_git("add", "history/notes.md")
    self.run_git("commit", "--quiet", "-m", "Captured regular nested notes")
    captured = self.run_git("rev-parse", "HEAD").strip()
    self.run_git("rm", "--quiet", "history/notes.md")
    outside = self.root.parent / "outside"
    outside.mkdir()
    (outside / "notes.md").write_text("Not release notes; must not be read.\n")
    directory.symlink_to(outside, target_is_directory=True)
    self.run_git("add", "history")
    self.run_git("commit", "--quiet", "-m", "Current source uses a different path type")
    self.assertEqual(self.git.notes(captured, "history/notes.md", "1.0.0"), self.notes.decode())
    self.assertEqual((outside / "notes.md").read_text(), "Not release notes; must not be read.\n")
    self.assertEqual(self.run_git("status", "--porcelain"), "")

  def test_captured_symlink_is_rejected_even_when_current_path_is_regular(self):
    captured = self.commit
    (self.root / "link.md").unlink()
    (self.root / "link.md").write_bytes(self.notes)
    self.run_git("add", "link.md")
    self.run_git("commit", "--quiet", "-m", "Current regular file does not authorize an old symlink")
    with self.assertRaisesRegex(ReleaseError, "regular committed"):
      self.git.notes(captured, "link.md", "1.0.0")

  def test_historical_regular_blob_survives_current_missing_path_and_directory(self):
    self.run_git("rm", "--quiet", "notes.md")
    self.run_git("commit", "--quiet", "-m", "Remove a historical path from current source")
    self.assertEqual(self.git.notes(self.commit, "notes.md", "1.0.0"), self.notes.decode())
    (self.root / "notes.md").mkdir()
    (self.root / "notes.md/current.txt").write_text("Different current tree layout\n")
    self.run_git("add", "notes.md/current.txt")
    self.run_git("commit", "--quiet", "-m", "Use a directory at the historical path")
    self.assertEqual(self.git.notes(self.commit, "notes.md", "1.0.0"), self.notes.decode())
    self.assertEqual(self.run_git("status", "--porcelain"), "")

  def test_committed_blob_reads_are_literal_and_reject_nonfile_or_unsafe_paths(self):
    for name in ("literal*.md", ":(glob)literal.md"):
      (self.root / name).write_bytes(self.notes)
    (self.root / "directory").mkdir()
    (self.root / "directory/notes.md").write_bytes(self.notes)
    (self.root / "directory-link").symlink_to("directory", target_is_directory=True)
    self.run_git("add", ".")
    self.run_git("commit", "--quiet", "-m", "Literal filenames and negative tree entries")
    commit = self.run_git("rev-parse", "HEAD").strip()
    for name in ("literal*.md", ":(glob)literal.md"):
      self.assertEqual(self.git.notes(commit, name, "1.0.0"), self.notes.decode())
    for name in ("directory", "directory-link/notes.md", "*.md", "../notes.md", "/notes.md", "bad\x00.md", "missing.md"):
      with self.subTest(path=name), self.assertRaises(ReleaseError):
        self.git.notes(commit, name, "1.0.0")

  def test_captured_gitlinks_and_invalid_or_oversized_blob_bytes_are_rejected(self):
    (self.root / "oversized.md").write_bytes(b"x" * 65537)
    (self.root / "invalid.md").write_bytes(b"\xff")
    (self.root / "wrong-version.md").write_text("# Release v2.0.0\n\nWrong release.\n")
    self.run_git("add", ".")
    self.run_git("update-index", "--add", "--cacheinfo", "160000," + self.commit + ",gitlink")
    self.run_git("commit", "--quiet", "-m", "Negative committed object fixtures")
    commit = self.run_git("rev-parse", "HEAD").strip()
    for path in ("gitlink", "oversized.md", "invalid.md", "wrong-version.md"):
      with self.subTest(path=path), self.assertRaises(ReleaseError):
        self.git.notes(commit, path, "1.0.0")


class PublicationNotesTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.registry = FakeRegistry()
    self.runner = FakeRunner(self.registry)
    self.api = FakeGitea(self.registry)
    self.config = configuration()

  def workflow(self):
    return Workflow(self.root, self.config, "1.0.0", REVISION, self.runner, self.registry, self.api, COMMIT)

  def test_public_body_is_only_frozen_project_text_and_retry_has_no_writes(self):
    workflow = self.workflow()
    workflow.publish()
    self.assertEqual(self.api.records[0]["body"], workflow.state.data["notes"]["text"])
    self.assertNotIn("sha256:", self.api.records[0]["body"])
    self.assertNotIn("Release identity:", self.api.records[0]["body"])
    before = load(workflow.state.path)
    start = len(self.runner.calls)
    self.workflow().publish()
    writes = [call for call in self.runner.calls[start:] if call[:2] == ["git", "push"] or
              call[:3] == ["docker", "buildx", "build"] or call[:4] == ["docker", "buildx", "imagetools", "create"]]
    self.assertEqual(writes, [])
    self.assertEqual(load(workflow.state.path)["identity"], before["identity"])

  def test_notes_validation_precedes_source_push_and_build(self):
    self.runner.git_blob = lambda *args: b"# Release v2.0.0\n\nWrong version\n"
    with self.assertRaisesRegex(ReleaseError, "heading"):
      self.workflow().publish()
    self.assertEqual(self.runner.calls, [])
    self.assertEqual(self.api.records, [])

  def test_lost_tag_response_reuses_recorded_object_without_build_or_push(self):
    self.runner.kill_tag = True
    with self.assertRaises(SystemExit):
      self.workflow().publish()
    pending = load(self.workflow().state.path)
    self.assertEqual(pending["operations"]["tag"]["status"], "pending")
    self.workflow().publish()
    pushes = [call for call in self.runner.calls if call[:2] == ["git", "push"]]
    self.assertEqual(len(pushes), 1)
    self.assertEqual(load(self.workflow().state.path)["operations"]["tag"]["details"], pending["operations"]["tag"]["details"])

  def test_missing_pending_object_recovery_does_not_repeat_build_or_confirmed_push(self):
    self.runner.kill_tag = True
    with self.assertRaises(SystemExit):
      self.workflow().publish()
    before = load(self.workflow().state.path)
    self.runner.objects.clear()  # Simulate only the local annotation cache being collected.
    self.workflow().publish()
    after = load(self.workflow().state.path)
    self.assertEqual(after["identity"], before["identity"])
    self.assertEqual(after["operations"]["tag"]["details"], before["operations"]["tag"]["details"])
    for prefix in (["git", "push"], ["docker", "buildx", "build"], ["docker", "buildx", "imagetools", "create"]):
      self.assertEqual(sum(call[:len(prefix)] == prefix for call in self.runner.calls), 1, str(prefix))
    self.assertEqual(len(self.api.records), 1)

  def test_tag_creation_before_intent_crash_is_replayable(self):
    workflow = self.workflow()
    original = workflow.state.intent
    def crash(name, details):
      if name == "tag":
        raise SystemExit("before tag intent")
      return original(name, details)
    with patch.object(workflow.state, "intent", side_effect=crash), self.assertRaises(SystemExit):
      workflow.publish()
    objects = set(self.runner.objects)
    self.workflow().publish()
    self.assertEqual(set(self.runner.objects), objects)

  def test_static_legacy_predecessor_is_read_without_rewriting(self):
    # Deliberately static schema-1 sample, not produced by the schema-2 serializer.
    body = ('Container release 0.9.0. Images are published in Gitea Packages.\n\nRelease identity:\n'
            '{"schema":1,"version":"0.9.0","tag":"v0.9.0","commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            '"template":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","repository":"fixtures/application",'
            '"targets":{},"platforms":{"application":["linux/amd64","linux/arm64"]}}')
    value = json.loads(body.split("\nRelease identity:\n")[1])
    root = self.registry.add("application", "latest", "0.9.0")
    # Bind only the synthetic registry digest; keep the old-format body renderer independent.
    value["targets"]["application:latest"] = root
    old_body = body[:body.index('{')] + json.dumps(value)
    self.api.publish("v0.9.0", COMMIT, old_body)
    self.runner.tags["refs/tags/v0.9.0"] = COMMIT
    self.workflow().publish()
    self.assertEqual(self.api.records[0]["body"], old_body)
    self.assertEqual(self.runner.tags["refs/tags/v0.9.0"], COMMIT)
    self.assertEqual(len(self.api.records), 2)
