"""Pure classification of manifest evidence, never an architecture allowlist."""

import re

from .core import require


OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
DOCKER_MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"
INDEX_TYPES = ("application/vnd.oci.image.index.v1+json",
               "application/vnd.docker.distribution.manifest.list.v2+json")
IMAGE_CONFIGS = ("application/vnd.oci.image.config.v1+json",
                 "application/vnd.docker.container.image.v1+json")
EMPTY_CONFIG = "application/vnd.oci.empty.v1+json"
ATTESTATION_LAYER = "application/vnd.in-toto+json"


def immutable(reference):
  require(isinstance(reference, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", reference),
          "Manifest dependencies must be immutable SHA-256 digests")
  return reference


def image_configuration(node, nodes):
  """Return a runnable configuration, or None for an explicitly proven artifact."""
  manifest, configuration = node["manifest"], node["configuration"]
  media_type = manifest.get("mediaType")
  require(media_type in (OCI_MANIFEST, DOCKER_MANIFEST), "Unsupported image/artifact manifest media type")
  require(isinstance(configuration, dict), "Image/artifact configuration must be an object")
  layers = manifest.get("layers")
  require(isinstance(layers, list) and all(isinstance(item, dict) and
          isinstance(item.get("mediaType"), str) and item["mediaType"] for item in layers),
          "Invalid image/artifact layer evidence")
  config_type = manifest.get("config", {}).get("mediaType")
  descriptors = [edge["descriptor"] for edge in node["incoming"] if edge["kind"] != "subject"]
  if manifest.get("artifactType"):
    require(media_type == OCI_MANIFEST and isinstance(manifest["artifactType"], str) and
            config_type == EMPTY_CONFIG and configuration == {}, "Contradictory OCI artifact/image evidence")
    require(all(not item.get("platform") and not item.get("annotations", {}).get("vnd.docker.reference.type")
                for item in descriptors), "Contradictory OCI artifact descriptor")
    return None
  require(config_type in IMAGE_CONFIGS, "Unsupported image configuration media type")
  require(isinstance(configuration.get("config", {}), dict), "Invalid image runtime configuration")
  require(isinstance(configuration.get("config", {}).get("Labels", {}), dict), "Invalid image labels")
  marked = any(item.get("annotations", {}).get("vnd.docker.reference.type") for item in descriptors)
  if marked:
    require(media_type == OCI_MANIFEST and configuration.get("os") == "unknown" and
            configuration.get("architecture") == "unknown" and layers and
            all(item["mediaType"] == ATTESTATION_LAYER for item in layers),
            "Contradictory attestation/image evidence")
    for descriptor in descriptors:
      annotations = descriptor.get("annotations", {})
      require(annotations.get("vnd.docker.reference.type") == "attestation-manifest" and
              descriptor.get("platform") == {"os": "unknown", "architecture": "unknown"},
              "Attestation descriptor lacks explicit non-runnable evidence")
      subject = immutable(annotations.get("vnd.docker.reference.digest"))
      require("subject" not in manifest or manifest["subject"].get("digest") == subject,
              "Attestation subject identity differs")
      require(subject in nodes and subject != node["digest"] and
              nodes[subject]["configuration"] is not None and
              nodes[subject]["configuration"].get("os") not in (None, "unknown"),
              "Attestation subject is not a known image")
    return None
  os_name, architecture = configuration.get("os"), configuration.get("architecture")
  require(all(isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", value) and
              value != "unknown" for value in (os_name, architecture)), "Unknown runnable image platform")
  for descriptor in descriptors:
    platform = descriptor.get("platform")
    if platform is not None:
      require(isinstance(platform, dict) and platform.get("os") == os_name and
              platform.get("architecture") == architecture, "Descriptor/configuration platform differs")
      if "variant" in platform and "variant" in configuration:
        require(platform["variant"] == configuration["variant"], "Descriptor/configuration variant differs")
  return configuration


def runnable(evidence, include_subjects=False):
  """Classify all fetched nodes, but count subject-only images only for ownership."""
  nodes, root = evidence["nodes"], evidence["root"]
  members, visiting = set(), set()

  def visit(reference):
    require(reference not in visiting, "Manifest membership cycle")
    require(reference not in members, "Duplicate manifest membership")
    visiting.add(reference)
    node = nodes[reference]
    for descriptor in node["manifest"].get("manifests", []):
      visit(descriptor["digest"])
    visiting.remove(reference)
    members.add(reference)

  visit(root)
  result = []
  for reference, node in nodes.items():
    manifest = node["manifest"]
    require(manifest.get("schemaVersion") == 2, "Unsupported manifest schema")
    for edge in node["incoming"]:
      declared = edge["descriptor"].get("mediaType")
      require(declared is None or declared == manifest.get("mediaType"), "Descriptor/manifest media type differs")
    if "manifests" in manifest:
      require(manifest.get("mediaType") in INDEX_TYPES and not manifest.get("artifactType") and
              "config" not in manifest and "layers" not in manifest, "Contradictory manifest index")
      continue
    configuration = image_configuration(node, nodes)
    if configuration is not None and (include_subjects or reference in members):
      result.append(configuration)
  return result
