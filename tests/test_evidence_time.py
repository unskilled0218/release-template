"""Deletion authorization uses bounded UTC evidence, never a calendar-dependent fixture."""

import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from release_template.cleanup import abandon, apply, deletion_environment, plan, validate_evidence_time
from release_template.core import ReleaseError, load
from release_template.workflow import Workflow
from tests.support import COMMIT, REVISION, FakeGitea, FakeRegistry, FakeRunner, configuration, evidence, package


NOW = datetime(2026, 3, 31, tzinfo=timezone.utc).timestamp()


class EvidenceTimeTests(unittest.TestCase):
  def test_exact_utc_formats_and_valid_leap_day_are_accepted(self):
    for value in ("2026-03-31", "2026-03-31T00:00:00Z", "2026-03-01T00:00:00Z"):
      with self.subTest(value=value):
        validate_evidence_time(value, now=NOW)
    leap_day = datetime(2024, 2, 29, tzinfo=timezone.utc).timestamp()
    validate_evidence_time("2024-02-29", now=leap_day)

  def test_malformed_shapes_types_and_calendar_values_are_rejected(self):
    values = (None, True, 123, [], {}, "", "not-a-date", "2026-3-31", "2026-03-31\n",
              " 2026-03-31", "2026-03-31 ", "2026-03-31T00:00:00", "2026-03-31T00:00:00+00:00",
              "2026-03-31T00:00:00.0Z", "2026-03-31t00:00:00z", "2026-02-29", "2026-04-31",
              "2026-13-01", "0000-01-01", "2026-03-31T24:00:00Z", "2026-03-31T00:60:00Z",
              "2026-03-31T00:00:60Z", "２０２６-03-31")
    for value in values:
      with self.subTest(value=value), self.assertRaisesRegex(ReleaseError, "Invalid deletion evidence"):
        validate_evidence_time(value, now=NOW)

  def test_maximum_age_is_inclusive_and_date_only_means_midnight_utc(self):
    validate_evidence_time("2026-03-01", now=NOW)
    validate_evidence_time("2026-03-01T00:00:00Z", now=NOW)
    for value in ("2026-03-01", "2026-03-01T00:00:00Z"):
      with self.subTest(value=value), self.assertRaisesRegex(ReleaseError, "expired"):
        validate_evidence_time(value, now=NOW + 1)
    validate_evidence_time("2026-03-01T00:00:01Z", now=NOW + 1)

  def test_future_skew_is_inclusive_and_one_second_more_is_rejected(self):
    validate_evidence_time("2026-03-31T00:05:00Z", now=NOW)
    with self.assertRaisesRegex(ReleaseError, "future"):
      validate_evidence_time("2026-03-31T00:05:01Z", now=NOW)
    validate_evidence_time("2026-03-31", now=NOW - 300)
    with self.assertRaisesRegex(ReleaseError, "future"):
      validate_evidence_time("2026-03-31", now=NOW - 301)

  def test_default_clock_is_read_at_call_time_and_errors_do_not_echo_input(self):
    with patch("release_template.cleanup.time.time", return_value=NOW) as clock:
      validate_evidence_time("2026-03-31")
      clock.assert_called_once_with()
      clock.return_value = NOW + 31 * 86400
      with self.assertRaisesRegex(ReleaseError, "expired"):
        validate_evidence_time("2026-03-31")
    with self.assertRaises(ReleaseError) as caught:
      validate_evidence_time("private-fixture-token", now=NOW)
    self.assertNotIn("private-fixture-token", str(caught.exception))


class EvidenceTimeGateTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.config = configuration()
    self.registry = FakeRegistry()
    self.gitea = FakeGitea(self.registry)
    self.runner = FakeRunner(self.registry)
    self.old = Workflow(self.root, self.config, "0.9.0", REVISION, self.runner, self.registry, self.gitea, COMMIT)
    self.old.state.data["created"] = NOW - 2 * 86400
    self.old.state.flush()
    self.workflow = Workflow(self.root, self.config, "1.0.0", REVISION, self.runner, self.registry, self.gitea, COMMIT)
    self.workflow.publish()
    staging = self.workflow.state.data["staging"]["application"]["tag"]
    self.gitea.package_records.append(package("application", staging))
    self.path = self.root / "evidence.json"

  def test_bad_time_blocks_cleanup_and_abandonment_before_version_request_or_writes(self):
    current_before = self.workflow.state.path.read_bytes()
    old_before = self.old.state.path.read_bytes()
    for value, message in (("1900-01-01", "expired"), ("not-a-date", "Invalid"), ("2999-01-01", "future"),
                           ("2026-02-29", "Invalid"), ("2026-03-31T00:05:01Z", "future")):
      evidence(self.path, verified_at=value)
      for mode in ("cleanup", "abandon"):
        with self.subTest(value=value, mode=mode), patch("release_template.cleanup.time.time", return_value=NOW):
          with patch.object(self.gitea, "get", wraps=self.gitea.get) as lookups:
            with self.assertRaisesRegex(ReleaseError, message):
              if mode == "cleanup":
                apply(self.workflow, self.path)
              else:
                abandon(self.workflow, [self.old.state.data["run"]], 86400, self.path)
          self.assertFalse(any(call.args[0] == "/api/v1/version" for call in lookups.call_args_list))
          self.assertEqual(self.gitea.deleted, [])
          self.assertEqual(self.workflow.state.path.read_bytes(), current_before)
          self.assertEqual(self.old.state.path.read_bytes(), old_before)
          self.assertTrue(load(self.workflow.state.path)["published"])

  def test_valid_time_preserves_attestation_and_exact_version_gate(self):
    evidence(self.path, verified_at="2026-03-31")
    before = self.path.read_bytes()
    with patch("release_template.cleanup.time.time", return_value=NOW):
      self.assertEqual(deletion_environment(self.workflow, self.path), json.loads(before))
      with patch.object(self.gitea, "get", return_value={"version": "28.2.0+different"}):
        with self.assertRaisesRegex(ReleaseError, "version differs"):
          deletion_environment(self.workflow, self.path)
    self.assertEqual(self.path.read_bytes(), before)

  def test_expired_retry_stops_without_changing_approved_cleanup(self):
    evidence(self.path, verified_at="2026-03-31")
    self.workflow.state.data["cleanup"] = plan(self.workflow)
    self.workflow.state.flush()
    before = self.workflow.state.path.read_bytes()
    with patch("release_template.cleanup.time.time", return_value=NOW + 31 * 86400):
      with self.assertRaisesRegex(ReleaseError, "expired"):
        apply(self.workflow, self.path)
    self.assertEqual(self.workflow.state.path.read_bytes(), before)
    self.assertEqual(self.gitea.deleted, [])

  def test_read_only_plan_needs_no_evidence_or_time_validation(self):
    before = self.workflow.state.path.read_bytes()
    with patch("release_template.cleanup.validate_evidence_time", side_effect=AssertionError("No evidence needed")):
      self.assertTrue(plan(self.workflow)["candidates"])
    self.assertEqual(self.workflow.state.path.read_bytes(), before)
    self.assertEqual(self.gitea.deleted, [])
