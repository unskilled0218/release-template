#!/usr/bin/env python3
"""Test-only command ports. State and Git remotes are exclusively owned temporary fixtures."""

import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
from urllib.parse import parse_qs, unquote, urlsplit


base = Path(os.environ["BASH_TEST_STATE"])
state_path = base / "state.json"
state = json.loads(state_path.read_text())
arguments = sys.argv[1:]
tool = Path(sys.argv[0]).name

if state.get("hostile_output"):
  print("HOSTILE_REMOTE_OUTPUT SENTINEL_PRIVATE_TOKEN " + str(base / "token"), file=sys.stderr)


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


def docker_selection():
  directory = Path(os.environ.get("DOCKER_CONFIG") or str(Path.home() / ".docker"))
  configuration = json.loads((directory / "config.json").read_text()) if (directory / "config.json").exists() else {}
  explicit = os.environ.get("DOCKER_CONTEXT") or None
  host = os.environ.get("DOCKER_HOST") or None
  context = explicit or ("default" if host else configuration.get("currentContext", "default"))
  if context == "default":
    endpoint = host if host and not explicit else "unix:///var/run/docker.sock"
    tls = "host-tls" if host and not explicit and os.environ.get("DOCKER_TLS_VERIFY") else "local"
    if tls == "host-tls":
      assert (Path(os.environ["DOCKER_CERT_PATH"]) / "ca.pem").read_text() == "fixture-host-ca"
  else:
    records = [path for path in (directory / "contexts/meta").glob("*/meta.json")
               if json.loads(path.read_text()).get("Name") == context]
    assert len(records) == 1, "Named context metadata must remain usable"
    metadata = json.loads(records[0].read_text())
    endpoint = metadata["Endpoints"]["docker"]["Host"]
    assert (directory / "contexts/tls" / records[0].parent.name / "docker/ca.pem").read_text() == "fixture-ca"
    tls = "context-tls"
  buildx = Path(os.environ.get("BUILDX_CONFIG") or str(directory / "buildx"))
  current = json.loads((buildx / "current").read_text()) if (buildx / "current").exists() else {}
  builder = os.environ.get("BUILDX_BUILDER") or current.get("Name", "default")
  result = {"operation": arguments[:2], "context": context, "endpoint": endpoint, "tls": tls, "builder": builder,
            "tls_verify": os.environ.get("DOCKER_TLS_VERIFY"), "cert_path": os.environ.get("DOCKER_CERT_PATH")}
  if state.get("plugin_discovery") and arguments[0] == "buildx":
    # Model the original Go struct decoder independently of the canonical-only helper.
    extra = []
    for key, value in configuration.items():
      if key.casefold() == "cliPluginsExtraDirs".casefold():
        extra = value or []
    assert isinstance(extra, list) and all(isinstance(value, str) for value in extra)
    directories = [*map(Path, extra), directory / "cli-plugins", *map(Path, state["plugin_system_dirs"])]
    for candidate in (path / "docker-buildx" for path in directories):
      if candidate.exists():
        assert candidate.is_file() and os.access(candidate, os.X_OK), "Invalid plugin candidate must not fall through"
        result |= {"plugin": str(candidate.absolute()), "plugin_identity": candidate.read_text()}
        break
    else:
      event("plugin-discovery-missing")
      sys.exit(1)
  return result


