"""Forward-only publication orchestration over durable operations."""

import json
from pathlib import Path
import tempfile

from .adapters import git_identity
from .core import ReleaseError, canonical, child, digest, image_order, load, promotion_allowed, require
from .policy import published
from .git import Git
from .linking import link_packages, verify_links
from .local import LocalImages
from .state import State


class Workflow:
  def __init__(self, root, config, release_version, revision, runner, registry, gitea, commit, link_window=None):
    self.root, self.config = Path(root), config
    self.release_version, self.tag = release_version, "v" + release_version
    self.runner, self.registry, self.gitea, self.commit = runner, registry, gitea, commit
    identity = {"repository": config["repository"], "version": release_version,
                "commit": commit, "config": digest(canonical(config)), "template": revision}
    self.state = State(self.root / ".release-template" / (self.tag + ".json"), identity)
    self.source = config["gitea"].rstrip("/") + "/" + config["repository"]
    self.git, self.link_window = Git(runner), link_window
    self.local = LocalImages(self)
    self.publication_verified = False

  def freeze_notes(self):
    path = self.config.get("release_notes")
    require(path is not None, "Add committed release_notes before publication")
    text = self.git.notes(self.commit, path, self.release_version)
    frozen = {"path": path, "digest": digest(text.encode()), "text": text}
    if "notes" in self.state.data:
      require(self.state.data["notes"] == frozen, "Frozen release notes changed")
    else:
      self.state.data["notes"] = frozen
      self.state.flush()
    return frozen

  def aliases(self):
    result = {}
    for image in self.config["images"]:
      name = image["name"]
      result[name + ":latest"] = self.registry.resolve(name, "latest")
      if image.get("retain_version"):
        result[name + ":" + self.tag] = self.registry.resolve(name, self.tag)
    return result

  def targets(self):
    result = {}
    for image in self.config["images"]:
      name = image["name"]
      if name not in self.state.data["outputs"]:
        continue
      result[name + ":latest"] = self.state.data["outputs"][name]["digest"]
      if image.get("retain_version"):
        result[name + ":" + self.tag] = self.state.data["outputs"][name]["digest"]
    return result

  def release_identity(self):
    notes = self.freeze_notes()
    return {"schema": 2, "version": self.release_version, "tag": self.tag,
            "commit": self.commit, "template": self.state.data["identity"]["template"],
            "repository": self.config["repository"], "targets": self.targets(),
            "platforms": {image["name"]: image["platforms"] for image in self.config["images"]},
            "notes": {"path": notes["path"], "digest": notes["digest"]}}

  def snapshot(self):
    if "predecessor" in self.state.data:
      return
    accepted = published(self.gitea.releases(), self.git.resolve)
    aliases = self.aliases()
    if accepted is None:
      require(all(value is None for value in aliases.values()), "Existing aliases have no recognized predecessor release")
    else:
      require(accepted["repository"] == self.config["repository"], "Predecessor repository differs")
      from .core import version
      require(version(accepted["version"]) < version(self.release_version), "New publication must advance version")
      for alias, value in aliases.items():
        if alias.endswith(":latest"):
          require(value is not None and accepted["targets"].get(alias) == value, "Predecessor alias metadata differs")
        else:
          require(value is None, "Requested immutable version alias already exists")
    self.state.data["predecessor"] = {"release": accepted, "aliases": aliases}
    self.state.flush()

  def eligibility(self):
    accepted = published(self.gitea.releases(), self.git.resolve)
    predecessor = self.state.data["predecessor"]
    if accepted is not None:
      require(accepted.get("repository") == self.config["repository"], "Publication repository differs")
      if accepted["version"] == self.release_version:
        require(accepted == self.release_identity(), "Equal version has conflicting publication identity")
      else:
        require(accepted == predecessor["release"], "Accepted publication changed since preparation")
    else:
      require(predecessor["release"] is None, "Predecessor release disappeared")
    promotion_allowed(self.aliases(), predecessor["aliases"], self.targets(), self.release_version, accepted)

  def unchanged(self):
    require(git_identity(self.runner, self.config) == self.commit, "Source changed during release")

  def synchronize_source(self):
    details = {"commit": self.commit, "push": self.config.get("source_push", False)}
    operation = self.state.intent("source", details)
    remote = self.runner.run(["git", "ls-remote", "origin", "refs/heads/main"]).split()
    if not remote or remote[0] != self.commit:
      require(details["push"] and operation["status"] != "complete", "Remote main differs from release source")
      self.runner.run(["git", "push", "origin", "HEAD:refs/heads/main"])
      remote = self.runner.run(["git", "ls-remote", "origin", "refs/heads/main"]).split()
    require(remote and remote[0] == self.commit, "Remote main not confirmed")
    self.state.complete("source")

  def tag_source(self):
    self.eligibility()
    identity = self.release_identity()
    previous = self.state.data["operations"].get("tag")
    oid = previous["details"]["object"] if previous else self.git.create(identity)
    require(self.git.inspect(oid, self.tag) == identity, "Recorded annotated tag identity differs")
    self.state.intent("tag", {"tag": self.tag, "commit": self.commit, "object": oid, "identity": identity})
    destination = "refs/tags/" + self.tag
    expected = {"object": oid, "commit": self.commit, "annotated": True}
    remote = self.git.remote(self.tag)
    if remote is None:
      require(not previous or previous["status"] != "complete", "Confirmed remote tag disappeared")
      self.runner.run(["git", "push", "origin", oid + ":" + destination])
    else:
      require(remote == expected, "Remote version tag object/identity conflicts")
    require(self.git.remote(self.tag) == expected, "Remote Git tag not confirmed")
    self.state.complete("tag")

  def check_local_tag(self):
    existing = self.runner.run(["git", "tag", "--list", self.tag]).strip()
    if existing:
      commit = self.runner.run(["git", "rev-parse", "--verify", "refs/tags/" + self.tag + "^{commit}"]).strip()
      require(commit == self.commit, "Local version tag identifies another commit")

  def prepare_image(self, image):
    name = image["name"]
    staging_tag = "rt-" + self.state.data["run"] + "-" + name
    reference = self.config["registry"] + "/" + self.gitea.owner + "/" + name
    metadata_path = self.state.path.parent / (self.state.data["run"] + "-" + name + ".build")
    details = {"tag": staging_tag, "image": reference, "commit": self.commit, "platforms": image["platforms"]}
    operation_name = "build:" + name
    existed = operation_name in self.state.data["operations"]
    self.state.intent(operation_name, details)
    self.state.data["staging"].setdefault(name, {"tag": staging_tag, "digest": None})
    self.state.flush()
    existing = self.registry.resolve(name, staging_tag)
    if existing is None:
      require(not existed, "Build outcome is uncertain or staging was removed; explicit recovery required, no automatic rebuild")
      dependencies = {parent: reference.rsplit("/", 1)[0] + "/" + parent + "@" +
                      self.state.data["outputs"][parent]["digest"] for parent in image.get("dependencies", [])}
      with tempfile.TemporaryDirectory(prefix="release-source-") as snapshot:
        self.runner.archive(self.commit, snapshot)
        inputs = {"schema": 1, "commit": self.commit, "version": self.release_version, "source": self.source,
                  "source_root": snapshot, "staging": reference + ":" + staging_tag, "platforms": image["platforms"],
                  "dependencies": dependencies, "metadata_file": str(metadata_path)}
        environment = {"RELEASE_INPUT_JSON": canonical(inputs).decode()}
        if "build" in image:
          self.runner.run(image["build"], extra=environment)
        else:
          self.local.build_intent(reference + ":" + staging_tag, image["platforms"])
          arguments = ["docker", "buildx", "build", "--platform", ",".join(image["platforms"]),
                       "--provenance=false", "--metadata-file", str(metadata_path), "--push",
                       "--tag", reference + ":" + staging_tag,
                       "--label", "org.opencontainers.image.revision=" + self.commit,
                       "--label", "org.opencontainers.image.version=" + self.release_version,
                       "--label", "org.opencontainers.image.source=" + self.source,
                       "--file", str(child(snapshot, image.get("dockerfile", "Dockerfile")))]
          for secret in image.get("secrets", []):
            secret_file = Path(secret["file"]).expanduser()
            if not secret_file.is_absolute():
              secret_file = self.root / secret_file
            require(secret_file.is_file() and "," not in str(secret_file), "BuildKit secret file is missing or malformed")
            arguments.extend(["--secret", "id=" + secret["id"] + ",src=" + str(secret_file.resolve())])
          arguments.append(str(child(snapshot, image.get("context", "."))))
          self.runner.run(arguments)
      existing = self.registry.resolve(name, staging_tag)
      require(existing is not None, "Build did not publish its prepared identity")
    previous = self.state.data["outputs"].get(name)
    require(previous is None or previous["digest"] == existing, "Prepared image identity changed")
    self.registry.verify(name, existing, image["platforms"], self.commit, self.release_version, self.source)
    self.local.build_observe(reference + ":" + staging_tag, existing)
    if metadata_path.exists():
      build_metadata = load(metadata_path)
      require(build_metadata.get("containerimage.digest") == existing, "Build metadata differs from staging digest")
    if "verify" in image:
      inputs = {"schema": 1, "image": reference + "@" + existing, "commit": self.commit,
                "version": self.release_version, "platforms": image["platforms"]}
      declaration = self.local.declare(inputs["image"], image["platforms"])
      if declaration is not None:
        inputs["local_images"] = declaration
      self.runner.run(image["verify"], extra={"RELEASE_INPUT_JSON": canonical(inputs).decode()})
      self.local.observe(declaration)
    self.state.data["outputs"][name] = {"digest": existing}
    self.state.data["staging"][name]["digest"] = existing
    self.state.flush()
    self.state.complete(operation_name)

  def promote(self):
    for alias, target in self.targets().items():
      self.unchanged()
      self.eligibility()
      name, tag = alias.split(":", 1)
      self.state.intent("promote:" + alias, {"digest": target, "alias": alias})
      if self.registry.resolve(name, tag) != target:
        reference = self.config["registry"] + "/" + self.gitea.owner + "/" + name
        self.runner.run(["docker", "buildx", "imagetools", "create", "--prefer-index=false",
                         "--tag", reference + ":" + tag, reference + "@" + target])
      require(self.registry.resolve(name, tag) == target, "Promotion changed the prepared manifest identity")
      self.state.complete("promote:" + alias)

  def verify_publication(self):
    self.publication_verified = False
    self.eligibility()
    require(len(self.state.data["outputs"]) == len(self.config["images"]), "Publication has missing prepared images")
    require(self.aliases() == self.targets(), "Final aliases do not identify the prepared release")
    release = self.gitea.release(self.tag)
    require(release is not None and not release.get("draft") and not release.get("prerelease") and
            not release.get("assets") and self.git.resolve(release) == self.release_identity(), "Text-only release not verified")
    for image in self.config["images"]:
      self.registry.verify(image["name"], self.state.data["outputs"][image["name"]]["digest"],
                           image["platforms"], self.commit, self.release_version, self.source)
    tag = self.state.data["operations"]["tag"]["details"]
    require(self.git.remote(self.tag) == {"object": tag["object"], "commit": self.commit, "annotated": True},
            "Remote release tag object changed")
    verify_links(self)
    self.publication_verified = True

  def publish(self):
    self.freeze_notes()
    self.local.start()
    self.snapshot()
    self.eligibility()
    self.check_local_tag()
    if not self.state.data.get("checked"):
      for check in self.config.get("checks", []):
        self.runner.run(check)
      self.unchanged()
      self.state.data["checked"] = True
      self.state.flush()
    self.synchronize_source()
    for image in image_order(self.config["images"]):
      self.unchanged()
      if image["name"] in self.state.data["outputs"] and self.state.data.get("published"):
        # Successful cleanup may already have retired staging aliases.
        self.registry.verify(image["name"], self.state.data["outputs"][image["name"]]["digest"],
                             image["platforms"], self.commit, self.release_version, self.source)
      else:
        self.prepare_image(image)
    self.eligibility()
    link_packages(self, self.link_window)
    self.tag_source()
    self.promote()
    self.eligibility()
    body = self.state.data["notes"]["text"]
    self.state.intent("release", {"body": body, "tag": self.tag})
    existing = self.gitea.release(self.tag)
    if existing is None:
      self.gitea.publish(self.tag, self.commit, body)
    else:
      require(self.git.resolve(existing) == self.release_identity() and not existing.get("assets") and
              not existing.get("draft") and not existing.get("prerelease"), "Existing release conflicts")
    self.verify_publication()
    self.state.complete("release")
    self.state.data["published"] = True
    self.state.flush()
