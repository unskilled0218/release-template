"""Evidence-gated deletion, with manifests protected before candidate selection."""

import heapq
import re
import time
from datetime import datetime, timezone

from .core import ReleaseError, canonical, digest, load, older, require
from .policy import owned_package, release_candidates
from .oci import immutable, runnable
from .config import server_version


MAX_RETIREMENT_CANDIDATES = 10000
MAX_RETIREMENT_REFERENCES = 100000
DIGEST_OWNERSHIP_REASON = "Digest ownership/version cannot be proven"
MAX_EVIDENCE_AGE_SECONDS = 30 * 86400
MAX_EVIDENCE_FUTURE_SECONDS = 5 * 60


def candidate_projection(inventory):
  """Completion is progress, not part of the immutable deletion authority."""
  require(isinstance(inventory, dict) and inventory.get("schema") == 1 and
          isinstance(inventory.get("run"), str) and inventory["run"], "Invalid cleanup inventory")
  candidates = inventory.get("candidates")
  require(isinstance(candidates, list) and len(candidates) <= MAX_RETIREMENT_CANDIDATES,
          "Cleanup candidate inventory exceeds safety bound or is malformed")
  identities, keys = [], set()
  for item in candidates:
    require(isinstance(item, dict) and isinstance(item.get("complete", False), bool), "Invalid cleanup candidate")
    if item.get("kind") == "package":
      require(all(isinstance(item.get(field), str) and item[field] for field in ("name", "version", "digest")),
              "Invalid package candidate identity")
      immutable(item["digest"])
      require(not item["version"].startswith("sha256:") or item["version"] == item["digest"],
              "Raw candidate reference differs from its digest")
      identity = {field: item[field] for field in ("kind", "name", "version", "digest")}
      key = ("package", item["name"], item["version"])
    else:
      require(item.get("kind") == "release" and type(item.get("id")) is int and
              isinstance(item.get("tag"), str) and item["tag"], "Invalid release candidate identity")
      identity = {field: item[field] for field in ("kind", "id", "tag")}
      key = ("release", item["id"])
    require(key not in keys, "Duplicate cleanup candidate")
    keys.add(key)
    identities.append(identity)
  return sorted(identities, key=canonical)


def raw_candidates(inventory):
  return {(item["name"], item["digest"]): item for item in inventory["candidates"]
          if item["kind"] == "package" and item["version"].startswith("sha256:")}


def retirement_order(graphs):
  """Referring candidates retire before all candidate dependencies, per image."""
  require(isinstance(graphs, dict) and len(graphs) <= MAX_RETIREMENT_CANDIDATES, "Invalid retirement graphs")
  by_name, references = {}, 0
  for key, reachable in graphs.items():
    require(isinstance(key, tuple) and len(key) == 2 and isinstance(key[0], str) and key[0],
            "Invalid retirement candidate key")
    immutable(key[1])
    require(isinstance(reachable, (set, list, tuple)) and key[1] in reachable, "Missing retirement root evidence")
    references += len(reachable)
    require(references <= MAX_RETIREMENT_REFERENCES, "Retirement graph exceeds safety bound")
    for reference in reachable:
      immutable(reference)
    require(len(reachable) == len(set(reachable)), "Duplicate retirement reachability evidence")
    by_name.setdefault(key[0], {})[key[1]] = key
  edges, incoming = {}, dict.fromkeys(graphs, 0)
  for key, reachable in graphs.items():
    edges[key] = {by_name[key[0]][reference] for reference in reachable
                  if reference != key[1] and reference in by_name[key[0]]}
    for dependency in edges[key]:
      incoming[dependency] += 1
  ready = [key for key, count in incoming.items() if count == 0]
  heapq.heapify(ready)
  result = []
  while ready:
    key = heapq.heappop(ready)
    result.append(key)
    for dependency in sorted(edges[key]):
      incoming[dependency] -= 1
      if incoming[dependency] == 0:
        heapq.heappush(ready, dependency)
  require(len(result) == len(graphs), "Retirement dependency cycle")
  return result


def retirement_fingerprint(inventory, graphs):
  return digest(canonical({"run": inventory["run"], "candidates": candidate_projection(inventory), "graphs": graphs}))


