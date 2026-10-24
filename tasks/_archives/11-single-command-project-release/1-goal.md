# Goal

- [Goal](#goal)
  - [command](#command)
  - [goal](#goal-1)

## command

Use only `./scripts/release.sh` to build and publish. Current command: `GIT_USERNAME=dev ./scripts/release.sh publish --config examples/ubuntu-hello/release.json --tag v0.2.6`.

## goal

Make running `./scripts/release.sh` without arguments build, verify, and publish this project's configured multi-platform image and release, using the committed project version and configured login without requiring an inline environment assignment or explicit mode, configuration, or tag arguments. Preserve explicit CLI commands, credential-file handling, exact-identity recovery, and existing publication and cleanup safety gates. This task defines the intended behavior only; it does not execute a release.
