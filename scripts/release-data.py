#!/usr/bin/env python3
"""Standard-library data and I/O helpers for the Bash release sequence; no legacy imports."""

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
from urllib.parse import quote, urlencode, urlsplit


API_LIMIT = 4194304
CONFIG_LIMIT = 1048576
ANNOTATION_LIMIT = 65536
REF_LIMIT = 16777216
INVENTORY_LIMIT = 67108864
PAGE_LIMIT = 1002
ITEM_LIMIT = 100000
READ_SECONDS = 60
MARKER = "container-release-bash/1\n"
PLATFORMS = ["linux/amd64", "linux/arm64"]


class Refusal(Exception):
  pass


class CommandFailed(Refusal):
  pass


class SetupRefusal(Refusal):
  def __init__(self, phase, message, advice):
    super().__init__(message)
    self.phase = phase
    self.advice = advice


def require(value, message):
  if not value:
    raise Refusal(message)


def canonical(value):
  return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha(data):
  return "sha256:" + hashlib.sha256(data).hexdigest()


def unique(pairs):
  result = {}
  for key, value in pairs:
    require(key not in result, "Duplicate JSON field")
    result[key] = value
  return result


def decode(data):
  return json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                    parse_constant=lambda _: (_ for _ in ()).throw(Refusal("Invalid JSON number")))


def read(path, limit=API_LIMIT):
  with Path(path).open("rb") as source:
    data = source.read(limit + 1)
  require(len(data) <= limit, "Input exceeds byte limit")
  return data


def document(path, limit=API_LIMIT):
  return decode(read(path, limit))


def write(path, value):
  Path(path).write_bytes(canonical(value) + b"\n")


def version(value):
  require(isinstance(value, str) and re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value),
          "Version must be MAJOR.MINOR.PATCH")
  return tuple(map(int, value.split(".")))


def digest(value):
  return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def path_text(value):
  require(isinstance(value, str) and value and not PurePosixPath(value).is_absolute() and
          ".." not in PurePosixPath(value).parts and not re.search(r"[\x00-\x1f\x7f]", value), "Unsafe relative path")
  return value


def regular(root, name):
  path_text(name)
  path = Path(root) / name
  require(path.resolve().is_relative_to(Path(root).resolve()), "Path escapes project")
  require(all(not p.is_symlink() for p in [path, *path.parents] if p != Path(root).parent), "Symlink input refused")
  require(path.is_file(), "Required regular file is missing")
  return path


def settings(root):
  root = Path(root)
  config = document(regular(root, "scripts/release.json"), ANNOTATION_LIMIT)
  fields = {"schema", "gitea", "repository", "image", "username", "token_file", "notes", "platforms"}
  require(isinstance(config, dict) and set(config) == fields and type(config["schema"]) is int and config["schema"] == 1,
          "Invalid Bash release configuration")
  require(all(isinstance(config[k], str) and config[k] and not re.search(r"[\x00-\x1f\x7f]", config[k])
              for k in fields - {"schema", "platforms"}), "Invalid configuration string")
  origin = urlsplit(config["gitea"])
  require(origin.scheme == "https" and origin.hostname and not origin.username and not origin.password and
          origin.path in ("", "/") and not origin.query and not origin.fragment and
          re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]+)?/?", config["gitea"]), "Expected credential-free HTTPS origin")
  name = r"[a-z0-9][a-z0-9._-]*"
  require(re.fullmatch(name + "/" + name, config["repository"]), "Invalid repository")
  owner = config["repository"].split("/")[0]
  require(re.fullmatch(re.escape(origin.netloc + "/" + owner + "/") + name, config["image"]), "Image scope differs")
  require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", config["username"]), "Invalid login")
  require(config["platforms"] == PLATFORMS, "Require linux/amd64 and linux/arm64 in that order")
  regular(root, config["notes"])
  regular(root, "Dockerfile")
  regular(root, ".dockerignore")
  release_version = read(regular(root, "VERSION"), 128).decode().strip()
  version(release_version)
  require(len(release_version) <= 16, "Version exceeds supported registry-tag length")
  script_hash = sha(b"".join(name.encode() + b"\x00" + read(regular(root, "scripts/" + name)) for name in
                             ("release.sh", "release-common.sh", "release-data.py")))
  return config | {"gitea": config["gitea"].rstrip("/"), "version": release_version, "tag": "v" + release_version,
                   "config_hash": sha(read(root / "scripts/release.json", ANNOTATION_LIMIT)), "script_hash": script_hash}


