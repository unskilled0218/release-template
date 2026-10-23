"""The opt-in live fixture's hook is tested locally without Docker or credentials."""

import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ubuntu_hello_verify", ROOT / "examples/ubuntu-hello/verify.py")
HOOK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOOK)
IMAGE = "git.lan/dev/container-release-template-hello@sha256:" + "a" * 64


class UbuntuHelloTests(unittest.TestCase):
  def inputs(self):
    return {"schema": 1, "image": IMAGE, "platforms": ["linux/amd64", "linux/arm64"]}

  def test_hook_pulls_and_runs_default_command_on_both_platforms(self):
    results = [subprocess.CompletedProcess([], 0, "pulled\n"), subprocess.CompletedProcess([], 0, "Hello World\n")] * 2
    with patch.object(HOOK.subprocess, "run", side_effect=results) as run, contextlib.redirect_stdout(io.StringIO()):
      HOOK.verify(self.inputs())
    self.assertEqual([call.args[0] for call in run.call_args_list], [
      ["docker", "pull", "--platform", "linux/amd64", IMAGE],
      ["docker", "run", "--rm", "--platform", "linux/amd64", IMAGE],
      ["docker", "pull", "--platform", "linux/arm64", IMAGE],
      ["docker", "run", "--rm", "--platform", "linux/arm64", IMAGE]])
    self.assertTrue(all(call.kwargs["timeout"] == 300 for call in run.call_args_list))

  def test_mutable_image_and_incomplete_platforms_fail_before_docker(self):
    for change in ({"image": "git.lan/dev/example:latest"}, {"schema": 2}, {"platforms": ["linux/amd64"]}):
      with self.subTest(change=change), patch.object(HOOK.subprocess, "run") as run:
        with self.assertRaises(ValueError):
          HOOK.verify(self.inputs() | change)
        run.assert_not_called()

  def test_failed_pull_stops_before_running_the_image(self):
    with patch.object(HOOK.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "private-fixture-token")) as run:
      with self.assertRaisesRegex(ValueError, "pull/run failed") as caught:
        HOOK.verify(self.inputs())
    self.assertEqual(run.call_count, 1)
    self.assertNotIn("private-fixture-token", str(caught.exception))

  def test_wrong_default_output_or_failed_runtime_cannot_pass(self):
    for code, output in ((0, "Hello World"), (0, "wrong\n"), (1, "Hello World\n")):
      with self.subTest(code=code, output=output):
        results = [subprocess.CompletedProcess([], 0, "pulled\n"), subprocess.CompletedProcess([], code, output)]
        with patch.object(HOOK.subprocess, "run", side_effect=results):
          with self.assertRaises(ValueError):
            HOOK.verify(self.inputs())
