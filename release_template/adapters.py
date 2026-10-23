"""Bounded external commands, trusted HTTP, Gitea and OCI evidence."""

import base64
import json
import os
import re
import shutil
import ssl
import subprocess
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler

from .config import CREDENTIAL_VARIABLES, UNSUPPORTED_CREDENTIAL_VARIABLES, endpoint
from .core import ReleaseError, canonical, digest, load, require
from .oci import immutable, runnable


class Runner:
  def __init__(self, root, token=""):
    self.root = Path(root)
    self.token = token
    self.environment = {key: value for key, value in os.environ.items()
                        if key not in CREDENTIAL_VARIABLES + UNSUPPORTED_CREDENTIAL_VARIABLES}

  def run(self, arguments, input_text=None, extra=None):
    environment = self.environment | (extra or {})
    try:
      result = subprocess.run(arguments, cwd=self.root, env=environment, input=input_text,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=7200)
    except (OSError, subprocess.TimeoutExpired) as exc:
      raise ReleaseError("Command unavailable or timed out; inspect prerequisites") from exc
    # Never relay raw command failures: hooks and tools can echo credentials or config files.
    require(result.returncode == 0, f"Command failed: {Path(arguments[0]).name} (exit {result.returncode})")
    return result.stdout.replace(self.token, "[redacted]") if self.token else result.stdout

  def archive(self, commit, destination):
    """Materialize only captured, committed files, never ignored local credentials/state."""
    destination = Path(destination).resolve()
    with tempfile.TemporaryFile() as output:
      process = subprocess.run(["git", "archive", "--format=tar", commit], cwd=self.root,
                               env=self.environment, stdout=output, stderr=subprocess.PIPE, timeout=60)
      require(process.returncode == 0, "Cannot export the captured Git source")
      output.seek(0)
      with tarfile.open(fileobj=output) as archive:
        from .core import child
        for member in archive:
          path = child(destination, member.name.rstrip("/"))
          if member.isdir():
            path.mkdir(parents=True, exist_ok=True)
          elif member.isfile():
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, path.open("wb") as target:
              shutil.copyfileobj(source, target)
            path.chmod(member.mode & 0o777)
          elif member.issym():
            require(not Path(member.linkname).is_absolute() and
                    (path.parent / member.linkname).resolve().is_relative_to(destination),
                    "Source archive symlink escapes build snapshot")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(member.linkname)
          else:
            raise ReleaseError("Source archive contains unsupported special entries")

  @contextmanager
  def docker_auth(self, registry, username, token):
    original = self.environment.copy()
    context = self.run(["docker", "context", "show"]).strip()
    with tempfile.TemporaryDirectory(prefix="release-auth-") as temporary:
      config = Path(temporary)
      # A nonempty auth inventory prevents Docker's implicit native-helper autodetection.
      (config / "config.json").write_bytes(canonical({"auths": {registry: {}}}) + b"\n")
      os.chmod(config / "config.json", 0o600)
      # Export only the selected context; never inherit credential helpers or all auths.
      archive = config / "context.dockercontext"
      # Context export is binary and may contain client TLS material; keep it private.
      if context != "default":
        with archive.open("wb") as output:
          process = subprocess.run(["docker", "context", "export", context, "-"], cwd=self.root,
                                   env=original, stdout=output, stderr=subprocess.PIPE, timeout=60)
        require(process.returncode == 0, "Cannot export selected Docker context")
      plugins = Path(original.get("DOCKER_CONFIG", str(Path.home() / ".docker"))) / "cli-plugins"
      if plugins.is_dir():
        (config / "cli-plugins").symlink_to(plugins.resolve(), target_is_directory=True)
      contexts = plugins.parent / "contexts"
      if contexts.is_dir():
        # Builder nodes can refer to named contexts other than the active one. Connection
        # metadata/TLS files are separate from registry auths and stay in the private temp tree.
        shutil.copytree(contexts, config / "contexts")
      self.environment["DOCKER_CONFIG"] = temporary
      self.environment["BUILDX_CONFIG"] = original.get(
        "BUILDX_CONFIG", str(Path(original.get("DOCKER_CONFIG", str(Path.home() / ".docker"))) / "buildx"))
      try:
        if context != "default" and not contexts.is_dir():
          self.run(["docker", "context", "import", context, str(archive)])
        if context != "default" or "DOCKER_CONTEXT" in original:
          self.environment["DOCKER_CONTEXT"] = context
          archive.unlink(missing_ok=True)
        self.run(["docker", "login", registry, "--username", username, "--password-stdin"], input_text=token)
        yield
      finally:
        self.environment = original


