import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from release_template.config import credentials, endpoint, read_version, validate
from release_template.core import ReleaseError, child, image_order, older, promotion_allowed, version
from release_template.state import State
from tests.support import configuration


class CoreTests(unittest.TestCase):
  def test_semantic_order_is_not_lexicographic_and_prereleases_are_not_deleted(self):
    self.assertTrue(older("v1.9.0", "1.10.0"))
    for value in ("latest", "01.0.0", "1.0.0-rc.1", "sha256:abc", None):
      self.assertFalse(older(value, "2.0.0"), value)

  def test_paths_refuse_absolute_parent_and_symlink_escapes(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      (root / "link").symlink_to("/tmp")
      for value in ("../elsewhere", "/etc/passwd", "link/file"):
        with self.subTest(value=value), self.assertRaises(ReleaseError):
          child(root, value)

  def test_token_default_and_override_never_use_real_home(self):
    with tempfile.TemporaryDirectory() as temporary:
      path = Path(temporary) / ".config/forgejo/forgejo-token"
      path.parent.mkdir(parents=True)
      path.write_text("fixture-token\n")
      path.chmod(0o600)
      environment = {"HOME": temporary, "FORGEJO_USERNAME": "fixture"}
      self.assertEqual(credentials(environment), ("fixture", "fixture-token"))
      for override in (str(path), "~/.config/forgejo/forgejo-token"):
        self.assertEqual(credentials(environment | {"FORGEJO_TOKEN": override})[1], "fixture-token")
      for override in ("", "raw-token-value", "~/missing"):
        with self.subTest(override=override), self.assertRaises(ReleaseError):
          credentials(environment | {"FORGEJO_TOKEN": override})
      path.chmod(0o644)
      with self.assertRaisesRegex(ReleaseError, "private"):
        credentials(environment)
      path.chmod(0o600)
      for value in ("", "two tokens"):
        path.write_text(value)
        with self.assertRaises(ReleaseError):
          credentials(environment)

  def test_username_owner_is_not_a_login_and_conflicts_fail(self):
    with tempfile.TemporaryDirectory() as temporary:
      path = Path(temporary) / "token"
      path.write_text("fixture")
      path.chmod(0o600)
      environment = {"FORGEJO_TOKEN": str(path), "FORGEJO_USER": "fixture"}
      self.assertEqual(credentials(environment)[0], "fixture")
      with self.assertRaisesRegex(ReleaseError, "Conflicting"):
        credentials(environment | {"FORGEJO_USERNAME": "other"})
      with self.assertRaisesRegex(ReleaseError, "login"):
        credentials({"FORGEJO_TOKEN": str(path)})

  def test_endpoint_rejects_credentials_redirect_origins_and_production_http(self):
    for value in ("http://forgejo.invalid", "https://user:pass@forgejo.invalid", "https://forgejo.invalid/api", "https://forgejo.invalid?q=x"):
      with self.subTest(value=value), self.assertRaises(ReleaseError):
        endpoint(value)
    self.assertEqual(endpoint("http://127.0.0.1:8000", True), "http://127.0.0.1:8000")
    with self.assertRaises(ReleaseError):
      endpoint("http://forgejo.invalid", True)

  def test_configuration_requires_explicit_names_and_pinned_dependency_adapter(self):
    config = configuration()
    self.assertEqual(validate(config, Path.cwd()), config)
    config["registry"] = "other.invalid"
    with self.assertRaises(ReleaseError):
      validate(config, Path.cwd())
    config = configuration()
    config["images"].append({"name": "child", "platforms": ["linux/amd64"], "dependencies": ["application"]})
    with self.assertRaisesRegex(ReleaseError, "adapter"):
      validate(config, Path.cwd())
    config["images"][1]["build"] = ["python3", "hooks/build.py"]
    self.assertEqual([image["name"] for image in image_order(config["images"])], ["application", "child"])
    config["images"][0]["dependencies"] = ["child"]
    with self.assertRaisesRegex(ReleaseError, "cycle"):
      image_order(config["images"])

  def test_package_version_agrees_with_both_lock_versions(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      (root / "package.json").write_text('{"version":"1.2.3"}')
      lock = {"version": "1.2.3", "packages": {"": {"version": "1.2.3"}}}
      (root / "package-lock.json").write_text(json.dumps(lock))
      config = {"version": {"kind": "package", "path": "package.json"}}
      self.assertEqual(read_version(config, root, None), "1.2.3")
      lock["packages"][""]["version"] = "1.2.4"
      (root / "package-lock.json").write_text(json.dumps(lock))
      with self.assertRaises(ReleaseError):
        read_version(config, root, None)

  def test_stale_promotion_and_unrelated_alias_change_are_refused(self):
    with self.assertRaisesRegex(ReleaseError, "Stale"):
      promotion_allowed({"app:latest": "new"}, {"app:latest": "old"}, {"app:latest": "target"},
                        "1.0.0", {"version": "2.0.0", "targets": {}})
    with self.assertRaisesRegex(ReleaseError, "outside"):
      promotion_allowed({"app:latest": "unrelated"}, {"app:latest": "old"}, {"app:latest": "target"}, "2.0.0", None)
    promotion_allowed({"a:latest": "old", "b:latest": "target"}, {"a:latest": "old", "b:latest": "old"},
                      {"a:latest": "target", "b:latest": "target"}, "2.0.0", None)

  def test_durable_intent_survives_process_exit_and_unknown_schema_fails(self):
    with tempfile.TemporaryDirectory() as temporary:
      path = Path(temporary) / "state.json"
      code = 'from pathlib import Path; from release_template.state import State; import os; s=State(Path(__import__("sys").argv[1]), {"test":1}); s.intent("push", {"tag":"rt-fixture"}); os._exit(23)'
      result = subprocess.run([sys.executable, "-c", code, str(path)], cwd=Path(__file__).resolve().parents[1])
      self.assertEqual(result.returncode, 23)
      state = State(path, {"test": 1})
      operation_id = state.data["operations"]["push"]["id"]
      self.assertEqual(state.intent("push", {"tag": "rt-fixture"})["id"], operation_id)
      with self.assertRaises(ReleaseError):
        state.intent("push", {"tag": "other"})
      state.data["schema"] = 99
      state.flush()
      with self.assertRaisesRegex(ReleaseError, "schema"):
        State(path, {"test": 1})