def make_retirement(inventory, rows):
  candidate_projection(inventory)
  graphs = {}
  for key in raw_candidates(inventory):
    require(key in rows, "Legacy cleanup is partial or uncertain; explicit operator recovery required")
    graphs[key] = set(rows[key]["graph"])
  order = retirement_order(graphs)
  records = [{"key": list(key), "reachable": sorted(graphs[key])} for key in sorted(graphs)]
  return {"schema": 1, "run": inventory["run"], "fingerprint": retirement_fingerprint(inventory, records),
          "graphs": records, "order": [list(key) for key in order]}


def validate_retirement(inventory):
  candidate_projection(inventory)
  metadata = inventory.get("retirement")
  require(isinstance(metadata, dict) and set(metadata) == {"schema", "run", "fingerprint", "graphs", "order"} and
          metadata["schema"] == 1 and metadata["run"] == inventory["run"], "Invalid or unsupported retirement metadata")
  records = metadata["graphs"]
  require(isinstance(records, list) and len(records) <= MAX_RETIREMENT_CANDIDATES, "Invalid retirement graph inventory")
  graphs = {}
  for record in records:
    require(isinstance(record, dict) and set(record) == {"key", "reachable"} and
            isinstance(record["key"], list) and len(record["key"]) == 2 and
            all(isinstance(value, str) for value in record["key"]) and
            isinstance(record["reachable"], list), "Invalid retirement graph record")
    key = tuple(record["key"])
    require(key not in graphs, "Duplicate retirement candidate key")
    graphs[key] = record["reachable"]
  require(set(graphs) == set(raw_candidates(inventory)), "Retirement candidate coverage differs")
  order = retirement_order(graphs)
  require(metadata["order"] == [list(key) for key in order], "Retirement order differs from dependency evidence")
  require(metadata["fingerprint"] == retirement_fingerprint(inventory, records), "Retirement fingerprint differs")
  return graphs


def validate_evidence_time(value, now=None):
  """Enforce exact UTC formats and inclusive freshness limits without rewriting evidence."""
  require(isinstance(value, str) and
          re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}Z)?", value),
          "Invalid deletion evidence verified_at; expected UTC date or UTC-second timestamp")
  try:
    verified = datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()
  except ValueError as exc:
    raise ReleaseError("Invalid deletion evidence verified_at calendar date or time") from exc
  age = (time.time() if now is None else now) - verified
  require(age >= -MAX_EVIDENCE_FUTURE_SECONDS, "Deletion evidence verified_at is too far in the future")
  require(age <= MAX_EVIDENCE_AGE_SECONDS, "Deletion evidence expired; repeat disposable verification")


def deletion_evidence(path, config):
  require(path is not None, "Container deletion disabled: no disposable Gitea verification evidence supplied")
  evidence = load(path)
  require(isinstance(evidence, dict) and evidence.get("schema") == 2 and evidence.get("product") == "gitea" and
          "server_major" not in evidence and evidence.get("origin") == config["gitea"].rstrip("/") and
          evidence.get("disposable_repository") != config["repository"] and
          isinstance(evidence.get("disposable_repository"), str) and
          re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", evidence["disposable_repository"]) and
          all(isinstance(evidence.get(field), str) and evidence[field].strip() and len(evidence[field]) <= 256
              for field in ("operator", "verified_at")) and evidence.get("alias_preserves_shared_manifest") is True and
          evidence.get("digest_deletion_is_scoped") is True and
          evidence.get("retained_platforms_pullable") is True,
          "Deletion evidence requires fresh schema-2 Gitea same-server disposable verification results")
  server_version(evidence.get("server_version"))
  validate_evidence_time(evidence["verified_at"])
  return evidence


def deletion_environment(workflow, path):
  evidence = deletion_evidence(path, workflow.config)
  server = workflow.gitea.get("/api/v1/version")
  require(isinstance(server, dict), "Invalid Gitea server version response")
  require(server_version(server.get("version")) == evidence["server_version"], "Server version differs from deletion evidence")
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
  source = workflow.config["gitea"].rstrip("/") + "/" + workflow.config["repository"]
  labels = [item.get("config", {}).get("Labels", {}) for item in configurations]
  return bool(labels) and all(isinstance(item, dict) and
    item.get("org.opencontainers.image.source") == source and
    older(item.get("org.opencontainers.image.version"), workflow.release_version) for item in labels)