def capture(arguments, limit=REF_LIMIT, seconds=READ_SECONDS, input_data=None, streams=None):
  """Drain bounded pipes concurrently; terminate the whole owned process group on failure."""
  extra = streams or {}
  pipes, readers, limits = {}, {}, {}
  for name, cap in extra.items():
    reader, writer = os.pipe()
    pipes[name] = (reader, writer)
    readers[name], limits[name] = reader, cap
  arguments = [str(a).replace("{body}", f"/dev/fd/{pipes['body'][1]}")
               .replace("{headers}", f"/dev/fd/{pipes['headers'][1]}") if pipes else str(a) for a in arguments]
  process = None
  selector = selectors.DefaultSelector()
  try:
    environment = {k: v for k, v in os.environ.items() if k not in
                   ("GIT_TOKEN", "GIT_USERNAME", "FORGEJO_TOKEN", "FORGEJO_USER", "GITEA_TOKEN", "GITEA_USERNAME")}
    process = subprocess.Popen(arguments, stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                               env=environment, pass_fds=tuple(w for _, w in pipes.values()))
    for _, writer in pipes.values():
      os.close(writer)
    readers |= {"stdout": process.stdout.fileno(), "stderr": process.stderr.fileno()}
    limits |= {"stdout": limit, "stderr": CONFIG_LIMIT}
    buffers = {name: bytearray() for name in readers}
    for name, reader in readers.items():
      os.set_blocking(reader, False)
      selector.register(reader, selectors.EVENT_READ, name)
    pending_input = memoryview(input_data or b"")
    if input_data is not None:
      os.set_blocking(process.stdin.fileno(), False)
      selector.register(process.stdin.fileno(), selectors.EVENT_WRITE, "stdin")
    deadline = time.monotonic() + seconds
    while selector.get_map():
      if time.monotonic() >= deadline:
        raise CommandFailed("Command timed out")
      for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
        name = key.data
        if name == "stdin":
          if pending_input:
            try:
              count = os.write(key.fd, pending_input[:65536])
              pending_input = pending_input[count:]
            except BrokenPipeError:
              pending_input = memoryview(b"")
          if not pending_input:
            selector.unregister(key.fd)
            process.stdin.close()
          continue
        chunk = os.read(key.fd, min(65536, limits[name] + 1 - len(buffers[name])))
        if not chunk:
          selector.unregister(key.fd)
          continue
        buffers[name].extend(chunk)
        require(len(buffers[name]) <= limits[name], "Command output exceeds byte limit")
    remaining = max(0.001, deadline - time.monotonic())
    status = process.wait(timeout=remaining)
    return status, {key: bytes(value) for key, value in buffers.items()}
  finally:
    selector.close()
    if process is not None:
      try:
        os.killpg(process.pid, signal.SIGKILL)
      except ProcessLookupError:
        pass
      process.wait()
      for pipe in (process.stdout, process.stderr, process.stdin):
        if pipe is not None:
          pipe.close()
    for reader, writer in pipes.values():
      for descriptor in (reader, writer):
        try:
          os.close(descriptor)
        except OSError:
          pass


def command(arguments, limit=REF_LIMIT, seconds=READ_SECONDS, input_data=None):
  status, output = capture(arguments, limit, seconds, input_data)
  if status != 0:
    raise CommandFailed("Command failed: " + Path(arguments[0]).name)
  return output["stdout"]


def git(root, *args, limit=REF_LIMIT, input_data=None):
  return command(["git", "-C", str(root), *args], limit=limit, input_data=input_data)


def remote_key(value):
  value = value.strip()
  if re.fullmatch(r"[^/@:]+@[^/:]+:[^\s]+", value):
    host, repository = value.split("@", 1)[1].split(":", 1)
  else:
    parts = urlsplit(value)
    require(parts.scheme in ("https", "ssh") and parts.hostname and not parts.password and
            not parts.query and not parts.fragment and (parts.scheme != "https" or not parts.username), "Invalid Git destination")
    host, repository = parts.hostname, parts.path.lstrip("/")
    if parts.scheme == "https" and parts.port not in (None, 443):
      host += ":" + str(parts.port)
  return host.lower(), repository.removesuffix(".git")