class NoRedirect(HTTPRedirectHandler):
  def redirect_request(self, request, fp, code, message, headers, new_url):
    return None


class HTTP:
  def __init__(self, origin, test_http=False):
    self.origin = endpoint(origin, test_http)
    self.opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))

  def request(self, method, path, headers=None, body=None, allowed=(200,)):
    require(path.startswith("/") and not path.startswith("//"), "Expected same-origin request path")
    request = Request(self.origin + path, data=body, headers=headers or {}, method=method)
    try:
      with self.opener.open(request, timeout=60) as response:
        data = response.read(64 * 1024 * 1024 + 1)
        require(len(data) <= 64 * 1024 * 1024, "API response exceeds safety bound")
        status, response_headers = response.status, response.headers
    except HTTPError as exc:
      status, response_headers, data = exc.code, exc.headers, b""
    except (URLError, OSError) as exc:
      raise ReleaseError("HTTPS operation failed; verify trust and connectivity") from exc
    require(status in allowed, f"Remote operation failed with HTTP {status}; no response body logged")
    return status, response_headers, data


def json_response(data):
  try:
    return json.loads(data)
  except (ValueError, UnicodeError) as exc:
    raise ReleaseError("Malformed remote JSON") from exc


class Gitea:
  def __init__(self, config, token):
    self.http = HTTP(config["gitea"], config.get("test_http", False))
    self.repository = config["repository"]
    self.owner, self.repo = self.repository.split("/")
    self.base = "/api/v1/repos/" + "/".join(quote(x, safe="") for x in (self.owner, self.repo))
    self.headers = {"Authorization": "token " + token, "Content-Type": "application/json"}

  def get(self, path, absent=False):
    """Only an allowed 404 is absent; optional lookups otherwise require objects."""
    status, _, data = self.http.request("GET", path, self.headers, allowed=(200, 404) if absent else (200,))
    if status == 404:
      return None
    value = json_response(data)
    require(value is not None, "Expected non-null Gitea JSON response")
    require(not absent or isinstance(value, dict), "Expected Gitea lookup object")
    return value

  def pages(self, path, query=None):
    result, fingerprints = [], set()
    for page in range(1, 10001):
      values = self.get(path + "?" + urlencode((query or {}) | {"page": page, "limit": 100}))
      require(isinstance(values, list), "Expected paginated array")
      if not values:
        return result
      fingerprint = digest(canonical(values))
      require(fingerprint not in fingerprints, "Pagination did not advance")
      fingerprints.add(fingerprint)
      result.extend(values)
    raise ReleaseError("Pagination safety bound exceeded")

  def releases(self):
    return self.pages(self.base + "/releases")

  def release(self, tag):
    release = self.get(self.base + "/releases/tags/" + quote(tag, safe=""), absent=True)
    require(release is None or isinstance(release, dict), "Expected Gitea release object")
    return release

  def publish(self, tag, commit, body):
    payload = {"tag_name": tag, "target_commitish": commit, "name": tag,
               "body": body, "draft": False, "prerelease": False}
    self.http.request("POST", self.base + "/releases", self.headers, canonical(payload), allowed=(201,))

  def packages(self):
    return self.pages("/api/v1/packages/" + quote(self.owner, safe=""), {"type": "container"})

  def package_path(self, name, package_version):
    return "/api/v1/packages/" + "/".join(quote(x, safe="") for x in
      (self.owner, "container", name, package_version))

  def delete_package(self, name, package_version):
    self.http.request("DELETE", self.package_path(name, package_version), self.headers, allowed=(204, 404))

  def delete_release(self, release_id):
    require(isinstance(release_id, int), "Invalid release ID")
    self.http.request("DELETE", self.base + f"/releases/{release_id}", self.headers, allowed=(204, 404))


