#!/usr/bin/env python3
"""Run the prepared image's default command on every required platform."""

import json
import os
import re
import subprocess
from pathlib import Path
import tempfile


def observe(inputs, platform):
  declaration = inputs.get("local_images")
  if declaration is None:
    return
  if declaration.get("schema") != 1 or declaration.get("reference") != inputs["image"]:
    raise ValueError("Local provenance declaration differs")
  result = subprocess.run(["docker", "image", "inspect", "--platform", platform, "--format", "{{.Id}}", inputs["image"]],
                          capture_output=True, text=True, timeout=60)
  platform_id = result.stdout.strip()
  if result.returncode != 0 or not re.fullmatch(r"sha256:[0-9a-f]{64}", platform_id):
    raise ValueError("Local image identity is unavailable")
  # Containerd image ls identifies the index; --platform inspect identifies its member.
  result = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", inputs["image"]],
                          capture_output=True, text=True, timeout=60)
  identity = result.stdout.strip()
  if result.returncode != 0 or not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
    raise ValueError("Local reference identity is unavailable")
  path = Path(declaration["journal"])
  value = {"schema": 1, "run": declaration["run"], "reference": inputs["image"], "observations": {}, "platform_ids": {}}
  if path.exists():
    if path.is_symlink() or path.stat().st_size > 65536:
      raise ValueError("Invalid local provenance journal")
    previous = json.loads(path.read_text())
    if any(previous.get(key) != value[key] for key in ("schema", "run", "reference")):
      raise ValueError("Local provenance journal differs")
    value["observations"].update(previous["observations"])
    value["platform_ids"].update(previous.get("platform_ids", {}))
  value["observations"][platform] = identity
  value["platform_ids"][platform] = platform_id
  descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".local-")
  try:
    with os.fdopen(descriptor, "w") as output:
      os.fchmod(output.fileno(), 0o600)
      json.dump(value, output)
      output.flush()
      os.fsync(output.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
      os.fsync(directory)
    finally:
      os.close(directory)
  finally:
    if os.path.exists(temporary):
      os.unlink(temporary)


def verify(inputs):
  image = inputs.get("image")
  platforms = inputs.get("platforms")
  if inputs.get("schema") != 1 or not isinstance(image, str) or not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image):
    raise ValueError("Verification requires an immutable image reference")
  if platforms != ["linux/amd64", "linux/arm64"]:
    raise ValueError("Hello World verification requires AMD64 and ARM64")
  for platform in platforms:
    commands = (["docker", "pull", "--platform", platform, image],
                ["docker", "run", "--rm", "--platform", platform, image])
    for command in commands:
      result = subprocess.run(command, capture_output=True, text=True, timeout=300)
      if result.returncode != 0:
        raise ValueError("Hello World pull/run failed for " + platform)
      if command[1] == "pull":
        observe(inputs, platform)
    if result.stdout != "Hello World\n":
      raise ValueError("Unexpected default-command output for " + platform)
    print(platform + ": Hello World")


if __name__ == "__main__":
  try:
    verify(json.loads(os.environ["RELEASE_INPUT_JSON"]))
  except (KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired):
    raise SystemExit("Hello World verification failed; inspect platform support, registry access, and default command") from None