def source(root, expected=None, remote=True):
  config = settings(root)
  require(git(root, "branch", "--show-current").strip() == b"main", "Release requires main")
  require(not git(root, "status", "--porcelain", "--untracked-files=all"), "Release requires a clean checkout")
  for ignored in (".template-operation.lock", ".release-template/probe"):
    git(root, "check-ignore", "--quiet", ignored)
  origin = urlsplit(config["gitea"])
  for arguments in (("remote", "get-url", "origin"), ("remote", "get-url", "--push", "--all", "origin")):
    destinations = git(root, *arguments).decode().removesuffix("\n").split("\n")
    require(len(destinations) == 1 and destinations[0] and not re.search(r"[\x00-\x20\x7f]", destinations[0]),
            "Require one valid effective Git destination")
    destination = destinations[0]
    ssh = destination.startswith("ssh://") or re.fullmatch(r"[^/@:]+@[^/:]+:[^\s]+", destination)
    host = origin.hostname.lower()
    if not ssh and origin.port not in (None, 443):
      host += ":" + str(origin.port)
    require(remote_key(destination) == (host, config["repository"]), "Git destination differs")
  commit = git(root, "rev-parse", "HEAD").decode().strip()
  require(re.fullmatch(r"[0-9a-f]{40}", commit) and (expected is None or expected == commit), "Captured source changed")
  if remote:
    values = git(root, "ls-remote", "origin", "refs/heads/main").decode().split()
    require(values == [commit, "refs/heads/main"], "Remote main differs; push source separately")
  return commit


def blob(root, commit, name):
  path_text(name)
  tree = git(root, "--literal-pathspecs", "ls-tree", "-z", commit, "--", name, limit=ANNOTATION_LIMIT)
  entries = tree.rstrip(b"\x00").split(b"\x00")
  require(len(entries) == 1 and b"\t" in entries[0], "Notes must be a regular committed blob")
  fields, filename = entries[0].split(b"\t", 1)
  mode, kind, oid = fields.decode().split()
  require(mode in ("100644", "100755") and kind == "blob" and filename.decode() == name, "Notes must be a regular committed blob")
  require(int(git(root, "cat-file", "-s", oid)) <= ANNOTATION_LIMIT, "Notes exceed byte limit")
  return git(root, "cat-file", "blob", oid, limit=ANNOTATION_LIMIT)


def notes(root, commit, config):
  text = blob(root, commit, config["notes"]).decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
  require(text.startswith("# Release " + config["tag"] + "\n") and len(text.splitlines()) > 2 and
          "\x00" not in text, "Invalid release notes heading/content")
  return text


def docker_plugin_dirs(original):
  path = original / "config.json"
  try:
    metadata = path.stat()
  except FileNotFoundError:
    config = {}
  else:
    require(stat.S_ISREG(metadata.st_mode), "Docker configuration must be regular")
    config = document(path, CONFIG_LIMIT)
  require(isinstance(config, dict), "Invalid Docker configuration")
  field = "cliPluginsExtraDirs"
  require(all(key == field or key.casefold() != field.casefold() for key in config),
          "Docker plugin discovery requires canonical cliPluginsExtraDirs spelling")
  directories = config.get(field)
  if directories is None:
    directories = []
  require(isinstance(directories, list) and all(isinstance(value, str) and value and
          not re.search(r"[\x00-\x1f\x7f]", value) for value in directories), "Invalid Docker plugin directories")
  return [os.path.abspath(value) for value in directories] + [str(original / "cli-plugins")]


