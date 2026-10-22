"""Validated identities, durable files, and side-effect-free policy."""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


class ReleaseError(Exception):
  """An unsafe or incomplete release operation."""


def require(condition, message):
  if not condition:
    raise ReleaseError(message)


def digest(data):
  return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(value):
  return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def version(value):
  require(isinstance(value, str), "Version must be a string")
  match = re.fullmatch(r"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value)
  require(match is not None, "Version must be MAJOR.MINOR.PATCH")
  return tuple(map(int, match.groups()))


def older(candidate, current):
  try:
    return version(candidate) < version(current)
  except ReleaseError:
    return False


def load(path):
  try:
    return json.loads(Path(path).read_text())
  except (OSError, ValueError) as exc:
    raise ReleaseError(f"Cannot read JSON file: {Path(path).name}") from exc


def sync_directory(path):
  descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
  try:
    os.fsync(descriptor)
  finally:
    os.close(descriptor)


def durable_directory(path):
  path = Path(path)
  if path.exists():
    require(path.is_dir(), "Expected a directory")
    return
  durable_directory(path.parent)
  path.mkdir()
  sync_directory(path.parent)
  sync_directory(path)


def atomic_bytes(path, data, mode=0o600):
  path = Path(path)
  durable_directory(path.parent)
  descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".write-")
  try:
    with os.fdopen(descriptor, "wb") as output:
      os.fchmod(output.fileno(), mode)
      output.write(data)
      output.flush()
      os.fsync(output.fileno())
    os.replace(temporary, path)
    sync_directory(path.parent)
  finally:
    if os.path.exists(temporary):
      os.unlink(temporary)


def save(path, value):
  atomic_bytes(path, canonical(value) + b"\n")


def child(root, name):
  require(isinstance(name, str) and name and not Path(name).is_absolute(), "Expected a relative path")
  path = Path(root) / name
  require(".." not in Path(name).parts, "Path traversal refused")
  require(path.resolve().is_relative_to(Path(root).resolve()), "Path escapes destination")
  current = path
  while current != Path(root):
    require(not current.is_symlink(), "Symlink destination refused")
    current = current.parent
  return path


def command(value):
  require(isinstance(value, list) and value and all(isinstance(x, str) and x for x in value),
          "Commands must be nonempty argument arrays")
  return value


def image_order(images):
  names = {image["name"] for image in images}
  require(len(names) == len(images), "Duplicate image name")
  result, visiting, visited = [], set(), set()
  by_name = {image["name"]: image for image in images}

  def visit(name):
    require(name in names, "Unknown image dependency")
    require(name not in visiting, "Image dependency cycle")
    if name in visited:
      return
    visiting.add(name)
    for dependency in by_name[name].get("dependencies", []):
      visit(dependency)
    visiting.remove(name)
    visited.add(name)
    result.append(by_name[name])

  for name in by_name:
    visit(name)
  return result


def promotion_allowed(current, predecessor, target, requested, published):
  """Only this recorded forward transition may own mutable aliases."""
  if published is not None:
    require(version(published["version"]) <= version(requested), "Stale release: newer publication exists")
    if version(published["version"]) == version(requested):
      require(published["targets"] == target, "Equal version has conflicting image identities")
  require(set(current) == set(predecessor), "Alias inventory changed")
  for name, value in current.items():
    require(value in (predecessor[name], target.get(name)), "Alias changed outside this release transition")
