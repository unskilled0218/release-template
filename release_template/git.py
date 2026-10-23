"""Source-bound note loading and exact annotated Git objects; no local tag replacement."""

import re

from .core import digest, require
from .policy import MAX_NOTES, annotation, metadata, normalize_notes, notes_text, tag_identity


class Git:
  def __init__(self, runner):
    self.runner = runner

  def notes(self, commit, path, release_version):
    return notes_text(self.runner.git_blob(commit, path, MAX_NOTES), release_version)

  def remote(self, tag):
    ref = "refs/tags/" + tag
    lines = self.runner.run(["git", "ls-remote", "--tags", "origin", ref, ref + "^{}"]).splitlines()
    values = {}
    for line in lines:
      fields = line.split()
      require(len(fields) == 2 and fields[1] in (ref, ref + "^{}") and
              re.fullmatch(r"[0-9a-f]{40}", fields[0]) and fields[1] not in values, "Malformed remote tag advertisement")
      values[fields[1]] = fields[0]
    if not values:
      return None
    require(ref in values, "Remote tag object is absent")
    return {"object": values[ref], "commit": values.get(ref + "^{}", values[ref]), "annotated": ref + "^{}" in values}

  def inspect(self, oid, tag):
    require(self.runner.run(["git", "cat-file", "-t", oid]).strip() == "tag", "New release requires annotated tag")
    size = int(self.runner.run(["git", "cat-file", "-s", oid]).strip())
    require(0 < size <= MAX_NOTES, "Tag annotation exceeds size bound")
    content = self.runner.run(["git", "cat-file", "tag", oid])
    headers, message = content.split("\n\n", 1)
    lines = headers.splitlines()
    require(len(lines) == 4 and lines[0].startswith("object ") and lines[1] == "type commit" and
            lines[2] == "tag " + tag and lines[3].startswith("tagger "), "Invalid direct annotated tag target")
    identity = tag_identity(message, tag)
    require(lines[0] == "object " + identity["commit"], "Annotated source commit differs")
    return identity

  def resolve(self, release):
    tag = release["tag_name"]
    remote = self.remote(tag)
    require(remote is not None, "Remote release tag is absent")
    if not remote["annotated"]:
      identity = metadata(release)
      require(identity["commit"] == remote["commit"], "Legacy release source tag differs")
      return identity
    self.runner.run(["git", "fetch", "--no-tags", "--no-write-fetch-head", "origin", remote["object"]])
    require(self.remote(tag) == remote, "Remote release tag changed during fetch")
    identity = self.inspect(remote["object"], tag)
    require(identity["commit"] == remote["commit"], "Peeled release commit differs")
    text = self.notes(identity["commit"], identity["notes"]["path"], identity["version"])
    require(digest(text.encode()) == identity["notes"]["digest"] and
            normalize_notes(release.get("body")) == text, "Published project notes differ: conflicting release")
    return identity

  def create(self, identity):
    tag = identity["tag"]
    # Deterministic tagger identity/time makes creation-before-checkpoint crashes replayable.
    content = ("object " + identity["commit"] + "\ntype commit\ntag " + tag +
               "\ntagger Release template <release-template@localhost> 0 +0000\n\n" + annotation(identity))
    oid = self.runner.run(["git", "mktag"], input_text=content).strip()
    require(re.fullmatch(r"[0-9a-f]{40}", oid) and self.inspect(oid, tag) == identity, "Created tag identity differs")
    existing = self.runner.run(["git", "tag", "--list", tag]).strip()
    if existing:
      local = self.runner.run(["git", "rev-parse", "--verify", "refs/tags/" + tag]).strip()
      require(local == oid, "Local release tag object conflicts")
    return oid
