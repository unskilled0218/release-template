import copy
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from release_template.core import ReleaseError, digest
from release_template.policy import description
from release_template.oci import OCI_MANIFEST, IMAGE_CONFIGS


COMMIT = "a" * 40
REVISION = "b" * 40


def configuration():
  return {"schema": 2, "gitea": "https://gitea.invalid", "registry": "gitea.invalid",
          "repository": "fixtures/application", "source_push": False,
          "version": {"kind": "explicit"}, "checks": [["check-project"]],
          "images": [{"name": "application", "platforms": ["linux/amd64", "linux/arm64"]}]}


class FakeRegistry:
  def __init__(self):
    self.aliases, self.images = {}, {}

  def add(self, name, tag, release_version, commit=COMMIT, source="https://gitea.invalid/fixtures/application",
          platforms=("linux/amd64", "linux/arm64")):
    root = digest((name + release_version + commit).encode())
    child = digest((root + "child").encode())
    self.images[name, root] = {"version": release_version, "commit": commit, "source": source, "graph": {root, child},
                             "platforms": platforms}
    self.images[name, child] = self.images[name, root]
    self.aliases[name, tag] = root
    return root

  def resolve(self, name, reference):
    if reference.startswith("sha256:"):
      return reference if (name, reference) in self.images else None
    return self.aliases.get((name, reference))

  def verify(self, name, root, platforms, commit, release_version, source):
    from release_template.adapters import Registry
    return Registry.verify(self, name, root, platforms, commit, release_version, source)

  def graph(self, name, root):
    image = self.images[name, root]
    if "evidence" in image:
      return image["graph"], image["evidence"]
    nodes, descriptors = {}, []
    for platform in image["platforms"]:
      os_name, architecture = platform.split("/")
      reference = digest((root + platform).encode())
      descriptor = {"digest": reference, "platform": {"os": os_name, "architecture": architecture}}
      descriptors.append(descriptor)
      nodes[reference] = {"digest": reference, "incoming": [{"kind": "member", "descriptor": descriptor}],
        "manifest": {"schemaVersion": 2, "mediaType": OCI_MANIFEST,
                     "config": {"mediaType": IMAGE_CONFIGS[0]}, "layers": []},
        "configuration": {"os": os_name, "architecture": architecture, "config": {"Labels": {
          "org.opencontainers.image.revision": image["commit"],
          "org.opencontainers.image.version": image["version"], "org.opencontainers.image.source": image["source"]}}}}
    nodes[root] = {"digest": root, "incoming": [{"kind": "root", "descriptor": {"digest": root}}],
      "configuration": None, "manifest": {"schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json", "manifests": descriptors}}
    return image["graph"] | set(nodes), {"root": root, "nodes": nodes}


class FakeGitea:
  owner = "fixtures"
  def __init__(self, registry):
    self.registry = registry
    self.records, self.deleted = [], []
    self.package_records = []
    self.fail_publish = False
    self.fail_delete = False

  def releases(self):
    return copy.deepcopy(self.records)

  def release(self, tag):
    return next((copy.deepcopy(item) for item in self.records if item["tag_name"] == tag), None)

  def publish(self, tag, commit, body):
    self.records.append({"id": len(self.records) + 1, "tag_name": tag, "body": body,
                         "draft": False, "prerelease": False, "assets": []})
    if self.fail_publish:
      self.fail_publish = False
      raise SystemExit("Lost release response")

  def packages(self):
    return copy.deepcopy(self.package_records)

  def package_path(self, name, release_version):
    return name + ":" + release_version

  def get(self, path, absent=False):
    if path == "/api/v1/version":
      return {"version": "28.2.0"}
    name, reference = path.split(":", 1)
    return next((copy.deepcopy(item) for item in self.package_records if
                 item["name"] == name and item["version"] == reference), None)

  def delete_package(self, name, reference):
    if self.fail_delete:
      self.fail_delete = False
      raise ReleaseError("Injected deletion failure")
    self.deleted.append(("package", name, reference))
    self.package_records = [item for item in self.package_records if (item["name"], item["version"]) != (name, reference)]
    self.registry.aliases.pop((name, reference), None)
    if reference.startswith("sha256:"):
      self.registry.images.pop((name, reference), None)

  def delete_release(self, release_id):
    self.deleted.append(("release", release_id))
    self.records = [item for item in self.records if item["id"] != release_id]


