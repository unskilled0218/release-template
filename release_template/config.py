"""Explicit consumer configuration and private file credentials."""

import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

from .core import child, command, image_order, load, require, version


def endpoint(url, test_http=False):
  parsed = urlsplit(url)
  require(parsed.scheme == "https" or (
    test_http and parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")
  ), "Credential endpoints must use HTTPS (loopback HTTP is test-only)")
  require(parsed.hostname and not parsed.username and not parsed.password and
          not parsed.query and not parsed.fragment and parsed.path in ("", "/"),
          "Expected a credential-free origin without a path")
  return url.rstrip("/")


def validate(data, root):
  require(isinstance(data, dict) and data.get("schema") == 1, "Unknown configuration schema")
  endpoint(data.get("forgejo", ""), data.get("test_http", False))
  require(re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", data.get("repository", "")),
          "Repository must be explicit owner/name")
  require(re.fullmatch(r"[a-z0-9.-]+(?::[0-9]+)?", data.get("registry", "")), "Invalid registry authority")
  require(urlsplit(data["forgejo"]).netloc == data["registry"], "Forgejo and registry origins must match")
  require(isinstance(data.get("source_push", False), bool), "source_push must be boolean")
  source = data.get("version", {})
  require(source.get("kind") in ("package", "file", "explicit", "command"), "Unknown version source")
  if source["kind"] in ("package", "file"):
    child(root, source["path"])
  if source["kind"] == "command":
    command(source["command"])
  require(isinstance(data.get("checks", []), list), "checks must be an array")
  for check in data.get("checks", []):
    command(check)
  images = data.get("images")
  require(isinstance(images, list) and images, "At least one image is required")
  for image in images:
    require(re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", image.get("name", "")), "Invalid image name")
    platforms = image.get("platforms")
    require(isinstance(platforms, list) and platforms and len(set(platforms)) == len(platforms) and
            all(re.fullmatch(r"linux/(amd64|arm64)", x) for x in platforms), "Invalid required platforms")
    require(isinstance(image.get("dependencies", []), list), "dependencies must be an array")
    child(root, image.get("context", "."))
    child(root, image.get("dockerfile", "Dockerfile"))
    require(isinstance(image.get("retain_version", False), bool), "retain_version must be boolean")
    for hook in ("build", "verify"):
      if hook in image:
        command(image[hook])
    require(not image.get("dependencies") or "build" in image,
            "Dependent images require an explicit build adapter consuming pinned dependencies")
    for secret in image.get("secrets", []):
      require(re.fullmatch(r"[a-zA-Z0-9_-]+", secret["id"]), "Invalid BuildKit secret ID")
      require(isinstance(secret["file"], str) and secret["file"], "Secret file is required")
  image_order(images)
  return data


def read_version(config, root, runner, explicit=None):
  source = config["version"]
  kind = source["kind"]
  if kind == "explicit":
    result = explicit
  elif kind == "command":
    result = runner.run(source["command"]).strip()
  elif kind == "file":
    result = child(root, source["path"]).read_text().strip()
  else:
    package = child(root, source["path"])
    result = load(package)["version"]
    lock = load(package.with_name("package-lock.json"))
    require(lock.get("version") == result and lock.get("packages", {}).get("", {}).get("version") == result,
            "Package and lockfile versions differ")
  version(result)
  normalized = result.removeprefix("v")
  require(explicit is None or explicit.removeprefix("v") == normalized, "Explicit version differs from source")
  return normalized


def credentials(environment=None):
  environment = os.environ if environment is None else environment
  configured = environment.get("FORGEJO_TOKEN", "~/.config/forgejo/forgejo-token")
  require(bool(configured), "FORGEJO_TOKEN must select a nonempty token-file path")
  home = environment.get("HOME", str(Path.home()))
  require(not configured.startswith("~") or configured == "~" or configured.startswith("~/"),
          "Only the current user's home expansion is supported")
  path = Path(home + configured[1:] if configured.startswith("~") else configured)
  try:
    metadata = path.stat()
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.getuid() and
            metadata.st_mode & 0o077 == 0 and metadata.st_mode & 0o400,
            "Token file must be user-owned, readable, and private (mode 600 or 400)")
    token = path.read_text().strip()
  except OSError as exc:
    from .core import ReleaseError
    raise ReleaseError("Cannot read protected token file") from exc
  require(token and not any(character.isspace() for character in token), "Token file is empty or malformed")
  username = environment.get("FORGEJO_USERNAME") or environment.get("FORGEJO_USER")
  require(username and re.fullmatch(r"[a-zA-Z0-9_.-]+", username), "Set FORGEJO_USERNAME to the token owner's login")
  require(not (environment.get("FORGEJO_USERNAME") and environment.get("FORGEJO_USER")) or
          environment["FORGEJO_USERNAME"] == environment["FORGEJO_USER"], "Conflicting Forgejo login variables")
  return username, token
