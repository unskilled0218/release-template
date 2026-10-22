#!/usr/bin/env python3
"""Stable bootstrap: lock and verify managed code before importing it (protocol 1)."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys


def inventory_path(root, name):
  path = root / name
  if Path(name).is_absolute() or ".." in Path(name).parts or not path.resolve().is_relative_to(root.resolve()):
    raise RuntimeError("Managed inventory path escapes destination")
  current = path
  while current != root:
    if current.is_symlink():
      raise RuntimeError("Managed inventory contains symlinks")
    current = current.parent
  return path


def verify(root):
  if (root / ".template-transaction").exists():
    raise RuntimeError("Incomplete template update; recover with the standalone updater before releasing")
  record = json.loads((root / "release-template.lock.json").read_text())
  if record.get("schema") != 1 or record.get("bootstrap_protocol") != 1:
    raise RuntimeError("Unsupported template lock/bootstrap protocol")
  if not record.get("files") or not record.get("revision"):
    raise RuntimeError("Incomplete template lock")
  for name, expected in record["files"].items():
    path = inventory_path(root, name)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
      raise RuntimeError("Managed template file differs from pinned inventory: " + name)
  for name, expected in record["bootstrap"].items():
    if hashlib.sha256(inventory_path(root, name).read_bytes()).hexdigest() != expected:
      raise RuntimeError("Stable launcher differs from installed bootstrap")
  managed = root / "scripts/release-template"
  actual_files = {str(path.relative_to(root)) for path in managed.rglob("*") if path.is_file()}
  if actual_files != set(record["files"]):
    raise RuntimeError("Managed inventory has missing or unexpected files")
  return record


class DestinationLock:
  def __init__(self, root):
    self.root = Path(root).resolve()
    self.file = None

  def __enter__(self):
    path = inventory_path(self.root, ".template-operation.lock")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    self.file = os.fdopen(descriptor, "a+")
    try:
      fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
      self.file.close()
      raise RuntimeError("Another update or release holds this destination lock") from None
    return self

  def __exit__(self, *_):
    self.file.close()


def main():
  root = Path(__file__).resolve().parent.parent
  try:
    with DestinationLock(root):
      if (root / "release-template.lock.json").exists() or (root / "scripts/release-template").exists():
        record = verify(root)
        source = root / "scripts/release-template"
        revision = record["revision"]
      else:
        if not (root / "release_template/cli.py").is_file() or (root / ".template-transaction").exists():
          raise RuntimeError("No verified template installation")
        source = root
        revision = None
      sys.dont_write_bytecode = True
      sys.path.insert(0, str(source))
      from release_template.cli import main as release_main
      return release_main(root, revision)
  except (OSError, ValueError, RuntimeError) as exc:
    print("Template bootstrap refused: " + str(exc), file=sys.stderr)
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
