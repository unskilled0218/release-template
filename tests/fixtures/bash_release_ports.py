#!/usr/bin/env python3
"""Test-only command ports. State and Git remotes are exclusively owned temporary fixtures."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import parse_qs, unquote, urlsplit


base = Path(os.environ["BASH_TEST_STATE"])
state_path = base / "state.json"
state = json.loads(state_path.read_text())
arguments = sys.argv[1:]
tool = Path(sys.argv[0]).name


def save():
  state_path.write_text(json.dumps(state))


def event(name):
  with (base / "events").open("a") as log:
    log.write(name + "\n")


def encode(value):
  return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def store(value):
  data = encode(value)
  digest = "sha256:" + hashlib.sha256(data).hexdigest()
  state["objects"][digest] = data.decode()
  return digest


if tool == "git":
  if "remote" in arguments and "get-url" in arguments:
    print("https://git.lan/" + ("foreign/project.git" if state.get("wrong_remote") else "fixtures/application.git"))
    sys.exit(0)
  if "ls-remote" in arguments and "refs/heads/main" in arguments and state.get("wrong_main"):
    print("a" * 40 + "\trefs/heads/main")
    sys.exit(0)
  is_push = "push" in arguments
  if is_push:
    event("tag-push")
  result = subprocess.run(["/usr/bin/git", *arguments])
  if is_push and state.pop("lose_tag", False):
    save()
    sys.exit(1)
  sys.exit(result.returncode)

if tool == "docker":
  if arguments[:2] == ["buildx", "inspect"]:
    event("builder")
    print("Platforms: " + ("linux/amd64" if state.get("unsupported") else "linux/amd64, linux/arm64"))
  elif arguments[:2] == ["context", "show"]:
    print("default")
  elif arguments[0] == "login":
    event("login")
    assert sys.stdin.read() == "SENTINEL_PRIVATE_TOKEN"
    config = json.loads((Path(os.environ["DOCKER_CONFIG"]) / "config.json").read_text())
    assert "credsStore" not in config and "credHelpers" not in config
    assert "SENTINEL_PRIVATE_TOKEN" not in json.dumps(config)
  elif arguments[:2] == ["buildx", "build"]:
    event("build")
    if state.get("hang_build"):
      time.sleep(20)
    context = Path(arguments[-1])
    assert (context / "Dockerfile").is_file() and not (context / ".git").exists()
    assert not (context / "ignored-secret").exists()
    labels = {arguments[i + 1].split("=", 1)[0]: arguments[i + 1].split("=", 1)[1]
              for i, arg in enumerate(arguments) if arg == "--label"}
    members = []
    for architecture in ("amd64", "arm64"):
      config = {"os": "linux", "architecture": architecture, "config": {"Labels": labels}}
      config_oid = store(config)
      manifest = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                  "config": {"digest": config_oid}, "layers": []}
      oid = store(manifest)
      members.append({"digest": oid, "platform": {"os": "linux", "architecture": architecture}})
    index = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json", "manifests": members}
    oid = store(index)
    state["aliases"][arguments[arguments.index("--tag") + 1].rsplit(":", 1)[1]] = oid
    state["prepared"] = oid
    if state.get("change_latest_build"):
      state["aliases"]["latest"] = store({"foreign": True})
    Path(arguments[arguments.index("--metadata-file") + 1]).write_text(json.dumps({
      "containerimage.digest": "sha256:" + "0" * 64 if state.get("bad_metadata") else oid}))
    save()
    if state.get("lose_build"):
      sys.exit(1)
  elif arguments[:3] == ["buildx", "imagetools", "create"]:
    event("promote")
    state["aliases"]["latest"] = arguments[-1].split("@", 1)[1]
    if state.get("oversize_after_promotion"):
      state["oversized"] = True
    save()
    if state.pop("lose_promotion", False):
      save()
      sys.exit(1)
  else:
    raise AssertionError("Unexpected Docker operation")
  sys.exit(0)

assert tool == "curl"
assert arguments[0] == "-q" and "--location" not in arguments and "--insecure" not in arguments
auth = Path(arguments[arguments.index("--config") + 1])
assert auth.stat().st_mode & 0o077 == 0
url = urlsplit(arguments[-1])
method = arguments[arguments.index("--request") + 1]
route = unquote(url.path)
status, headers, body = 200, {}, None
event("http:" + method + ":" + route)
if route.endswith("/releases") and method == "POST":
  event("release-post")
  if state.get("fail_release"):
    sys.exit(7)
  payload = Path(arguments[arguments.index("--data-binary") + 1][1:])
  record = json.loads(payload.read_text()) | {"id": 1}
  state["releases"].append(record)
  save()
  body, status = record, 201
  if state.pop("lose_release", False):
    save()
    sys.exit(7)
elif route.endswith("/releases"):
  page = int(parse_qs(url.query)["page"][0])
  body = state["releases"] if page == 1 or state.get("repeat_pages") else []
  if state.get("null_inventory"):
    body = None
elif route.endswith("/tags"):
  page = int(parse_qs(url.query)["page"][0])
  refs = subprocess.check_output(["/usr/bin/git", "--git-dir", str(base / "remote.git"), "tag", "--list"], text=True)
  body = [{"name": name} for name in refs.splitlines()] if page == 1 else []
elif route.startswith("/v2/"):
  reference = route.rsplit("/", 1)[1]
  if state.get("realm_foreign"):
    status, body = 401, {}
    headers["WWW-Authenticate"] = 'Bearer realm="https://foreign.invalid/token",service="test"'
  else:
    event("registry:" + reference)
    oid = reference if reference.startswith("sha256:") else state["aliases"].get(reference)
    if oid is None or oid not in state["objects"]:
      status, body = 404, {}
    else:
      body = json.loads(state["objects"][oid])
      headers["Docker-Content-Digest"] = oid
else:
  raise AssertionError("Unexpected fixture HTTP route")
if state.get("status"):
  status = state["status"]
data = encode(body)
if state.get("oversized"):
  data = b" " * 4194305
if state.get("malformed"):
  data = b"{broken"
header_data = "HTTP/1.1 " + str(status) + " Fixture\r\n" + "".join(k + ": " + v + "\r\n" for k, v in headers.items()) + "\r\n"
with open(arguments[arguments.index("--dump-header") + 1], "wb") as output:
  output.write(header_data.encode())
with open(arguments[arguments.index("--output") + 1], "wb") as output:
  output.write(data)
print(status, end="")