def auth(root, work):
  config = settings(root)
  username = os.environ.get("GIT_USERNAME", config["username"])
  require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", username), "Invalid login")
  token_path = Path(os.environ.get("GIT_TOKEN", config["token_file"])).expanduser()
  if not token_path.is_absolute():
    token_path = Path(root) / token_path
  require(not token_path.resolve().is_relative_to(Path(root).resolve()), "Keep credentials outside the project")
  descriptor = os.open(token_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
  with os.fdopen(descriptor, "rb") as source_file:
    metadata = os.fstat(source_file.fileno())
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.getuid() and
            metadata.st_mode & 0o077 == 0 and metadata.st_mode & 0o400, "Token file must be owned, private, and regular")
    raw = source_file.read(4097)
  require(len(raw) <= 4096, "Token file exceeds size bound")
  token = raw.decode().strip()
  require(re.fullmatch(r"[A-Za-z0-9._~-]+", token), "Malformed token file")
  work = Path(work)
  (work / "token").write_text(token)
  (work / "login").write_text(username)
  (work / "api.curl").write_text('header = "Authorization: token ' + token + '"\n')
  basic = base64.b64encode((username + ":" + token).encode()).decode()
  (work / "registry.curl").write_text('header = "Authorization: Basic ' + basic + '"\n')
  original = Path(os.path.abspath(os.environ.get("DOCKER_CONFIG") or str(Path.home() / ".docker")))
  docker = work / "docker"
  docker.mkdir()
  write(docker / "config.json", {"auths": {urlsplit(config["gitea"]).netloc: {}},
                               "cliPluginsExtraDirs": docker_plugin_dirs(original)})
  if (original / "contexts").is_dir():
    shutil.copytree(original / "contexts", docker / "contexts")
  for path in work.iterdir():
    if path.is_file():
      path.chmod(0o600)


def http(work, method, url, auth_name="api.curl", payload=None, limit=API_LIMIT, seconds=READ_SECONDS):
  require(urlsplit(url).scheme == "https", "HTTPS is required")
  args = ["curl", "-q", "--silent", "--show-error", "--proto", "=https", "--max-time", str(seconds),
          "--config", str(Path(work) / auth_name), "--request", method,
          "--header", "Accept: application/json, application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json",
          "--dump-header", "{headers}", "--output", "{body}", "--write-out", "%{http_code}"]
  if payload is not None:
    args += ["--header", "Content-Type: application/json", "--data-binary", "@" + str(payload)]
  args += [url]
  status, output = capture(args, 16, seconds, streams={"body": limit, "headers": ANNOTATION_LIMIT})
  if status != 0:
    raise CommandFailed("HTTPS request failed; inspect trust/connectivity")
  require(re.fullmatch(b"[0-9]{3}", output["stdout"]), "Invalid HTTP status")
  code = int(output["stdout"])
  require(code in (200, 201, 401, 404), "Unexpected HTTP status " + str(code))
  headers = {}
  for line in output["headers"].decode("iso-8859-1").splitlines():
    if line.startswith("HTTP/"):
      headers = {}
    elif ":" in line:
      key, value = line.split(":", 1)
      key = key.lower().strip()
      require(key not in headers or key not in ("docker-content-digest", "www-authenticate"), "Duplicate HTTP evidence header")
      headers[key] = value.strip()
  return code, headers, output["body"]


def api_document(work, url):
  status, _, body = http(work, "GET", url)
  require(status == 200, "Package association evidence unavailable")
  return decode(body)


def repository_identity(record, repository):
  owner, name = repository.split("/")
  require(isinstance(record, dict) and type(record.get("id")) is int and record["id"] > 0 and
          record.get("full_name") == repository and record.get("name") == name and
          isinstance(record.get("owner"), dict) and record["owner"].get("login") == owner,
          "Package repository identity differs")
  return record["id"]


def package_routes(config):
  _, owner, name = config["image"].split("/")
  base = config["gitea"] + "/api/v1/"
  package = base + "packages/" + quote(owner, safe="") + "/container/" + quote(name, safe="")
  target = base + "repos/" + "/".join(quote(part, safe="") for part in config["repository"].split("/"))
  link = package + "/-/link/" + quote(config["repository"].split("/")[1], safe="")
  return target, package + "/latest", link


def package_linked(work, config, package_url, target_id):
  record = api_document(work, package_url)
  _, owner, name = config["image"].split("/")
  require(isinstance(record, dict) and type(record.get("id")) is int and record["id"] > 0 and
          isinstance(record.get("owner"), dict) and record["owner"].get("login") == owner and
          record.get("type") == "container" and record.get("name") == name and
          record.get("version") == "latest" and "repository" in record, "Package identity or association evidence differs")
  if record["repository"] is None:
    return False
  require(repository_identity(record["repository"], config["repository"]) == target_id,
          "Package is linked to a different repository; reassignment refused")
  return True


