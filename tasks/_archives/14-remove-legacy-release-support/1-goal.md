# Goal

- [Goal](#goal)
  - [command](#command)
  - [goal](#goal-1)

## command

Remove legacy Python release support, including `release_template/`, `examples/`, legacy launcher/updater scripts, and legacy-only tests and active documentation. Keep the Bash release workflow and standalone Python data helper, use root `VERSION` as the sole project version source, and remove dependencies on deleted files while retaining useful current-workflow coverage.

## goal

Make the repository support only `./scripts/release.sh`, its standard-library helper, root Dockerfile, and explicit settings. Update README, active documentation, and verification to match; retain or migrate relevant tests and verify syntax, configuration, version/notes agreement, and active links. Preserve archived tasks, historical release notes, published resources, and original pinned checkouts/checkpoints without migration or rewriting. Keep Python as a runtime prerequisite and the two remaining release-review warnings as separate unresolved work. Do not touch `todo.md`, access real credentials, run live publication or Docker daemon operations, push source, or delete remote resources. This stage records the goal only; it changes no implementation code.
