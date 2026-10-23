# goal

- [goal](#goal)
  - [command](#command)
  - [goal](#goal-1)

## command

Fix warnings from `tasks/1-standardize-container-releases/5-code-reivew.md`.

## goal

Resolve both warnings in `tasks/1-standardize-container-releases/5-code-review.md`: protect the complete manifest graphs of preserved references during cleanup, and reject unexpected runnable platforms while correctly recognizing artifacts and attestations. Add regression tests for both safety guarantees, including cleanup ownership checks. Keep destructive cleanup gated and make no live publications, deletions, or consumer changes. This stage records the goal only; implementation follows a separate approved plan.
