"""Pure publication metadata and retention eligibility rules."""

import json

from .core import ReleaseError, canonical, older, require, version


MARKER = "\nRelease identity:\n"


def description(identity):
  return "Container release " + identity["version"] + ". Images are published in Forgejo Packages.\n" + MARKER + canonical(identity).decode()


def metadata(release):
  try:
    value = json.loads(release["body"].split(MARKER, 1)[1])
    require(value.get("schema") == 1, "Unknown release metadata schema")
    version(value["version"])
    require(value["tag"] == "v" + value["version"] == release["tag_name"], "Release version identity differs")
    require(isinstance(value["commit"], str) and isinstance(value["targets"], dict), "Invalid release identity")
    return value
  except (KeyError, IndexError, TypeError, ValueError) as exc:
    raise ReleaseError("Published release lacks recognized identity metadata; explicit migration is required") from exc


def published(releases):
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
  return None if not candidates else metadata(max(candidates, key=lambda item: item[0])[1])


def release_candidates(releases, current):
  return [{"kind": "release", "id": item["id"], "tag": item["tag_name"]}
          for item in releases if not item.get("draft") and not item.get("prerelease") and
          older(item.get("tag_name"), current)]


def owned_package(package, repository, names):
  return (package.get("type") == "container" and package.get("name") in names and
          isinstance(package.get("repository"), dict) and
          package["repository"].get("full_name") == repository and
          isinstance(package.get("version"), str))
