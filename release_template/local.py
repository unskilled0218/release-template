"""Daemon-bound, restart-safe removal of proven local release references only."""

import json
from pathlib import Path
import re

from .core import ReleaseError, canonical, digest, require


def image_id(value):
  require(isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value), "Malformed local image identity")
  return value


class DockerLocal:
  def __init__(self, runner):
    self.runner = runner

  def binding(self):
    context = self.runner.run(["docker", "context", "show"]).strip()
    endpoint = self.runner.run(["docker", "context", "inspect", context, "--format", "{{json .Endpoints.docker.Host}}"])
    info = json.loads(self.runner.run(["docker", "info", "--format", "{{json .ID}}"]))
    require(isinstance(info, str) and info and context, "Docker daemon identity is unavailable")
    environment = getattr(self.runner, "environment", {})
    # Hash connection identity, never persist connection credentials or TLS material.
    connection = {"endpoint": endpoint, "host": environment.get("DOCKER_HOST"),
                  "context": environment.get("DOCKER_CONTEXT")}
    return {"context": context, "endpoint": digest(canonical(connection)), "daemon": info}

  def inventory(self):
    ids = sorted(set(self.runner.run(["docker", "image", "ls", "--all", "--quiet", "--no-trunc"]).split()))
    require(len(ids) <= 10000, "Local image inventory exceeds safety bound")
    records = []
    for offset in range(0, len(ids), 50):
      for identity in ids[offset:offset + 50]:
        image_id(identity)
      rows = json.loads(self.runner.run(["docker", "image", "inspect", *ids[offset:offset + 50]]))
      require(isinstance(rows, list) and len(rows) == len(ids[offset:offset + 50]), "Incomplete local image inventory")
      for row in rows:
        require(isinstance(row, dict), "Malformed local image inventory")
        identity = image_id(row.get("Id"))
        tags, references = row.get("RepoTags") or [], row.get("RepoDigests") or []
        require(isinstance(tags, list) and isinstance(references, list) and
                all(isinstance(item, str) for item in tags + references), "Malformed local image references")
        records.append({"id": identity, "tags": sorted(tags), "digests": sorted(references)})
    require(sorted(item["id"] for item in records) == ids, "Local image inventory identity differs")
    return records

  def used(self, reference):
    return bool(self.runner.run(["docker", "ps", "--all", "--filter", "ancestor=" + reference,
                                 "--format", "{{.ID}}"]).strip())

  def remove(self, reference):
    self.runner.run(["docker", "image", "rm", "--no-prune", reference])


