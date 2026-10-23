# Goal

- [Goal](#goal)
  - [Command](#command)
  - [Goal](#goal-1)

## Command

Publish AMD64 and ARM64 images to Gitea Packages so users can use an image reference such as `git.lan/dev/example-image:latest`. Write release descriptions as human-readable content, not JSON or another machine-oriented format.

## Goal

Provide a reusable `latest` image reference that selects the correct AMD64 or ARM64 image, with verified pull/run instructions. Replace JSON release descriptions with clear human-readable release notes showing the image reference, supported platforms, and usage, while preserving publication identity verification and safe retries. This stage records the goal only; it makes no implementation changes or remote mutations.
