# Goal

- [Goal](#goal)
  - [command](#command)
  - [goal](#goal-1)

## command

Fix warnings from the previous code review.

## goal

Address B1–B3 in `tasks/12-simplify-bash-release-template/5-code-review.md`: stop before promotion or release creation when a prerequisite registry read fails; require the exact confirmed Git tag to remain present before later publication writes; and preserve the caller's effective Docker host/context/TLS selection during private authentication setup. Add focused local regressions while retaining the single-command workflow, immutable identity, conservative retries, and existing resource limits. Do not add automatic repair, rollback, deletion, old-checkpoint migration, or live publication. This stage records the goal only; it changes no implementation code.
