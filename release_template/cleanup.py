"""Evidence-gated deletion, with manifests protected before candidate selection."""

import time

from .core import ReleaseError, load, older, require
from .policy import owned_package, release_candidates
from .oci import runnable


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


def digest_owned(workflow, evidence):
  try:
    configurations = runnable(evidence, include_subjects=True)
  except ReleaseError:
    return False
  source = workflow.config["forgejo"].rstrip("/") + "/" + workflow.config["repository"]
  labels = [item.get("config", {}).get("Labels", {}) for item in configurations]
  return bool(labels) and all(isinstance(item, dict) and
    item.get("org.opencontainers.image.source") == source and
    older(item.get("org.opencontainers.image.version"), workflow.release_version) for item in labels)


def package_eligibility(workflow, package, resolved, evidence):
  """Eligibility is policy, not authority to expand a persisted transaction."""
  config, state = workflow.config, workflow.state.data
  name, reference = package["name"], package["version"]
  if not owned_package(package, config["repository"], set(state["outputs"])):
    return False, None
  image = next(image for image in config["images"] if image["name"] == name)
  if reference == "latest" or (image.get("retain_version") and reference == workflow.tag):
    return False, None
  staging = state["staging"].get(name)
  if staging and reference == staging["tag"]:
    require(resolved == staging["digest"], "Staging ownership/digest conflict")
    return True, None
  if reference.startswith("sha256:"):
    owned = digest_owned(workflow, evidence)
    return owned, None if owned else "Digest ownership/version cannot be proven"
  if older(reference, workflow.release_version):
    return True, None
  return False, "Unrecognized version or unfinished external staging reference"


def package_inventory(workflow):
  """Resolve all same-name references, including records outside deletion authority."""
  rows, graphs = {}, {}
  packages = workflow.forgejo.packages()
  require(isinstance(packages, list), "Expected package inventory array")
  for package in packages:
    require(isinstance(package, dict), "Invalid package inventory record")
    if package.get("type") != "container" or package.get("name") not in workflow.state.data["outputs"]:
      continue
    name, reference = package["name"], package.get("version")
    require(isinstance(reference, str) and reference, "Invalid package reference")
    key = (name, reference)
    require(key not in rows, "Duplicate package inventory reference")
    resolved = workflow.registry.resolve(name, reference)
    require(resolved is not None, "Preserved package reference has no registry identity")
    if (name, resolved) not in graphs:
      graphs[name, resolved] = workflow.registry.graph(name, resolved)
    graph, evidence = graphs[name, resolved]
    eligible, reason = package_eligibility(workflow, package, resolved, evidence)
    rows[key] = {"package": package, "digest": resolved, "graph": graph,
                 "eligible": eligible, "reason": reason}
  return rows


def survivor_graph(workflow, rows, candidates):
  protected = protected_graph(workflow)
  pending = {(item["name"], item["version"]): item for item in candidates
             if item["kind"] == "package" and not item.get("complete")}
  for key, row in rows.items():
    candidate = pending.get(key)
    authorized = candidate and candidate.get("digest") == row["digest"] and row["eligible"]
    if not authorized:
      protected[key[0]].update(row["graph"])
  return protected


def skipped_records(rows, protected):
  return [{"name": name, "version": reference, "reason": row["reason"]}
          for (name, reference), row in rows.items() if row["reason"] and
          (not reference.startswith("sha256:") or row["digest"] not in protected[name])]


def plan(workflow):
  workflow.verify_publication()
  rows = package_inventory(workflow)
  candidates = release_candidates(workflow.forgejo.releases(), workflow.release_version)
  candidates.extend({"kind": "package", "name": name, "version": reference, "digest": row["digest"]}
                    for (name, reference), row in rows.items() if row["eligible"])
  protected = survivor_graph(workflow, rows, candidates)
  candidates = [item for item in candidates if item["kind"] != "package" or
                not item["version"].startswith("sha256:") or item["digest"] not in protected[item["name"]]]
  # Unknown digest roots remain visible even though they protect their own graph.
  skipped = skipped_records(rows, protected_graph(workflow))
  return {"schema": 1, "run": workflow.state.data["run"], "candidates": candidates, "skipped": skipped}


def validate_inventory(workflow, inventory):
  require(inventory.get("schema") == 1 and inventory["run"] == workflow.state.data["run"],
          "Cleanup belongs to another run or schema")
  rows = package_inventory(workflow)
  protected = survivor_graph(workflow, rows, inventory["candidates"])
  keys = set()
  for candidate in inventory["candidates"]:
    require(candidate.get("kind") in ("release", "package"), "Invalid cleanup candidate kind")
    if candidate["kind"] != "package":
      continue
    key = (candidate["name"], candidate["version"])
    require(key not in keys, "Duplicate cleanup candidate")
    keys.add(key)
    if candidate.get("complete"):
      continue
    row = rows.get(key)
    if row is None:
      require(workflow.forgejo.get(workflow.forgejo.package_path(*key), absent=True) is None,
              "Cleanup candidate missing from complete package inventory")
      continue
    require(row["digest"] == candidate["digest"] and row["eligible"], "Cleanup package identity/eligibility changed")
    require(not key[1].startswith("sha256:") or candidate["digest"] not in protected[key[0]],
            "Digest is now required by a retained, surviving, or resumable image")
  return rows


def apply(workflow, evidence_path):
  workflow.verify_publication()
  evidence = deletion_environment(workflow, evidence_path)
  if "cleanup" not in workflow.state.data:
    workflow.state.data["cleanup"] = plan(workflow)
    workflow.state.flush()
  inventory = workflow.state.data["cleanup"]
  validate_inventory(workflow, inventory)
  # Retire aliases before their backing digest, regardless of saved inventory order.
  ordered = sorted(inventory["candidates"], key=lambda item:
    2 if item["kind"] == "package" and item["version"].startswith("sha256:") else
    0 if item["kind"] == "package" else 1)
  for candidate in ordered:
    if candidate.get("complete"):
      continue
    workflow.verify_publication()
    validate_inventory(workflow, inventory)
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
        require(evidence["alias_preserves_shared_manifest"], "Shared alias deletion is not verified")
        workflow.forgejo.delete_package(name, reference)
    candidate["complete"] = True
    workflow.state.flush()
  workflow.verify_publication()
  rows = validate_inventory(workflow, inventory)
  inventory["skipped"] = skipped_records(rows, protected_graph(workflow))
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
