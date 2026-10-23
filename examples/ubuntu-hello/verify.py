#!/usr/bin/env python3
"""Run the prepared image's default command on every required platform."""

import json
import os
import re
import subprocess


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
    if result.stdout != "Hello World\n":
      raise ValueError("Unexpected default-command output for " + platform)
    print(platform + ": Hello World")


if __name__ == "__main__":
  try:
    verify(json.loads(os.environ["RELEASE_INPUT_JSON"]))
  except (KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired):
    raise SystemExit("Hello World verification failed; inspect platform support, registry access, and default command") from None