def package_association(work, config, ensure=False):
  """Only explicit unlinked evidence authorizes one POST, under operator writer exclusion."""
  target_url, package_url, link_url = package_routes(config)
  target_id = repository_identity(api_document(work, target_url), config["repository"])
  if package_linked(work, config, package_url, target_id):
    return
  require(ensure, "Package is not linked to the configured repository")
  # Gitea can hide inaccessible links as null. Only reviewed stable contracts
  # (1.25.x and exact 28.2.0) may rely on the server's existing-link refusal.
  server = api_document(work, config["gitea"] + "/api/v1/version")
  require(isinstance(server, dict) and isinstance(server.get("version"), str) and
          re.fullmatch(r"(?:1\.25\.(0|[1-9][0-9]*)|28\.2\.0)", server["version"]),
          "Package link writes require supported stable Gitea 1.25.x or exact 28.2.0; server association safety is unverified")
  # Refresh both identities immediately before mutation; never treat failed reads as permission.
  require(repository_identity(api_document(work, target_url), config["repository"]) == target_id,
          "Package target repository changed")
  if package_linked(work, config, package_url, target_id):
    return
  try:
    status, _, _ = http(work, "POST", link_url)
    require(status == 201, "Package association POST failed; inspect without rollback")
  except CommandFailed:
    # The server may have accepted the write. Reconcile once without repeating it.
    pass
  require(package_linked(work, config, package_url, target_id),
          "Package association incomplete or uncertain; inspect without rollback")


def registry(work, origin, image, kind, reference, missing=False):
  repository = image.split("/", 1)[1]
  route = "/v2/" + repository + "/" + kind + "/" + quote(reference, safe="")
  limit = API_LIMIT if kind == "manifests" else CONFIG_LIMIT
  status, headers, data = http(work, "GET", origin + route, "registry.curl", limit=limit)
  if status == 401:
    challenge = headers.get("www-authenticate", "")
    require(challenge.lower().startswith("bearer "), "Unsupported registry challenge")
    fields = dict(re.findall(r'([a-z]+)="([^"\r\n]*)"', challenge))
    realm = urlsplit(fields.get("realm", ""))
    base = urlsplit(origin)
    require((realm.scheme, realm.netloc) == (base.scheme, base.netloc) and not realm.username and
            not realm.password and not realm.fragment and realm.path.startswith("/") and not realm.path.startswith("//"),
            "Registry token realm must be same-origin")
    query = urlencode({"service": fields.get("service", ""), "scope": "repository:" + repository + ":pull"})
    url = origin + realm.path + "?" + (realm.query + "&" if realm.query else "") + query
    token_status, _, response = http(work, "GET", url, "registry.curl", limit=CONFIG_LIMIT)
    require(token_status == 200, "Registry authentication failed")
    token = decode(response)
    value = token.get("token", token.get("access_token")) if isinstance(token, dict) else None
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._~-]+", value), "Invalid registry token")
    (Path(work) / "bearer.curl").write_text('header = "Authorization: Bearer ' + value + '"\n')
    status, headers, data = http(work, "GET", origin + route, "bearer.curl", limit=limit)
  if status == 404 and missing:
    return None
  require(status == 200, "Registry evidence unavailable")
  actual = sha(data)
  require(not reference.startswith("sha256:") or actual == reference, "Registry object digest differs")
  advertised = headers.get("docker-content-digest")
  require(advertised is None or advertised == actual, "Registry digest header differs")
  return actual, decode(data)


def image(work, config, reference, commit, missing=False):
  result = registry(work, config["gitea"], config["image"], "manifests", reference, missing)
  if result is None:
    return ""
  root, index = result
  require(isinstance(index, dict) and index.get("schemaVersion") == 2 and
          index.get("mediaType") in ("application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json") and
          isinstance(index.get("manifests"), list) and len(index["manifests"]) == 2, "Expected two-platform image index")
  seen = set()
  for member in index["manifests"]:
    require(isinstance(member, dict) and digest(member.get("digest")) and isinstance(member.get("platform"), dict), "Invalid index member")
    platform = member["platform"].get("os", "") + "/" + member["platform"].get("architecture", "")
    require(platform in PLATFORMS and platform not in seen and not member["platform"].get("variant"), "Invalid image platforms")
    seen.add(platform)
    _, manifest = registry(work, config["gitea"], config["image"], "manifests", member["digest"])
    require(isinstance(manifest, dict) and manifest.get("schemaVersion") == 2 and
            isinstance(manifest.get("config"), dict) and digest(manifest["config"].get("digest")), "Invalid platform manifest")
    _, content = registry(work, config["gitea"], config["image"], "blobs", manifest["config"]["digest"])
    require(isinstance(content, dict) and content.get("os", "") + "/" + content.get("architecture", "") == platform,
            "Configuration platform differs")
    labels = content.get("config", {}).get("Labels", {})
    require(isinstance(labels, dict) and labels.get("org.opencontainers.image.revision") == commit and
            labels.get("org.opencontainers.image.version") == config["version"] and
            labels.get("org.opencontainers.image.source") == config["gitea"] + "/" + config["repository"], "Image labels differ")
  return root


