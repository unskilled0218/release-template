"""Evidence-gated deletion, with manifests protected before candidate selection."""

import time

from .core import ReleaseError, load, older, require
from .policy import owned_package, release_candidates


def deletion_evidence(path, config):
  require(path is not None, "Container deletion disabled: no disposable Forgejo verification evidence supplied")
  evidence = load(path)
  require(evidence.get("schema") == 1 and evidence.get("origin") == config["forgejo"].rstrip("/") and
          evidence.get("server_major") == 17 and evidence.get("disposable_repository") != config["repository"] and
          isinstance(evidence.get("disposable_repository"), str) and evidence.get("operator") and
          evidence.get("verified_at") and evidence.get("alias_preserves_shared_manifest") is True and
          evidence.get("digest_deletion_is_scoped") is True and
          evidence.get("retained_platforms_pullable") is True,
          "Deletion evidence is missing required same-server disposable verification results")
  return evidence


def deletion_environment(workflow, path):
  evidence = deletion_evidence(path, workflow.config)
  server = workflow.forgejo.get("/api/v1/version")
  require(str(server.get("version", "")).startswith("17."), "Server version differs from deletion evidence")
  return evidence


def protected_graph(workflow):
  roots = {name: {output["digest"]} for name, output in workflow.state.data["outputs"].items()}
  # A single state directory is required across invocations. Never delete a resumable run's graph.
  for path in workflow.state.path.parent.glob("*.json"):
    record = load(path)
    require(record.get("schema") == 1, "Unknown sibling checkpoint schema")
    if record.get("identity", {}).get("repository") != workflow.config["repository"]:
      continue
    if record.get("cleanup_complete"):
      continue
    for name, output in record.get("outputs", {}).items():
      if name in roots:
        roots[name].add(output["digest"])
    for operation_name, operation in record.get("operations", {}).items():
      if not operation_name.startswith("build:"):
        continue
      name = operation_name.removeprefix("build:")
      if name not in roots or name in record.get("outputs", {}):
        continue
      # A process can die after the remote accepts a build but before outputs are
      # checkpointed. The durable intent still owns the exact staging reference.
      staging_tag = operation.get("details", {}).get("tag")
      require(staging_tag == "rt-" + record["run"] + "-" + name, "Unfinished staging intent is not owned")
      recovered = workflow.registry.resolve(name, staging_tag)
      require(recovered is not None, "Unfinished build evidence is uncertain; cleanup requires explicit recovery")
      roots[name].add(recovered)
  protected = {}
  for name, references in roots.items():
    protected[name] = set()
    for reference in references:
      graph, _ = workflow.registry.graph(name, reference)
      protected[name].update(graph)
  return protected


def plan(workflow):
  workflow.verify_publication()
  config, state = workflow.config, workflow.state.data
  protected = protected_graph(workflow)
  current = workflow.release_version
  candidates = release_candidates(workflow.forgejo.releases(), current)
  skipped = []
  names = set(state["outputs"])
  for package in workflow.forgejo.packages():
    if not owned_package(package, config["repository"], names):
      continue
    name, reference = package["name"], package["version"]
    retained = {"latest"}
    image = next(image for image in config["images"] if image["name"] == name)
    if image.get("retain_version"):
      retained.add(workflow.tag)
    if reference in retained:
      continue
    staging = state["staging"].get(name)
    own_staging = bool(staging and reference == staging["tag"])
    if not own_staging and not older(reference, current) and not reference.startswith("sha256:"):
      skipped.append({"name": name, "version": reference, "reason": "Unrecognized version or unfinished external staging reference"})
      continue
    resolved = workflow.registry.resolve(name, reference)
    require(resolved is not None, "Package exists without registry identity")
    if own_staging:
      require(resolved == staging["digest"], "Staging ownership/digest conflict")
    if reference.startswith("sha256:"):
      if resolved in protected[name]:
        continue
      _, configurations = workflow.registry.graph(name, resolved)
      runnable = [item for item in configurations if item.get("architecture") in ("amd64", "arm64")]
      labels = [item.get("config", {}).get("Labels", {}) for item in runnable]
      source = config["forgejo"].rstrip("/") + "/" + config["repository"]
      if not labels or not all(item.get("org.opencontainers.image.source") == source and
          older(item.get("org.opencontainers.image.version"), current) for item in labels):
        skipped.append({"name": name, "version": reference, "reason": "Digest ownership/version cannot be proven"})
        continue
    candidates.append({"kind": "package", "name": name, "version": reference, "digest": resolved})
  return {"schema": 1, "run": state["run"], "candidates": candidates, "skipped": skipped}


