# Goal

- [Goal](#goal)
  - [Command](#command)
  - [Goal](#goal-1)

## Command

Test this project's container release workflow using a disposable image based on `ubuntu:24.04` that prints `Hello World`. Use a disposable test repository, not an existing consumer project. Confirm the target and permissions before remote pushes, publication, or deletion. The local Docker build/run smoke test already passed; it does not verify the release workflow.

## Goal

Verify the pinned template's release workflow in an approved disposable repository using the Ubuntu `Hello World` image, and record actual publication, image execution, and retry results. Test deletion only with separate approval and valid disposable-test evidence; otherwise leave cleanup blocked and report it as unverified. Preserve existing consumer projects and distinguish end-to-end release results from the completed local build/run smoke test. This task stage records the goal only; it performs no implementation or remote operations.