class Registry:
  ACCEPT = ", ".join(("application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"))

  def __init__(self, config, username, token):
    self.http = HTTP(config["gitea"], config.get("test_http", False))
    self.owner = config["repository"].split("/")[0]
    self.basic = "Basic " + base64.b64encode((username + ":" + token).encode()).decode()
    self.bearer = {}

  def request(self, name, kind, reference, absent=False):
    repository = self.owner + "/" + name
    path = "/v2/" + "/".join(quote(x, safe="") for x in (self.owner, name)) + "/" + kind + "/" + quote(reference, safe="")
    headers = {"Accept": self.ACCEPT, "Authorization": self.bearer.get(repository, self.basic)}
    status, response_headers, data = self.http.request("GET", path, headers, allowed=(200, 401, 404))
    if status == 401:
      challenge = response_headers.get("WWW-Authenticate", "")
      require(challenge.lower().startswith("bearer "), "Unsupported registry authentication challenge")
      fields = dict(re.findall(r'([a-z]+)="([^"\r\n]*)"', challenge))
      realm = urlsplit(fields.get("realm", ""))
      origin = urlsplit(self.http.origin)
      require((realm.scheme, realm.netloc) == (origin.scheme, origin.netloc) and
              not realm.username and not realm.password and not realm.fragment,
              "Registry token realm must be same-origin")
      require(realm.path.startswith("/") and not realm.path.startswith("//"), "Invalid token realm path")
      query = urlencode({"service": fields.get("service", ""), "scope": f"repository:{repository}:pull"})
      token_path = realm.path + "?" + (realm.query + "&" if realm.query else "") + query
      _, _, token_data = self.http.request("GET", token_path, {"Authorization": self.basic})
      token = json_response(token_data)
      value = token.get("token") or token.get("access_token")
      require(isinstance(value, str) and value, "Registry token response is invalid")
      self.bearer[repository] = "Bearer " + value
      headers["Authorization"] = self.bearer[repository]
      status, response_headers, data = self.http.request("GET", path, headers, allowed=(200, 404))
    if status == 404:
      require(absent, "Required registry content is absent")
      return None
    actual = digest(data)
    if reference.startswith("sha256:"):
      require(actual == reference, "Registry content digest mismatch")
    declared = response_headers.get("Docker-Content-Digest")
    require(declared is None or declared == actual, "Registry digest header mismatch")
    return actual, json_response(data)

  def resolve(self, name, reference):
    record = self.request(name, "manifests", reference, absent=True)
    return None if record is None else record[0]

  def graph(self, name, root):
    nodes, edges = {}, 0

    def visit(descriptor, kind, parent=None, depth=0):
      nonlocal edges
      require(isinstance(descriptor, dict), "Invalid manifest descriptor")
      reference = immutable(descriptor.get("digest"))
      require(isinstance(descriptor.get("annotations", {}), dict), "Invalid descriptor annotations")
      edges += 1
      require(depth < 32 and edges <= 10000, "Manifest graph exceeds safety bound")
      incoming = {"kind": kind, "parent": parent, "descriptor": descriptor}
      if reference in nodes:
        nodes[reference]["incoming"].append(incoming)
        return
      require(len(nodes) < 1000, "Manifest graph exceeds safety bound")
      actual, manifest = self.request(name, "manifests", reference)
      require(isinstance(manifest, dict), "Invalid manifest object")
      node = {"digest": actual, "manifest": manifest, "configuration": None, "incoming": [incoming]}
      nodes[actual] = node
      if "manifests" in manifest:
        require(isinstance(manifest["manifests"], list), "Invalid manifest index")
        references = [immutable(item.get("digest")) if isinstance(item, dict) else immutable(None)
                      for item in manifest["manifests"]]
        require(len(references) == len(set(references)), "Duplicate manifest descriptor")
        for descriptor in manifest["manifests"]:
          visit(descriptor, "member", actual, depth + 1)
      elif "config" in manifest:
        require(isinstance(manifest["config"], dict), "Invalid configuration descriptor")
        configuration_digest = immutable(manifest["config"].get("digest"))
        _, configuration = self.request(name, "blobs", configuration_digest)
        require(isinstance(configuration, dict), "Invalid configuration object")
        node["configuration"] = configuration
      else:
        require("artifactType" in manifest, "Unrecognized OCI manifest")
      if "subject" in manifest:
        visit(manifest["subject"], "subject", actual, depth + 1)

    visit({"digest": root}, "root")
    return set(nodes), {"root": root, "nodes": nodes}

  def verify(self, name, root, platforms, commit, release_version, source):
    graph, evidence = self.graph(name, root)
    configurations = runnable(evidence)
    actual = [item["os"] + "/" + item["architecture"] for item in configurations]
    require(sorted(actual) == sorted(platforms), "Published platforms differ from required platforms")
    for configuration in configurations:
      labels = configuration.get("config", {}).get("Labels", {})
      require(labels.get("org.opencontainers.image.revision") == commit and
              labels.get("org.opencontainers.image.version") == release_version and
              labels.get("org.opencontainers.image.source") == source,
              "Published image source/version labels differ")
    return graph


