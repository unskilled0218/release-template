# goal

- [goal](#goal)
  - [command](#command)
  - [goal](#goal-1)

## command

Fix warning from previous task code review.

## goal

Resolve B1 in `tasks/4-migrate-forgejo-to-gitea/5-code-review.md`: distinguish malformed successful Gitea responses from confirmed HTTP 404 absence. Reject HTTP 200 JSON `null` and invalid release/package lookup shapes so publication and cleanup stop without authorizing writes or falsely recording retirement completion. Add regression coverage while preserving valid-404 recovery and existing safety guarantees. This stage records the goal only; no implementation changes or live operations.
