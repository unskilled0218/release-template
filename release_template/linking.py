"""Explicit whole-package association, gated by operator-established writer exclusion."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

from .config import server_version
from .core import ReleaseError, digest, canonical, require


def association(workflow, name, required_version=None):
  records = workflow.gitea.packages()
  require(isinstance(records, list) and all(isinstance(item, dict) for item in records), "Invalid package inventory")
  selected = [item for item in records if item.get("name") == name]
  require(selected, "Prepared package is missing from inventory")
  associations, versions = set(), set()
  for item in selected:
    reference = item.get("version")
    require(item.get("type") == "container" and isinstance(reference, str) and reference and reference not in versions,
            "Malformed or duplicate package evidence")
    versions.add(reference)
    scoped = workflow.gitea.get(workflow.gitea.package_path(name, reference), absent=True)
    for record in (item, scoped):
      require(isinstance(record, dict) and record.get("type") == "container" and record.get("name") == name and
              record.get("version") == reference and "repository" in record, "Package association evidence is uncertain")
      owner = record.get("owner")
      require(owner is None or isinstance(owner, dict) and owner.get("username", owner.get("login")) == workflow.gitea.owner,
              "Package owner differs")
      repository = record["repository"]
      require(repository is None or isinstance(repository, dict) and
              repository.get("full_name") == workflow.config["repository"], "Package is linked to a foreign repository")
      associations.add(None if repository is None else repository["full_name"])
  require(len(associations) == 1, "Package association views disagree")
  require(required_version is None or required_version in versions, "Prepared package version missing from inventory")
  return associations.pop()


def window(workflow, name, path, now=None):
  try:
    return read_window(workflow, name, path, now)
  except (OSError, ValueError, KeyError, TypeError) as exc:
    raise ReleaseError("Invalid or unavailable package-link window") from exc


def read_window(workflow, name, path, now=None):
  require(path is not None, "Package linking requires an operator-enforced --package-link-window")
  with Path(path).open("rb") as source:
    data = source.read(65537)
  require(len(data) <= 65536, "Package-link window exceeds size bound")
  def unique(pairs):
    result = {}
    for key, item in pairs:
      require(key not in result, "Duplicate package-link window field")
      result[key] = item
    return result
  value = json.loads(data, object_pairs_hook=unique)
  fields = {"schema", "origin", "server_version", "owner", "packages", "repository", "operator",
            "starts_at", "expires_at", "exclusion_procedure", "exclusion_confirmed"}
  require(isinstance(value, dict) and set(value) == fields and type(value["schema"]) is int and value["schema"] == 1,
          "Invalid package-link window")
  require(value["origin"] == workflow.config["gitea"].rstrip("/") and value["owner"] == workflow.gitea.owner and
          value["repository"] == workflow.config["repository"] and value["exclusion_confirmed"] is True,
          "Package-link window scope or exclusion differs")
  names = {image["name"] for image in workflow.config["images"]}
  require(isinstance(value["packages"], list) and value["packages"] and
          all(isinstance(item, str) for item in value["packages"]) and
          len(set(value["packages"])) == len(value["packages"]) and
          name in value["packages"] and set(value["packages"]) <= names, "Package-link window names differ")
  for field in ("operator", "exclusion_procedure"):
    require(isinstance(value[field], str) and 0 < len(value[field].strip()) <= 2048, "Unconfirmed writer exclusion procedure")
  times = []
  for field in ("starts_at", "expires_at"):
    require(isinstance(value[field], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value[field]),
            "Package-link window requires UTC-second timestamps")
    times.append(datetime.fromisoformat(value[field]).replace(tzinfo=timezone.utc).timestamp())
  now = time.time() if now is None else now
  require(times[0] <= now < times[1] and 0 < times[1] - times[0] <= 86400, "Package-link window expired or invalid")
  server = workflow.gitea.get("/api/v1/version")
  require(isinstance(server, dict) and server_version(server.get("version")) == server_version(value["server_version"]),
          "Package-link window server version differs")
  return {"digest": digest(canonical(value)), "scope": value}


def link_packages(workflow, path=None):
  if not workflow.config.get("link_packages", False):
    return
  for image in workflow.config["images"]:
    name = image["name"]
    details = {"owner": workflow.gitea.owner, "name": name, "repository": workflow.config["repository"],
               "digest": workflow.state.data["outputs"][name]["digest"]}
    operation = "link:" + name
    workflow.state.intent(operation, details)
    staging = workflow.state.data["staging"].get(name)
    require(isinstance(staging, dict) and staging.get("digest") == details["digest"], "Prepared package evidence is missing")
    # After a completed publication, separately authorized cleanup may have retired staging.
    required = None if workflow.state.data.get("published") else staging["tag"]
    if association(workflow, name, required) is None:
      authority = window(workflow, name, path)
      workflow.state.data.setdefault("link_windows", {}).setdefault(name, []).append(authority)
      workflow.state.flush()
      # The second read narrows stale evidence; only actual operator exclusion closes the race.
      window(workflow, name, path)
      if association(workflow, name, required) is None:
        window(workflow, name, path)
        workflow.gitea.link_package(name)
    require(association(workflow, name) == workflow.config["repository"], "Package linking was not confirmed")
    workflow.state.complete(operation)


def verify_links(workflow):
  if workflow.config.get("link_packages", False):
    for image in workflow.config["images"]:
      require(association(workflow, image["name"]) == workflow.config["repository"], "Publication package link differs")