def inventory(root, work, config):
  started = time.monotonic()
  pages = items = size = 0
  release = None
  for resource in ("releases", "tags"):
    fingerprints, identities = set(), set()
    for page in range(1, PAGE_LIMIT + 1):
      pages += 1
      remaining = 600 - (time.monotonic() - started)
      require(pages <= PAGE_LIMIT and remaining > 0, "Inventory budget exceeded")
      url = config["gitea"] + "/api/v1/repos/" + config["repository"] + "/" + resource + "?" + urlencode({"page": page, "limit": 100})
      status, _, data = http(work, "GET", url, seconds=min(READ_SECONDS, remaining))
      require(status == 200, "Inventory unavailable")
      size += len(data)
      require(size <= INVENTORY_LIMIT and time.monotonic() - started < 600, "Inventory budget exceeded")
      values = decode(data)
      require(isinstance(values, list) and len(values) <= 100, "Expected paginated array")
      items += len(values)
      require(items <= ITEM_LIMIT, "Inventory item limit exceeded")
      if not values:
        break
      fingerprint = sha(canonical(values))
      require(fingerprint not in fingerprints, "Pagination did not advance")
      fingerprints.add(fingerprint)
      for value in values:
        require(isinstance(value, dict), "Invalid inventory record")
        name = value.get("tag_name") if resource == "releases" else value.get("name")
        require(isinstance(name, str) and name not in identities, "Duplicate/invalid inventory identity")
        identities.add(name)
        if resource == "releases":
          require(type(value.get("draft")) is bool and type(value.get("prerelease")) is bool, "Invalid release state")
          if name == config["tag"]:
            release = value
          if not value["draft"] and not value["prerelease"]:
            require(name.startswith("v") and version(name[1:]) <= version(config["version"]), "Newer or unrecognized publication")
    else:
      raise Refusal("Inventory has no terminal page")
  remaining = 600 - (time.monotonic() - started)
  require(remaining > 0, "Inventory timed out")
  refs = command(["git", "-C", str(root), "ls-remote", "--tags", "origin"], REF_LIMIT, min(READ_SECONDS, remaining))
  size += len(refs)
  require(size <= INVENTORY_LIMIT and time.monotonic() - started < 600, "Inventory budget exceeded")
  advertised = {}
  for line in refs.decode().splitlines():
    fields = line.split()
    require(len(fields) == 2 and re.fullmatch(r"[0-9a-f]{40}", fields[0]) and fields[1].startswith("refs/tags/") and
            fields[1] not in advertised, "Malformed tag advertisement")
    advertised[fields[1]] = fields[0]
  items += len(advertised)
  require(items <= ITEM_LIMIT, "Inventory item limit exceeded")
  ref = "refs/tags/" + config["tag"]
  require(ref in advertised or ref + "^{}" not in advertised, "Missing direct tag advertisement")
  return {"release": release, "object": advertised.get(ref), "commit": advertised.get(ref + "^{}")}


def base_identity(root, commit, config):
  text = notes(root, commit, config)
  return {"format": "container-release-bash/1", "repository": config["repository"], "version": config["version"],
          "tag": config["tag"], "commit": commit, "config": config["config_hash"], "scripts": config["script_hash"],
          "image": config["image"], "platforms": PLATFORMS, "notes": {"path": config["notes"], "digest": sha(text.encode())}}


def tag_bytes(value):
  return ("object " + value["commit"] + "\ntype commit\ntag " + value["tag"] +
          "\ntagger Release template <release-template@localhost> 0 +0000\n\n" + MARKER).encode() + canonical(value) + b"\n"