if tool == "git":
  if "remote" in arguments and "get-url" in arguments:
    if "--push" in arguments:
      if state.get("push_urls_change_after_build") and state.get("prepared"):
        state.pop("push_urls_change_after_build")
        state["push_url_output"] = "https://git.lan/fixtures/application.git\nhttps://foreign.invalid/other/project.git\n"
        event("push-urls-changed")
        save()
      if "--all" in arguments:
        event("push-urls-read")
        fault = state.get("push_url_fault")
        if fault == "command":
          sys.exit(1)
        if fault == "overflow":
          sys.stdout.buffer.write(b"x" * 16777217)
          sys.exit(0)
        if fault == "encoding":
          sys.stdout.buffer.write(b"\xff\n")
          sys.exit(0)
      if "push_url_output" in state:
        value = state["push_url_output"]
        # Model get-url's first-entry default separately from --all.
        sys.stdout.write(value if "--all" in arguments else value.split("\n")[0] + "\n")
        sys.exit(0)
    print("https://git.lan/" + ("foreign/project.git" if state.get("wrong_remote") else "fixtures/application.git"))
    sys.exit(0)
  if "ls-remote" in arguments and "refs/heads/main" in arguments and state.get("wrong_main"):
    print("a" * 40 + "\trefs/heads/main")
    sys.exit(0)
  is_push = "push" in arguments
  if is_push:
    event("tag-push")
  tags = "ls-remote" in arguments and "--tags" in arguments
  pushed = "tag-push" in (base / "events").read_text().splitlines() if (base / "events").exists() else False
  if tags and pushed:
    state["post_push_scans"] = state.get("post_push_scans", 0) + 1
    fault = state.get("tag_change")
    promoted = "promote" in (base / "events").read_text().splitlines()
    if fault and ((fault["stage"] == "before_promotion" and state["post_push_scans"] == 2) or
                  (fault["stage"] == "before_release" and promoted)):
      state.pop("tag_change")
      event("tag-change:" + fault["stage"] + ":" + fault["kind"])
      reference = "refs/tags/v1.0.0"
      remote = ["/usr/bin/git", "--git-dir", str(base / "remote.git")]
      if fault["kind"] == "absent":
        subprocess.run([*remote, "update-ref", "-d", reference], check=True)
      elif fault["kind"] == "lightweight":
        commit = subprocess.check_output([*remote, "rev-parse", "main"], text=True).strip()
        subprocess.run([*remote, "update-ref", reference, commit], check=True)
      elif fault["kind"] == "changed":
        commit = subprocess.check_output([*remote, "rev-parse", "main"], text=True).strip()
        content = "object " + commit + "\ntype commit\ntag v1.0.0\ntagger Fixture <fixture@localhost> 0 +0000\n\nForeign annotation\n"
        oid = subprocess.check_output([*remote, "mktag"], input=content, text=True).strip()
        subprocess.run([*remote, "update-ref", reference, oid], check=True)
      elif fault["kind"] == "wrong_peel":
        state["wrong_peel"] = True
    save()
  if tags:
    result = subprocess.run(["/usr/bin/git", *arguments], capture_output=True)
    output = result.stdout
    if state.get("wrong_peel"):
      output = b"\n".join((b"a" * 40 + b"\t" + line.split(b"\t", 1)[1])
                          if line.endswith(b"refs/tags/v1.0.0^{}") else line for line in output.split(b"\n"))
    if pushed and state["post_push_scans"] == 1 and result.returncode == 0:
      event("tag-confirmed")
      state["confirmed_object"] = next(line.split()[0].decode() for line in output.splitlines()
                                       if line.endswith(b"\trefs/tags/v1.0.0"))
      save()
    sys.stdout.buffer.write(output)
    sys.stderr.buffer.write(result.stderr)
  else:
    result = subprocess.run(["/usr/bin/git", *arguments])
  if is_push and state.pop("lose_tag", False):
    save()
    sys.exit(1)
  sys.exit(result.returncode)

if tool == "docker":
  selection = docker_selection()
  with (base / "docker-selections").open("a") as output:
    output.write(json.dumps(selection) + "\n")
  if arguments[:2] == ["buildx", "inspect"]:
    event("builder")
    if state.get("builder_failure"):
      sys.exit(1)
    print("Platforms: " + ("linux/amd64" if state.get("unsupported") else "linux/amd64, linux/arm64"))
  elif arguments[:2] == ["context", "show"]:
    print(selection["context"])
  elif arguments[0] == "login":
    event("login")
    assert sys.stdin.read() == "SENTINEL_PRIVATE_TOKEN"
    config = json.loads((Path(os.environ["DOCKER_CONFIG"]) / "config.json").read_text())
    assert "credsStore" not in config and "credHelpers" not in config
    assert "SENTINEL_PRIVATE_TOKEN" not in json.dumps(config)
    assert "UNRELATED_AUTH_SENTINEL" not in json.dumps(config)
    if state.get("plugin_discovery"):
      assert set(config) == {"auths", "cliPluginsExtraDirs"}
      assert all(Path(value).is_absolute() for value in config["cliPluginsExtraDirs"])
      # Persist only the synthetic private config for post-login fixture assertions.
      (base / "private-docker-config.json").write_text(json.dumps(config))
      (Path(os.environ["DOCKER_CONFIG"]) / "config.json").write_text(json.dumps(config))
  elif arguments[:2] == ["buildx", "build"]:
    event("build")
    if state.get("build_barrier"):
      with (base / "build-entered").open("wb", buffering=0) as output:
        output.write(b"entered")
      descriptor = os.open(base / "build-release", os.O_RDONLY | os.O_NONBLOCK)
      try:
        assert select.select([descriptor], [], [], 30)[0], "Build barrier timed out"
        assert os.read(descriptor, 1) == b"1", "Build barrier was not released"
      finally:
        os.close(descriptor)
      event("build-barrier-released")
    if state.get("build_failure"):
      sys.exit(1)
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
    state["promotion_ready"] = True
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
raw_body = None
target_repository = {"id": 17, "name": "application", "full_name": "fixtures/application", "owner": {"login": "fixtures"}}
association_resource = None
event("http:" + method + ":" + route)
if state.get("http_transport_failure"):
  sys.exit(7)