def package_eligibility(workflow, package, resolved, evidence):
  """Eligibility is policy, not authority to expand a persisted transaction."""
  config, state = workflow.config, workflow.state.data
  name, reference = package["name"], package["version"]
  if not owned_package(package, config["repository"], set(state["outputs"])):
    return False, "Package is not linked to the configured repository; preserved"
  image = next(image for image in config["images"] if image["name"] == name)
  if reference == "latest" or (image.get("retain_version") and reference == workflow.tag):
    return False, None
  staging = state["staging"].get(name)
  if staging and reference == staging["tag"]:
    require(resolved == staging["digest"], "Staging ownership/digest conflict")
    return True, None
  if reference.startswith("sha256:"):
    owned = digest_owned(workflow, evidence)
    return owned, None if owned else DIGEST_OWNERSHIP_REASON
  if older(reference, workflow.release_version):
    return True, None
  return False, "Unrecognized version or unfinished external staging reference"


def package_records(workflow):
  """Collect references before graph traversal, so absence can be reconciled first."""
  records = {}
  packages = workflow.gitea.packages()
  require(isinstance(packages, list), "Expected package inventory array")
  for package in packages:
    require(isinstance(package, dict), "Invalid package inventory record")
    if package.get("type") != "container" or package.get("name") not in workflow.state.data["outputs"]:
      continue
    name, reference = package["name"], package.get("version")
    require(isinstance(reference, str) and reference, "Invalid package reference")
    key = (name, reference)
    require(key not in records, "Duplicate package inventory reference")
    records[key] = package
  return records


def package_inventory(workflow, records=None):
  """Resolve all same-name references, including records outside deletion authority."""
  rows, graphs = {}, {}
  records = package_records(workflow) if records is None else records
  for key, package in records.items():
    name, reference = key
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
          (row["reason"] != DIGEST_OWNERSHIP_REASON or not reference.startswith("sha256:") or
           row["digest"] not in protected[name])]


def plan(workflow):
  workflow.verify_publication()
  rows = package_inventory(workflow)
  candidates = release_candidates(workflow.gitea.releases(), workflow.release_version)
  candidates.extend({"kind": "package", "name": name, "version": reference, "digest": row["digest"]}
                    for (name, reference), row in rows.items() if row["eligible"])
  protected = survivor_graph(workflow, rows, candidates)
  candidates = [item for item in candidates if item["kind"] != "package" or
                not item["version"].startswith("sha256:") or item["digest"] not in protected[item["name"]]]
  # Unknown digest roots remain visible even though they protect their own graph.
  skipped = skipped_records(rows, protected_graph(workflow))
  inventory = {"schema": 1, "run": workflow.state.data["run"], "candidates": candidates, "skipped": skipped}
  inventory["retirement"] = make_retirement(inventory, rows)
  return inventory


def validate_inventory(workflow, inventory):
  candidate_projection(inventory)
  require(inventory.get("schema") == 1 and inventory["run"] == workflow.state.data["run"],
          "Cleanup belongs to another run or schema")
  snapshots = validate_retirement(inventory) if "retirement" in inventory else None
  records = package_records(workflow)
  for candidate in inventory["candidates"]:
    if candidate["kind"] == "package":
      key = (candidate["name"], candidate["version"])
      require(key[0] in workflow.state.data["outputs"], "Cleanup candidate outside configured image inventory")
      if key not in records:
        require(workflow.gitea.get(workflow.gitea.package_path(*key), absent=True) is None,
                "Cleanup candidate missing from complete package inventory")
  rows = package_inventory(workflow, records)
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
    if snapshots is not None and key in snapshots and row is not None:
      require(set(row["graph"]) == set(snapshots[key]), "Live retirement topology differs from approved evidence")
    if row is None:
      continue
    require(row["digest"] == candidate["digest"] and row["eligible"], "Cleanup package identity/eligibility changed")
    require(not key[1].startswith("sha256:") or candidate["digest"] not in protected[key[0]],
            "Digest is now required by a retained, surviving, or resumable image")
  return rows


def ensure_retirement(workflow, inventory):
  candidate_projection(inventory)
  if "retirement" in inventory:
    validate_retirement(inventory)
    return
  require(not any(item.get("complete") for item in raw_candidates(inventory).values()),
          "Legacy cleanup is partial or uncertain; explicit operator recovery required")
  try:
    rows = validate_inventory(workflow, inventory)
    inventory["retirement"] = make_retirement(inventory, rows)
  except ReleaseError as exc:
    raise ReleaseError("Legacy cleanup cannot establish retirement evidence: " + str(exc) +
                       "; explicit operator recovery required") from exc
  workflow.state.flush()


def reconcile_absence(workflow, inventory, rows):
  changed = False
  for item in inventory["candidates"]:
    if item["kind"] == "package" and not item.get("complete") and (item["name"], item["version"]) not in rows:
      item["complete"] = True
      changed = True
  if changed:
    workflow.state.flush()


