#!/usr/bin/env python3
"""Synthetic child build; Dockerfile must use ARG PARENT then FROM ${PARENT}."""

import json
import os
from pathlib import Path
import subprocess

inputs = json.loads(os.environ["RELEASE_INPUT_JSON"])
source_root = Path(inputs["source_root"])
parent = inputs["dependencies"]["base"]
if "@sha256:" not in parent:
  raise SystemExit("A pinned parent digest is required")
subprocess.run([
  "docker", "buildx", "build", "--platform", ",".join(inputs["platforms"]),
  "--provenance=false", "--push", "--tag", inputs["staging"],
  "--metadata-file", inputs["metadata_file"], "--build-arg", "PARENT=" + parent,
  "--label", "org.opencontainers.image.revision=" + inputs["commit"],
  "--label", "org.opencontainers.image.version=" + inputs["version"],
  "--label", "org.opencontainers.image.source=" + inputs["source"],
  "--file", str(source_root / "docker/child.Dockerfile"), str(source_root),
], check=True)
