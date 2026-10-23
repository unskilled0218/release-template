"""Pure publication metadata and retention eligibility rules."""

import json
import re
from pathlib import PurePosixPath

from .core import ReleaseError, canonical, older, require, version


MARKER = "\nRelease identity:\n"
TAG_MARKER = "Release-template identity 2\n"
MAX_NOTES = 65536


def normalize_notes(text):
  require(isinstance(text, str), "Release notes must be UTF-8 text")
  return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"


def notes_text(data, release_version):
  require(isinstance(data, bytes) and 0 < len(data) <= MAX_NOTES, "Release notes exceed size bound or are empty")
  try:
    text = normalize_notes(data.decode("utf-8"))
  except UnicodeError as exc:
    raise ReleaseError("Release notes must be UTF-8 text") from exc
  require(text.startswith("# Release v" + release_version + "\n"), "Release notes version heading differs")
  require(len(text.splitlines()) > 2 and "\x00" not in text, "Release notes need project-update content")
  return text


def validate_identity(value, tag):
  fields = {"schema", "version", "tag", "commit", "template", "repository", "targets", "platforms", "notes"}
  require(isinstance(value, dict) and set(value) == fields and type(value["schema"]) is int and
          value["schema"] == 2, "Unknown or malformed annotated release identity")
  version(value["version"])
  require(value["tag"] == tag == "v" + value["version"], "Release version identity differs")
  for field in ("commit", "template"):
    require(isinstance(value[field], str) and re.fullmatch(r"[0-9a-f]{40}", value[field]), "Invalid release revision")
  require(isinstance(value["repository"], str) and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value["repository"]),
          "Invalid release repository")
  targets, platforms = value["targets"], value["platforms"]
  require(isinstance(targets, dict) and targets and isinstance(platforms, dict) and platforms, "Invalid image coverage")
  expected = set()
  for name, items in platforms.items():
    require(isinstance(name, str) and re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", name) and isinstance(items, list) and items and
            all(item in ("linux/amd64", "linux/arm64") for item in items) and len(set(items)) == len(items),
            "Invalid image platform coverage")
    expected.add(name + ":latest")
  require(expected <= set(targets) <= expected | {name + ":" + tag for name in platforms}, "Invalid alias coverage")
  for alias, reference in targets.items():
    require(isinstance(reference, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", reference), "Invalid image digest")
    require(reference == targets[alias.split(":", 1)[0] + ":latest"], "Contradictory image digests")
  notes = value["notes"]
  require(isinstance(notes, dict) and set(notes) == {"path", "digest"}, "Invalid notes binding")
  path = notes["path"]
  require(isinstance(path, str) and path and not PurePosixPath(path).is_absolute() and
          ".." not in PurePosixPath(path).parts and "\x00" not in path, "Invalid notes path")
  require(isinstance(notes["digest"], str) and re.fullmatch(r"sha256:[0-9a-f]{64}", notes["digest"]), "Invalid notes digest")
  return value


def annotation(identity):
  validate_identity(identity, identity["tag"])
  return TAG_MARKER + canonical(identity).decode() + "\n"


def tag_identity(message, tag):
  require(message.startswith(TAG_MARKER), "Annotated tag lacks recognized identity")
  def unique(pairs):
    result = {}
    for key, value in pairs:
      require(key not in result, "Duplicate annotated identity field")
      result[key] = value
    return result
  try:
    value = json.loads(message[len(TAG_MARKER):], object_pairs_hook=unique)
  except ValueError as exc:
    raise ReleaseError("Malformed annotated release identity") from exc
  validate_identity(value, tag)
  require(message == annotation(value), "Annotated identity is not canonical")
  return value


def description(identity):
  return "Container release " + identity["version"] + ". Images are published in Gitea Packages.\n" + MARKER + canonical(identity).decode()


def metadata(release):
  try:
    value = json.loads(release["body"].split(MARKER, 1)[1])
    require(isinstance(value, dict), "Unknown release metadata object")
    require(value.get("schema") == 1, "Unknown release metadata schema")
    version(value["version"])
    require(value["tag"] == "v" + value["version"] == release["tag_name"], "Release version identity differs")
    require(isinstance(value["commit"], str) and isinstance(value["targets"], dict), "Invalid release identity")
    return value
  except (KeyError, IndexError, TypeError, ValueError) as exc:
    raise ReleaseError("Published release lacks recognized identity metadata; explicit migration is required") from exc


def published(releases, resolve=metadata):
  candidates = []
  for release in releases:
    require(isinstance(release, dict), "Invalid release record")
    if release.get("draft") or release.get("prerelease"):
      continue
    try:
      parsed = version(release["tag_name"])
    except ReleaseError:
      # Unknown published identities cannot establish monotonic ownership safely.
      raise ReleaseError("Unrecognized published release identity; explicit migration is required")
    candidates.append((parsed, release))
  return None if not candidates else resolve(max(candidates, key=lambda item: item[0])[1])


def release_candidates(releases, current):
  return [{"kind": "release", "id": item["id"], "tag": item["tag_name"]}
          for item in releases if not item.get("draft") and not item.get("prerelease") and
          older(item.get("tag_name"), current)]


def owned_package(package, repository, names):
  return (package.get("type") == "container" and package.get("name") in names and
          isinstance(package.get("repository"), dict) and
          package["repository"].get("full_name") == repository and
          isinstance(package.get("version"), str))