def create_tag(root, value):
  oid = git(root, "mktag", input_data=tag_bytes(value)).decode().strip()
  require(re.fullmatch(r"[0-9a-f]{40}", oid), "Invalid tag object ID")
  local = git(root, "tag", "--list", value["tag"]).strip()
  if local:
    require(git(root, "rev-parse", "refs/tags/" + value["tag"]).decode().strip() == oid, "Local tag conflicts")
  return oid


def inspect_tag(root, commit, oid, config):
  require(re.fullmatch(r"[0-9a-f]{40}", oid), "Invalid advertised tag")
  require(git(root, "cat-file", "-t", oid).strip() == b"tag" and
          int(git(root, "cat-file", "-s", oid)) <= ANNOTATION_LIMIT, "Expected bounded annotated tag")
  raw = git(root, "cat-file", "tag", oid, limit=ANNOTATION_LIMIT)
  _, message = raw.split(b"\n\n", 1)
  require(message.startswith(MARKER.encode()), "Different tag identity format")
  value = decode(message[len(MARKER):])
  base = base_identity(root, commit, config)
  require(isinstance(value, dict) and set(value) == set(base) | {"digest", "predecessor"} and
          all(value[k] == v for k, v in base.items()) and digest(value["digest"]) and
          (value["predecessor"] is None or digest(value["predecessor"])), "Conflicting publication identity")
  require(raw == tag_bytes(value) and create_tag(root, value) == oid, "Different canonical tag bytes")
  return value


def release_check(record, root, commit, config):
  require(isinstance(record, dict) and record.get("tag_name") == config["tag"] and record.get("draft") is False and
          record.get("prerelease") is False and record.get("name") == config["tag"] and
          isinstance(record.get("body"), str), "Release identity/state differs")
  body = record["body"].replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
  require(body == notes(root, commit, config), "Release notes differ")


def snapshot(root, commit, destination):
  target = Path(destination)
  target.mkdir()
  archive_path = target.parent / "source.tar"
  # Source is local and captured; archive is not a network response or a Docker export.
  with archive_path.open("wb") as output:
    result = subprocess.run(["git", "-C", root, "archive", "--format=tar", commit], stdout=output,
                            stderr=subprocess.DEVNULL, timeout=60)
  require(result.returncode == 0, "Cannot export captured source")
  with tarfile.open(archive_path) as archive:
    for entry in archive:
      path_text(entry.name.rstrip("/"))
      path = target / entry.name
      require(path.resolve().is_relative_to(target.resolve()), "Source archive escapes snapshot")
      if entry.isdir():
        path.mkdir(parents=True, exist_ok=True)
      elif entry.isfile():
        path.parent.mkdir(parents=True, exist_ok=True)
        with archive.extractfile(entry) as source_file, path.open("wb") as output:
          shutil.copyfileobj(source_file, output)
        path.chmod(entry.mode & 0o777)
      elif entry.issym():
        require(not Path(entry.linkname).is_absolute() and
                (path.parent / entry.linkname).resolve().is_relative_to(target.resolve()), "Source symlink escapes snapshot")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(entry.linkname)
      else:
        raise Refusal("Unsupported source archive entry")
  archive_path.unlink()