if route == "/api/v1/version" and method == "GET":
  association_resource = "version"
  body = {"version": state.get("gitea_version", "1.25.0")}
elif route == "/api/v1/repos/fixtures/application" and method == "GET":
  association_resource = "target"
  body = target_repository
elif route == "/api/v1/packages/fixtures/container/application-hello/latest" and method == "GET":
  association_resource = "package"
  body = {"id": 23, "owner": {"login": "fixtures"}, "type": "container", "name": "application-hello",
          "version": "latest", "repository": None if state.get("hide_link") else state.get("linked_repository")}
  if "latest" not in state["aliases"]:
    status = 404
elif route == "/api/v1/packages/fixtures/container/application-hello/-/link/application" and method == "POST":
  event("package-link")
  assert "--data-binary" not in arguments
  assert auth.name == "api.curl"
  fault = state.get("link_fault")
  if fault in ("transport", "timeout"):
    sys.exit(28 if fault == "timeout" else 7)
  if state.get("linked_repository") is not None:
    status = 400
  elif fault in ("denied", "missing", "server", "wrong_status"):
    status = {"denied": 403, "missing": 404, "server": 500, "wrong_status": 200}[fault]
  else:
    if fault != "ignore":
      state["linked_repository"] = target_repository if fault != "conflict_after" else target_repository | {"id": 99}
    save()
    status, raw_body = 201, b""
    if fault == "overflow":
      raw_body = b" " * 4194305
    if fault == "lost":
      sys.exit(7)
elif route.endswith("/releases") and method == "POST":
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
  fault = None
  if reference == "latest" and "tag-confirmed" in (base / "events").read_text().splitlines() and "promote" not in (base / "events").read_text().splitlines():
    state["promotion_reads"] = state.get("promotion_reads", 0) + 1
    if state["promotion_reads"] == 2 and state.get("promotion_read_fault"):
      fault = state.pop("promotion_read_fault")
      event("promotion-read-injected:" + fault)
      if fault == "foreign":
        state["aliases"]["latest"] = store({"foreign": True})
      elif fault == "prepared":
        state["aliases"]["latest"] = state["prepared"]
        state["promotion_ready"] = True
    save()
  if reference == "latest" and state.get("promotion_ready") and state.get("post_confirmation_fault") and fault != "prepared":
    state["confirmation_reads"] = state.get("confirmation_reads", 0) + 1
    if state["confirmation_reads"] == 1:
      event("promotion-confirmation-read")
    elif state["confirmation_reads"] == 2:
      fault = state.pop("post_confirmation_fault")
      event("post-confirmation-injected:" + fault)
      if fault == "predecessor":
        state["aliases"]["latest"] = state["post_confirmation_predecessor"]
      elif fault == "absent":
        state["aliases"].pop("latest", None)
      elif fault == "foreign":
        state["aliases"]["latest"] = store({"foreign": True})
    save()
  if fault in ("transport", "timeout"):
    sys.exit(28 if fault == "timeout" else 7)
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
if association_resource:
  count_key = association_resource + "_reads"
  state[count_key] = state.get(count_key, 0) + 1
  fault = state.get("association_fault", {})
  if fault.get("resource") == association_resource and state[count_key] == fault.get("read", 1):
    kind = fault["kind"]
    event("association-read-injected:" + kind)
    if kind in ("transport", "timeout"):
      save()
      sys.exit(28 if kind == "timeout" else 7)
    if kind in ("missing", "unauthorized", "server", "redirect"):
      status = {"missing": 404, "unauthorized": 401, "server": 500, "redirect": 302}[kind]
    elif kind in ("malformed", "overflow"):
      raw_body = b"{broken" if kind == "malformed" else b" " * 4194305
    elif kind == "null":
      body = None
    elif kind == "absent_repository":
      body.pop("repository")
    elif kind == "wrong_name":
      body["name"] = "another-package"
    elif kind == "wrong_version":
      body["version"] = "rt-foreign"
    elif kind == "wrong_id":
      body["id"] = 99
    elif kind == "change_latest":
      state["aliases"]["latest"] = store({"foreign": True})
    else:
      raise AssertionError("Unexpected association fault")
  save()
data = encode(body) if raw_body is None else raw_body
if route.startswith("/v2/"):
  if fault == "overflow":
    data = b" " * 4194305
  elif fault == "malformed":
    data = b"{broken"
  elif fault == "null":
    data = b"null"
  elif fault in ("unauthorized", "server_error"):
    status = 401 if fault == "unauthorized" else 500
  if fault not in (None, "foreign", "prepared"):
    headers.pop("Docker-Content-Digest", None)
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