def require_retired_parents(inventory, candidate, rows):
  key = (candidate["name"], candidate["digest"])
  candidates = raw_candidates(inventory)
  for graph in inventory["retirement"]["graphs"]:
    parent = tuple(graph["key"])
    if parent != key and parent[0] == key[0] and key[1] in graph["reachable"]:
      require(candidates[parent].get("complete") and parent not in rows,
              "Referring manifest has not reached confirmed retirement")


def apply(workflow, evidence_path):
  workflow.verify_publication()
  evidence = deletion_environment(workflow, evidence_path)
  if "cleanup" not in workflow.state.data:
    workflow.state.data["cleanup"] = plan(workflow)
    workflow.state.flush()
  inventory = workflow.state.data["cleanup"]
  ensure_retirement(workflow, inventory)
  rows = validate_inventory(workflow, inventory)
  reconcile_absence(workflow, inventory, rows)
  # Retire aliases before their backing digest, regardless of saved inventory order.
  positions = {tuple(key): index for index, key in enumerate(inventory["retirement"]["order"])}
  ordered = sorted(inventory["candidates"], key=lambda item:
    (2, positions[item["name"], item["digest"]]) if item["kind"] == "package" and item["version"].startswith("sha256:") else
    (0, 0) if item["kind"] == "package" else (1, 0))
  for candidate in ordered:
    if candidate.get("complete"):
      continue
    workflow.verify_publication()
    rows = validate_inventory(workflow, inventory)
    reconcile_absence(workflow, inventory, rows)
    if candidate.get("complete"):
      continue
    if candidate["kind"] == "release":
      existing = workflow.gitea.release(candidate["tag"])
      if existing is not None:
        require(existing["id"] == candidate["id"] and not existing.get("draft") and
                not existing.get("prerelease") and older(existing["tag_name"], workflow.release_version),
                "Release cleanup candidate changed")
        workflow.gitea.delete_release(candidate["id"])
    else:
      name, reference = candidate["name"], candidate["version"]
      if reference.startswith("sha256:"):
        require_retired_parents(inventory, candidate, rows)
      present = workflow.gitea.get(workflow.gitea.package_path(name, reference), absent=True)
      if present is not None:
        require(owned_package(present, workflow.config["repository"], set(workflow.state.data["outputs"])),
                "Package ownership changed")
        require(workflow.registry.resolve(name, reference) == candidate["digest"], "Cleanup package digest changed")
        require(evidence["alias_preserves_shared_manifest"], "Shared alias deletion is not verified")
        workflow.gitea.delete_package(name, reference)
        require(workflow.gitea.get(workflow.gitea.package_path(name, reference), absent=True) is None,
                "Deletion outcome is not yet absent; retry cleanup")
    candidate["complete"] = True
    workflow.state.flush()
  workflow.verify_publication()
  rows = validate_inventory(workflow, inventory)
  inventory["skipped"] = skipped_records(rows, protected_graph(workflow))
  workflow.state.data["cleanup_complete"] = not bool(inventory["skipped"])
  workflow.state.flush()
  require(workflow.state.data["cleanup_complete"], "Cleanup incomplete: ambiguous records were preserved; inspect cleanup-plan")


def retire_abandoned_alias(workflow, name, staging):
  """Reconcile both remote views before deletion and before recording retirement."""
  current = workflow.registry.resolve(name, staging["tag"])
  package_path = workflow.gitea.package_path(name, staging["tag"])
  package = workflow.gitea.get(package_path, absent=True)
  require(current is None or current == staging["digest"], "Abandoned staging identity conflict")
  require(package is None or owned_package(package, workflow.config["repository"],
          set(workflow.state.data["outputs"])), "Abandoned package association differs")
  require((current is None) == (package is None), "Abandoned package/registry presence differs; retry abandonment")
  if package is None:
    return
  workflow.verify_publication()
  workflow.gitea.delete_package(name, staging["tag"])
  require(workflow.gitea.get(package_path, absent=True) is None,
          "Abandoned package deletion is not yet absent; retry abandonment")
  require(workflow.registry.resolve(name, staging["tag"]) is None,
          "Abandoned registry alias is not yet absent; retry abandonment")


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
      retire_abandoned_alias(workflow, name, staging)
    record["abandoned"] = True
    # Do not erase graph protection: this operation retires aliases, not manifest digests.
    from .core import save
    save(path, record)
  workflow.verify_publication()
