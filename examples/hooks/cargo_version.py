#!/usr/bin/env python3
"""Print exactly one locked Cargo package version selected by package name."""

import json
import subprocess
import sys

result = subprocess.run(["cargo", "metadata", "--locked", "--no-deps", "--format-version", "1"],
                        capture_output=True, text=True, check=True)
packages = [item for item in json.loads(result.stdout)["packages"] if item["name"] == sys.argv[1]]
if len(packages) != 1:
  raise SystemExit("Select exactly one workspace package")
print(packages[0]["version"])