def apply(workflow, evidence_path):
  workflow.verify_publication()
  evidence = deletion_environment(workflow, evidence_path)
  if "cleanup" not in workflow.state.data:
    workflow.state.data["cleanup"] = plan(workflow)
    workflow.state.flush()
  inventory = workflow.state.data["cleanup"]
  require(inventory["run"] == workflow.state.data["run"], "Cleanup belongs to another run")
  for candidate in inventory["candidates"]:
    if candidate.get("complete"):
      continue
    workflow.verify_publication()
    if candidate["kind"] == "release":
      existing = workflow.forgejo.release(candidate["tag"])
      if existing is not None:
        require(existing["id"] == candidate["id"] and not existing.get("draft") and
                not existing.get("prerelease") and older(existing["tag_name"], workflow.release_version),
                "Release cleanup candidate changed")
        workflow.forgejo.delete_release(candidate["id"])
    else:
      name, reference = candidate["name"], candidate["version"]
      present = workflow.forgejo.get(workflow.forgejo.package_path(name, reference), absent=True)
      if present is not None:
        require(owned_package(present, workflow.config["repository"], set(workflow.state.data["outputs"])),
                "Package ownership changed")
        require(workflow.registry.resolve(name, reference) == candidate["digest"], "Cleanup package digest changed")
        protected = protected_graph(workflow)
        require(not reference.startswith("sha256:") or candidate["digest"] not in protected[name],
                "Digest is now required by a retained or resumable image")
        require(evidence["alias_preserves_shared_manifest"], "Shared alias deletion is not verified")
        workflow.forgejo.delete_package(name, reference)
    candidate["complete"] = True
    workflow.state.flush()
  workflow.verify_publication()
  workflow.state.data["cleanup_complete"] = not bool(inventory["skipped"])
  workflow.state.flush()
  require(workflow.state.data["cleanup_complete"], "Cleanup incomplete: ambiguous records were preserved; inspect cleanup-plan")


def abandon(workflow, run_ids, minimum_age, evidence_path):
  """Explicitly selected abandoned runs only; never infer authority from tag age."""
  require(run_ids and minimum_age >= 86400, "Select run IDs and a retention threshold of at least one day")
  deletion_environment(workflow, evidence_path)
  workflow.verify_publication()
  records = {}
  for path in workflow.state.path.parent.glob("*.json"):
    record = load(path)
    if record.get("run") in run_ids:
      require(record.get("schema") == 1 and record.get("identity", {}).get("repository") == workflow.config["repository"],
              "Abandoned checkpoint ownership/schema differs")
      require(record["run"] != workflow.state.data["run"] and not record.get("published") and
              time.time() - record["created"] >= minimum_age, "Run is current, published, or inside the retention threshold")
      records[record["run"]] = (path, record)
  require(set(records) == set(run_ids), "Missing selected abandoned checkpoint inventory")
  for path, record in records.values():
    for name, staging in record["staging"].items():
      require(staging.get("tag") == "rt-" + record["run"] + "-" + name and staging.get("digest"),
              "Abandoned staging ownership is incomplete")
      current = workflow.registry.resolve(name, staging["tag"])
      if current is not None:
        require(current == staging["digest"], "Abandoned staging identity conflict")
        workflow.verify_publication()
        package = workflow.forgejo.get(workflow.forgejo.package_path(name, staging["tag"]), absent=True)
        require(package is None or owned_package(package, workflow.config["repository"],
                set(workflow.state.data["outputs"])), "Abandoned package association differs")
        if package is not None:
          workflow.forgejo.delete_package(name, staging["tag"])
    record["abandoned"] = True
    # Do not erase graph protection: this operation retires aliases, not manifest digests.
    from .core import save
    save(path, record)
  workflow.verify_publication()