class LocalImages:
  def __init__(self, workflow, port=None):
    self.workflow = workflow
    self.state = workflow.state
    self.port = port or DockerLocal(workflow.runner)
    self.enabled = workflow.config.get("remove_local_images", False)

  def start(self):
    if not self.enabled:
      return
    binding = self.port.binding()
    record = self.state.data.get("local_finalization")
    if record is None:
      require(not self.state.data["operations"] and not self.state.data["outputs"] and
              not self.state.data.get("checked"), "Local ownership baseline missing; explicit recovery required")
      record = {"schema": 1, "run": self.state.data["run"], "binding": binding,
                "baseline": self.port.inventory(), "references": {}, "unproven": []}
      self.state.data["local_finalization"] = record
      self.state.flush()
    self.record()
    require(record["binding"] == binding, "Docker daemon/context differs from original local ownership")

  def record(self):
    record = self.state.data.get("local_finalization")
    require(isinstance(record, dict) and record.get("schema") == 1 and record.get("run") == self.state.data["run"] and
            isinstance(record.get("baseline"), list) and isinstance(record.get("references"), dict) and
            isinstance(record.get("unproven"), list) and isinstance(record.get("binding"), dict),
            "Local ownership record missing or malformed; explicit recovery required")
    for row in record["baseline"]:
      require(isinstance(row, dict) and set(row) == {"id", "tags", "digests"} and
              isinstance(row["tags"], list) and isinstance(row["digests"], list) and
              all(isinstance(value, str) for value in row["tags"] + row["digests"]), "Malformed local baseline")
      image_id(row["id"])
    names = {self.workflow.config["registry"] + "/" + self.workflow.gitea.owner + "/" + image["name"]: image
             for image in self.workflow.config["images"]}
    for reference, entry in record["references"].items():
      name, separator, expected = reference.partition("@")
      require(separator and name in names and re.fullmatch(r"sha256:[0-9a-f]{64}", expected) and
              isinstance(entry, dict) and set(entry) == {"details", "observations", "status"} and
              entry["details"] == {"digest": expected, "platforms": names[name]["platforms"]} and
              isinstance(entry["status"], str) and isinstance(entry["observations"], dict) and
              set(entry["observations"]) <= set(names[name]["platforms"]), "Malformed local reference record")
      for identity in entry["observations"].values():
        image_id(identity)
    require(all(isinstance(reference, str) and reference in record["references"] for reference in record["unproven"]),
            "Malformed unproven local effects")
    return record

  def declare(self, reference, platforms):
    if not self.enabled:
      return None
    record = self.record()
    names = {self.workflow.config["registry"] + "/" + self.workflow.gitea.owner + "/" + item["name"]
             for item in self.workflow.config["images"]}
    name, separator, expected = reference.partition("@")
    require(separator and name in names and re.fullmatch(r"sha256:[0-9a-f]{64}", expected), "Unowned local pull reference")
    details = {"digest": expected, "platforms": platforms}
    previous = record["references"].get(reference)
    if previous is None:
      record["references"][reference] = {"details": details, "observations": {}, "status": "pending"}
    else:
      require(previous["details"] == details, "Local pull intent changed")
    self.state.flush()
    path = self.state.path.parent / ("local-" + self.state.data["run"] + "-" + digest(reference.encode())[7:] + ".journal")
    return {"schema": 1, "journal": str(path), "run": record["run"], "reference": reference}

  def observe(self, declaration):
    if declaration is None:
      return
    path = Path(declaration["journal"])
    if not path.exists():
      # Opaque hooks do not acquire authority just by receiving a declaration.
      record = self.record()
      reference = declaration["reference"]
      if reference not in record["unproven"]:
        record["unproven"].append(reference)
      self.state.flush()
      return
    require(not path.is_symlink() and path.stat().st_size <= 65536, "Invalid local observation journal")
    with path.open("rb") as source:
      data = source.read(65537)
    require(len(data) <= 65536, "Local observation journal exceeds size bound")
    value = json.loads(data)
    require(isinstance(value, dict) and set(value) == {"schema", "run", "reference", "observations"} and
            type(value["schema"]) is int and value["schema"] == 1 and value["run"] == declaration["run"] and
            value["reference"] == declaration["reference"] and isinstance(value["observations"], dict),
            "Local observation journal scope differs")
    entry = self.record()["references"][declaration["reference"]]
    require(set(value["observations"]) <= set(entry["details"]["platforms"]), "Unknown observed platform")
    for platform, identity in value["observations"].items():
      image_id(identity)
    entry["observations"] = value["observations"]
    entry["status"] = "observed"
    self.state.flush()

  def finalize(self):
    if not self.enabled:
      return []
    require(self.state.data.get("published") and self.workflow.publication_verified,
            "Local finalization requires publication verification in this invocation")
    record = self.record()
    require(self.port.binding() == record["binding"], "Docker daemon/context differs from original local ownership")
    baseline_ids = {row["id"] for row in record["baseline"]}
    baseline_refs = {ref for row in record["baseline"] for ref in row["tags"] + row["digests"]}
    outcomes = []
    for reference, entry in record["references"].items():
      require(isinstance(entry, dict) and set(entry) == {"details", "observations", "status"} and
              isinstance(entry["details"], dict) and isinstance(entry["observations"], dict), "Malformed local removal record")
      # Validate persisted references again; a checkpoint name alone never grants authority.
      expected = entry["details"].get("digest")
      require(isinstance(expected, str) and reference.endswith("@" + expected) and
              re.fullmatch(r"sha256:[0-9a-f]{64}", expected) and
              reference.split("@", 1)[0] in {self.workflow.config["registry"] + "/" + self.workflow.gitea.owner + "/" +
                image["name"] for image in self.workflow.config["images"]}, "Invalid local removal scope")
      name = reference.split("@", 1)[0].rsplit("/", 1)[1]
      require(self.state.data["outputs"].get(name, {}).get("digest") == expected, "Local digest differs from prepared output")
      try:
        require(self.port.binding() == record["binding"], "Docker daemon/context changed")
        inventory = self.port.inventory()
        rows = [row for row in inventory if reference in row["digests"] + row["tags"]]
        reason = None
        if not rows:
          result = "already absent"
        else:
          ids = {row["id"] for row in rows}
          observed = set(entry["observations"].values())
          if reference in baseline_refs or ids & baseline_ids:
            reason = "pre-existing reference/image"
          elif reference in record["unproven"]:
            reason = "opaque hook provenance"
          elif not observed or not ids <= observed:
            reason = "uncertain or changed local identity"
          elif any(set(row["tags"] + row["digests"]) - {reference} for row in rows):
            reason = "shared local references"
          elif self.port.used(reference):
            reason = "image used by a running or stopped container"
          if reason:
            result = "safely skipped: " + reason
          else:
            entry["status"] = "removing"
            self.state.flush()
            require(self.port.binding() == record["binding"] and self.port.inventory() == inventory and
                    not self.port.used(reference), "Local image evidence changed before removal")
            self.port.remove(reference)
            require(not any(reference in row["tags"] + row["digests"] for row in self.port.inventory()),
                    "Local image removal was not confirmed")
            result = "removed"
        entry["status"] = result
        self.state.flush()
      except (ReleaseError, OSError, ValueError, KeyError, TypeError):
        result = "failed: local evidence/removal unavailable"
        entry["status"] = result
        self.state.flush()
      outcomes.append({"reference": reference, "result": result})
    known = set(record["references"]) | baseline_refs
    prefixes = {self.workflow.config["registry"] + "/" + self.workflow.gitea.owner + "/" + image["name"]
                for image in self.workflow.config["images"]}
    try:
      inventory = self.port.inventory()
    except (ReleaseError, OSError, ValueError, KeyError, TypeError):
      return outcomes + [{"reference": "(inventory)", "result": "failed: local inventory unavailable"}]
    for row in inventory:
      for reference in row["tags"] + row["digests"]:
        if reference not in known and any(reference.startswith(prefix + "@") or reference.startswith(prefix + ":")
                                          for prefix in prefixes):
          outcomes.append({"reference": reference, "result": "safely skipped: undeclared local effect"})
    return outcomes