def preflight(runner, images):
  runner.run(["docker", "buildx", "version"])
  output = runner.run(["docker", "buildx", "inspect", "--bootstrap"])
  advertised = set()
  builder = "unknown"
  for line in output.splitlines():
    if line.startswith("Name:") and builder == "unknown":
      builder = line.split(":", 1)[1].strip()
    if line.strip().startswith("Platforms:"):
      advertised.update(x.strip().rstrip("*") for x in line.split(":", 1)[1].split(","))
  required = {platform for image in images for platform in image["platforms"]}
  require(required <= advertised, f"Builder {builder}: advertised {sorted(advertised)}, required {sorted(required)}")


def git_identity(runner, config):
  require(runner.run(["git", "branch", "--show-current"]).strip() == "main", "Release requires clean main")
  require(not runner.run(["git", "status", "--porcelain", "--untracked-files=all"]).strip(), "Release requires a clean checkout")
  commit = runner.run(["git", "rev-parse", "HEAD"]).strip()
  expected = urlsplit(config["gitea"]).netloc
  for mode in (["--push", "--all"], ["--all"]):
    remote = runner.run(["git", "remote", "get-url", *mode, "origin"]).splitlines()
    require(len(remote) == 1, "Origin must have one fetch and one push destination")
    address = remote[0]
    if address.startswith(("https://", "ssh://")):
      parsed = urlsplit(address)
      require(not parsed.password and not parsed.query and not parsed.fragment,
              "Git URL must not contain credentials, query, or fragment")
      authority = parsed.netloc.rsplit("@", 1)[-1]
      if parsed.scheme == "ssh":
        require(parsed.username in (None, "git"), "Unexpected SSH identity")
        authority = expected if parsed.hostname == urlsplit(config["gitea"]).hostname else parsed.hostname
      else:
        require(not parsed.username, "HTTPS Git credentials must not appear in remote URL")
      path = parsed.path.strip("/").removesuffix(".git")
      require(authority == expected and path == config["repository"], "Git destination differs from configured Gitea repository")
    else:
      require(address == "git@" + urlsplit(config["gitea"]).hostname + ":" + config["repository"] + ".git", "Unsupported Git destination")
  return commit