class FakeRunner:
  def __init__(self, registry, release_version="1.0.0"):
    self.registry = registry
    self.release_version = release_version
    self.calls, self.tags = [], {}
    self.kill_build = self.kill_promote = self.kill_tag = False
    self.kill_source = False
    self.remote_commit = COMMIT
    self.drift = False

  def archive(self, commit, destination):
    if commit != COMMIT:
      raise AssertionError("Snapshot must identify captured source")
    Path(destination, "Dockerfile").write_text("FROM scratch\n")

  @contextmanager
  def docker_auth(self, registry, username, token):
    self.calls.append(["docker", "login", registry])
    yield

  def run(self, arguments, input_text=None, extra=None):
    self.calls.append(arguments)
    if arguments[:3] == ["git", "branch", "--show-current"]:
      return "main\n"
    if arguments[:3] == ["git", "status", "--porcelain"]:
      return " M changed" if self.drift else ""
    if arguments[:3] == ["git", "rev-parse", "HEAD"]:
      return COMMIT
    if arguments[:3] == ["git", "tag", "--list"]:
      return ""
    if arguments[:3] == ["git", "check-ignore", "--quiet"]:
      return ""
    if arguments[:3] == ["git", "remote", "get-url"]:
      return "https://gitea.invalid/fixtures/application.git\n"
    if arguments[:2] == ["git", "ls-remote"]:
      if "refs/heads/main" in arguments:
        return self.remote_commit + "\trefs/heads/main\n"
      requested = [value for value in arguments if value.startswith("refs/tags/") and not value.endswith("^{}")]
      return "".join(self.tags[tag] + "\t" + tag + "\n" for tag in requested if tag in self.tags)
    if arguments[:2] == ["git", "push"]:
      value = arguments[-1]
      if value == "HEAD:refs/heads/main":
        self.remote_commit = COMMIT
        if self.kill_source:
          self.kill_source = False
          raise SystemExit("Lost source push response")
      if ":refs/tags/" in value:
        commit, tag = value.split(":", 1)
        self.tags[tag] = commit
        if self.kill_tag:
          self.kill_tag = False
          raise SystemExit("Lost tag response")
      return ""
    if arguments[:3] == ["docker", "buildx", "build"]:
      reference = arguments[arguments.index("--tag") + 1]
      name, tag = reference.rsplit("/", 1)[1].split(":")
      platforms = arguments[arguments.index("--platform") + 1].split(",")
      self.registry.add(name, tag, self.release_version, platforms=platforms)
      if self.kill_build:
        self.kill_build = False
        raise SystemExit("Lost build response")
      return ""
    if arguments[:4] == ["docker", "buildx", "imagetools", "create"]:
      name, tag = arguments[arguments.index("--tag") + 1].rsplit("/", 1)[1].split(":")
      self.registry.aliases[name, tag] = arguments[-1].split("@", 1)[1]
      if self.kill_promote:
        self.kill_promote = False
        raise SystemExit("Lost promotion response")
      return ""
    if arguments == ["check-project"]:
      return ""
    if arguments == ["fixture-build"]:
      inputs = json.loads(extra["RELEASE_INPUT_JSON"])
      self.last_build_inputs = inputs
      name, tag = inputs["staging"].rsplit("/", 1)[1].split(":")
      self.registry.add(name, tag, self.release_version, platforms=inputs["platforms"])
      return ""
    if arguments[:3] == ["docker", "buildx", "version"]:
      return "buildx fixture"
    if arguments[:3] == ["docker", "buildx", "inspect"]:
      return "Name: fixture\nPlatforms: linux/amd64, linux/arm64\n"
    raise AssertionError("Unexpected command: " + repr(arguments))


def package(name, reference, repository="fixtures/application"):
  return {"type": "container", "name": name, "version": reference, "repository": {"full_name": repository}}


def evidence(path, verified_at=None):
  verified_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if verified_at is None else verified_at
  record = {"schema": 2, "product": "gitea", "origin": "https://gitea.invalid", "server_version": "28.2.0",
            "disposable_repository": "fixtures/disposable-contract", "operator": "fixture",
            "verified_at": verified_at, "alias_preserves_shared_manifest": True,
            "digest_deletion_is_scoped": True, "retained_platforms_pullable": True}
  path.write_text(json.dumps(record))
  return path
