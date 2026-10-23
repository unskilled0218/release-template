#!/usr/bin/env python3
"""Install pinned shared code using a recoverable, destination-local transaction."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from release_template.core import ReleaseError, atomic_bytes, child, load, require, save, sync_directory
from launch import DestinationLock, verify


BOOTSTRAP = ("scripts/launch.py", "scripts/release.sh")


def checksum(data):
  return hashlib.sha256(data).hexdigest()


def source_inventory(source, revision):
  source = Path(source).resolve()
  require(isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision),
          "Pin an exact immutable 40-character commit, not a branch or tag")
  def git(*arguments):
    result = subprocess.run(["git", *arguments], cwd=source, capture_output=True, check=True)
    return result.stdout
  commit = git("rev-parse", "--verify", revision + "^{commit}").decode().strip()
  require(len(commit) == 40 and revision == commit, "Pin an exact immutable 40-character commit, not a branch or tag")
  require(not git("ls-tree", "--name-only", commit, "scripts/release-data.py").strip(),
          "Bash template revisions cannot be installed as a legacy Python inventory; copy/review the Bash template separately")
  paths = git("ls-tree", "-r", "--name-only", commit, "release_template", "scripts/launch.py", "scripts/release.sh", "VERSION").decode().splitlines()
  files, bootstrap = {}, {}
  template_version = None
  for path in paths:
    data = git("show", commit + ":" + path)
    if path.startswith("release_template/") and path.endswith(".py"):
      files["scripts/release-template/" + path] = data
    elif path in BOOTSTRAP:
      bootstrap[path] = data
    elif path == "VERSION":
      template_version = data.decode().strip()
  require(files and set(bootstrap) == set(BOOTSTRAP) and template_version, "Pinned source inventory is incomplete")
  from release_template.core import version
  version(template_version)
  lock = {"schema": 1, "bootstrap_protocol": 1, "revision": commit, "version": template_version,
          "files": {path: checksum(data) for path, data in files.items()},
          "bootstrap": {path: checksum(data) for path, data in bootstrap.items()}}
  return files, bootstrap, lock


def content(path):
  return path.read_bytes() if path.is_file() else None


def transaction(destination, files, bootstrap, lock, dry_run=False):
  root = Path(destination).resolve()
  require(not (root / ".template-transaction").exists(), "An update transaction already needs recovery")
  lock_path = child(root, "release-template.lock.json")
  if lock_path.exists():
    old = verify(root)
    require(old["bootstrap"] == lock["bootstrap"],
            "Bootstrap protocol/code changed; standalone bootstrap migration requires separate review")
  else:
    old = {"files": {}, "bootstrap": {}}
    require(not child(root, "scripts/release-template").exists(), "Initial managed destination must be absent")
    require(all(not child(root, path).exists() for path in BOOTSTRAP), "Initial launcher paths must be absent")
  desired = files | bootstrap | {"release-template.lock.json": (json.dumps(lock, sort_keys=True, separators=(",", ":")) + "\n").encode()}
  paths = sorted(set(old["files"]) | set(desired))
  paths.remove("release-template.lock.json")
  paths.append("release-template.lock.json")
  for path in paths:
    target = child(root, path)
    require(not target.exists() or target.is_file(), "Managed destination is not a regular file")
    if path not in old["files"] and path not in old["bootstrap"] and path != "release-template.lock.json":
      require(not target.exists(), "New managed file would overwrite untracked content")
  report = {"revision": lock["revision"], "replace": [p for p in paths if p in desired],
            "remove": [p for p in paths if p not in desired]}
  if dry_run:
    return report
  journal = {"schema": 1, "status": "preparing", "entries": []}
  workspace = child(root, ".template-transaction")
  workspace.mkdir(mode=0o700)
  sync_directory(root)
  for index, name in enumerate(paths):
    previous = content(child(root, name))
    updated = desired.get(name)
    entry = {"path": name, "before": None if previous is None else checksum(previous),
             "after": None if updated is None else checksum(updated), "index": index}
    journal["entries"].append(entry)
    if previous is not None:
      atomic_bytes(workspace / f"{index}.before", previous)
    if updated is not None:
      atomic_bytes(workspace / f"{index}.after", updated)
  journal["status"] = "applying"
  save(workspace / "journal.json", journal)
  recover(root, "complete")
  return report


def recover(destination, direction):
  root = Path(destination).resolve()
  workspace = child(root, ".template-transaction")
  journal_path = workspace / "journal.json"
  if not journal_path.exists():
    # A kill while preparing made no destination writes. Do not guess about unknown files.
    require(workspace.is_dir() and all(path.is_file() and not path.is_symlink() and
            (path.name.endswith(".before") or path.name.endswith(".after")) for path in workspace.iterdir()),
            "Unknown incomplete update preparation; manual inspection required")
    for path in workspace.iterdir():
      path.unlink()
    workspace.rmdir()
    sync_directory(root)
    return
  journal = load(journal_path)
  require(journal.get("schema") == 1 and journal.get("status") in ("applying", "complete", "restore"),
          "Unknown update journal")
  entries = journal["entries"]
  require(isinstance(entries, list) and len({item["path"] for item in entries}) == len(entries), "Invalid update inventory")
  # Validate the whole transaction and staged content before changing even one file.
  for entry in entries:
    name = entry["path"]
    require(name in BOOTSTRAP or name == "release-template.lock.json" or
            name.startswith("scripts/release-template/release_template/"), "Journal path is outside managed inventory")
    current = content(child(root, name))
    actual = None if current is None else checksum(current)
    require(actual in (entry["before"], entry["after"]), "User changes conflict with update recovery")
    selected = "after" if direction == "complete" else "before"
    if entry[selected] is not None and actual != entry[selected]:
      staged = child(workspace, f'{entry["index"]}.{selected}')
      require(checksum(staged.read_bytes()) == entry[selected], "Recovery staging checksum mismatch")
  # The lock record is last for both completion and restoration.
  for entry in entries:
    target = child(root, entry["path"])
    selected = "after" if direction == "complete" else "before"
    current = content(target)
    if (None if current is None else checksum(current)) == entry[selected]:
      continue
    if entry[selected] is None:
      if target.exists():
        target.unlink()
        sync_directory(target.parent)
    else:
      atomic_bytes(target, (workspace / f'{entry["index"]}.{selected}').read_bytes(),
                   0o755 if entry["path"] in BOOTSTRAP else 0o644)
  journal["status"] = direction
  if direction == "complete":
    # Verify without hiding the in-progress marker from a concurrent launcher.
    lock = load(root / "release-template.lock.json")
    for name, expected in lock["files"].items():
      require(checksum(child(root, name).read_bytes()) == expected, "Completed update verification failed")
  save(journal_path, journal)
  for path in list(workspace.iterdir()):
    require(path.is_file() and not path.is_symlink(), "Unexpected transaction content")
    path.unlink()
  workspace.rmdir()
  # Prune only empty directories left by managed removals or a restored initial install.
  managed = child(root, "scripts/release-template")
  if managed.exists():
    for path in sorted((p for p in managed.rglob("*") if p.is_dir()), reverse=True):
      if not any(path.iterdir()):
        path.rmdir()
    if not any(managed.iterdir()):
      managed.rmdir()
  sync_directory(root)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("destination", type=Path)
  parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent.parent)
  parser.add_argument("--revision")
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--verify", action="store_true")
  parser.add_argument("--recover", choices=("complete", "restore"))
  arguments = parser.parse_args()
  try:
    require(arguments.destination.is_dir(), "Destination must already exist")
    inventory = None
    if not arguments.verify and not arguments.recover:
      require(arguments.revision, "Select an immutable --revision")
      # Refuse an incompatible source before even creating a destination lock file.
      inventory = source_inventory(arguments.source, arguments.revision)
    with DestinationLock(arguments.destination):
      if arguments.verify:
        print(json.dumps(verify(arguments.destination.resolve()), sort_keys=True))
      elif arguments.recover:
        recover(arguments.destination, arguments.recover)
      else:
        files, bootstrap, lock = inventory
        print(json.dumps(transaction(arguments.destination, files, bootstrap, lock, arguments.dry_run), sort_keys=True))
    return 0
  except (ReleaseError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
    print("Template update refused: " + str(exc), file=sys.stderr)
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
