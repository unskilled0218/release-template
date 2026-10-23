"""Release command entry point; defaults never select a production project."""

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .adapters import Gitea, Registry, Runner, git_identity, preflight
from .cleanup import abandon, apply, plan
from .config import credentials, read_version, validate
from .core import ReleaseError, child, load, require
from .workflow import Workflow


def main(root, revision=None, argv=None):
  parser = argparse.ArgumentParser(description="Build once, publish text-only releases, clean up only with verified evidence.")
  parser.add_argument("mode", choices=("validate", "publish", "resume", "cleanup-plan", "cleanup", "abandon"))
  parser.add_argument("--config", default="release.json")
  parser.add_argument("--tag")
  parser.add_argument("--deletion-evidence", type=Path)
  parser.add_argument("--run", action="append", default=[])
  parser.add_argument("--minimum-age-days", type=int, default=30)
  arguments = parser.parse_args(argv)
  workflow = None
  try:
    root = Path(root).resolve()
    config = validate(load(child(root, arguments.config)), root)
    require(not config.get("test_http") or "unittest" in sys.modules,
            "Loopback HTTP is only available to in-process test fixtures")
    if arguments.mode == "validate":
      print("Configuration valid; no credentials or remote operations used")
      return 0
    username, token = credentials()
    runner = Runner(root, token)
    preflight(runner, config["images"])
    commit = git_identity(runner, config)
    # State/lock paths must already be ignored by the consumer; never edit its ignore rules.
    for ignored in (".release-template/probe", ".template-operation.lock", ".template-transaction/probe"):
      runner.run(["git", "check-ignore", "--quiet", ignored])
    release_version = read_version(config, root, runner, arguments.tag)
    if revision is None:
      revision = runner.run(["git", "rev-parse", "HEAD"]).strip()
    registry, gitea = Registry(config, username, token), Gitea(config, token)
    state_path = root / ".release-template" / ("v" + release_version + ".json")
    if arguments.mode != "publish":
      require(state_path.exists(), "Mode requires an existing verified release checkpoint")
    workflow = Workflow(root, config, release_version, revision, runner, registry, gitea, commit)
    if arguments.mode in ("publish", "resume"):
      with runner.docker_auth(config["registry"], username, token):
        workflow.publish()
      print("Publication verified: v" + release_version)
      # An absent evidence file blocks cleanup, but never invalidates recorded publication success.
      apply(workflow, arguments.deletion_evidence)
    elif arguments.mode == "cleanup-plan":
      print(json.dumps(plan(workflow), sort_keys=True, indent=2))
    elif arguments.mode == "cleanup":
      apply(workflow, arguments.deletion_evidence)
    else:
      abandon(workflow, arguments.run, arguments.minimum_age_days * 86400, arguments.deletion_evidence)
    return 0
  except (ReleaseError, OSError, KeyError, TypeError, ValueError) as exc:
    prefix = "Publication succeeded; cleanup incomplete" if workflow and workflow.state.data.get("published") else "Release stopped"
    # Expected operational errors are deliberately bounded; raw tool/API bodies never enter this path.
    message = str(exc) if isinstance(exc, ReleaseError) else "Invalid or unavailable input; inspect configuration and prerequisites"
    print(prefix + ": " + message, file=sys.stderr)
    return 1
