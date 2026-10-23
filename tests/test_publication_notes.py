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
from release_template.core import ReleaseError, canonical, digest, load
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