def locked(root, script):
  advice = "Inspect or wait for the active checkout lock owner; check checkout permissions and filesystem lock support. Do not delete or bypass the lock."
  try:
    fd = os.open(Path(root) / ".template-operation.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
  except OSError:
    raise SetupRefusal("checkout locking", "Cannot open checkout lock", "Check checkout access, permissions, and a regular non-symlink lock file. Do not delete or bypass an active lock.") from None
  try:
    try:
      fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
      raise SetupRefusal("checkout locking", "Checkout lock is held", advice) from None
    except OSError:
      raise SetupRefusal("checkout locking", "Cannot acquire checkout lock", advice) from None
    environment = os.environ | {"RELEASE_LOCK_FD": str(fd)}
    try:
      child = subprocess.Popen(["bash", script], env=environment, pass_fds=(fd,), start_new_session=True)
    except OSError:
      raise SetupRefusal("locked child startup", "Cannot start locked release process", "Check Bash availability, process resources, and checkout access; retry only after the setup problem is resolved.") from None
    def forward(number, _frame):
      try:
        os.killpg(child.pid, number)
      except ProcessLookupError:
        pass
    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    return child.wait()
  finally:
    os.close(fd)


def dispatch(args):
  action, *args = args
  if action == "settings":
    write(args[1], settings(args[0]))
  elif action == "field":
    value = document(args[0])
    for key in args[1].split("."):
      value = value[key]
    print("" if value is None else value if isinstance(value, str) else canonical(value).decode())
  elif action == "source":
    print(source(args[0], args[1] if len(args) > 1 else None))
  elif action == "auth":
    auth(*args)
  elif action == "run":
    limit, seconds, output, *arguments = args
    Path(output).write_bytes(command(arguments, int(limit), float(seconds)))
  elif action == "run-input":
    limit, seconds, output, source_file, *arguments = args
    Path(output).write_bytes(command(arguments, int(limit), float(seconds), read(source_file, 4096)))
  elif action == "http":
    work, method, url, output, *payload = args
    status, _, data = http(work, method, url, payload=payload[0] if payload else None)
    require(status in (200, 201, 404), "Authentication failed")
    Path(output).write_bytes(data)
    print(status)
  elif action == "image":
    root, work, reference, commit, *missing = args
    print(image(work, settings(root), reference, commit, bool(missing)))
  elif action == "resolve":
    root, work, reference = args
    config = settings(root)
    result = registry(work, config["gitea"], config["image"], "manifests", reference, True)
    print(result[0] if result else "")
  elif action == "inventory":
    root, work, output = args
    write(output, inventory(root, work, settings(root)))
  elif action in ("package-check", "package-ensure"):
    root, work = args
    package_association(work, settings(root), ensure=action == "package-ensure")
  elif action == "make-tag":
    root, commit, reference, predecessor, output = args
    require(digest(reference) and (not predecessor or digest(predecessor)), "Invalid image digest")
    value = base_identity(root, commit, settings(root)) | {"digest": reference, "predecessor": predecessor or None}
    write(output, value)
    print(create_tag(root, value))
  elif action == "inspect-tag":
    root, commit, oid, output = args
    write(output, inspect_tag(root, commit, oid, settings(root)))
  elif action == "release-check":
    root, commit, record = args
    release_check(document(record), root, commit, settings(root))
  elif action == "payload":
    root, commit, output = args
    config = settings(root)
    write(output, {"tag_name": config["tag"], "target_commitish": commit, "name": config["tag"],
                   "body": notes(root, commit, config), "draft": False, "prerelease": False})
  elif action == "snapshot":
    snapshot(*args)
  elif action == "metadata":
    require(document(args[0]).get("containerimage.digest") == args[1], "Build metadata differs")
  elif action == "platforms":
    matches = re.findall(r"^\s*Platforms:\s*(.+)$", read(args[0]).decode(), re.MULTILINE)
    advertised = {value.strip().rstrip("*") for line in matches for value in line.split(",")}
    require(set(PLATFORMS) <= advertised, "Builder must advertise linux/amd64 and linux/arm64")
  elif action == "locked":
    return locked(*args)
  elif action == "lock-check":
    fd = int(os.environ["RELEASE_LOCK_FD"])
    path = Path(args[0]) / ".template-operation.lock"
    require(not path.is_symlink() and os.fstat(fd).st_ino == path.stat().st_ino and
            os.fstat(fd).st_dev == path.stat().st_dev, "Invalid inherited release lock")
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
  else:
    raise Refusal("Unknown data-helper action")
  return 0


if __name__ == "__main__":
  def interrupted(_number, _frame):
    raise Refusal("Operation interrupted")
  signal.signal(signal.SIGTERM, interrupted)
  signal.signal(signal.SIGINT, interrupted)
  try:
    require(sys.version_info >= (3, 11), "Python 3.11 or later is required")
    sys.exit(dispatch(sys.argv[1:]))
  except SetupRefusal as exc:
    print("Release stopped (" + exc.phase + "): " + str(exc), file=sys.stderr)
    print("Next: " + exc.advice, file=sys.stderr)
    print("No publication writes were sent by this invocation; existing remote state may still need inspection. Follow docs/bash-publication.md#retry-states before retrying.", file=sys.stderr)
    sys.exit(1)
  except (Refusal, OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError, subprocess.SubprocessError) as exc:
    # Never relay raw remote bodies, command stderr, config values, or credential paths.
    print("Release stopped: " + (str(exc) if isinstance(exc, Refusal) else "Invalid or unavailable input"), file=sys.stderr)
    sys.exit(2 if isinstance(exc, CommandFailed) else 1)
