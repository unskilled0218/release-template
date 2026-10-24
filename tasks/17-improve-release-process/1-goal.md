# goal

- [goal](#goal)
  - [command](#command)
  - [goal](#goal-1)

## command

Update documentation and related release workflow guidance so projects using this template can follow it. Suggest improvements to the release process: show progress logs and actionable failure instructions; check ARM64 build compatibility, server connectivity, and installed prerequisites before building and pushing images. If platform support is missing, provide `docker run --privileged --rm tonistiigi/binfmt --install amd64,arm64 && docker buildx inspect --bootstrap` as a preparation instruction.

## goal

Define a clear, reusable release process with visible progress and actionable recovery guidance, covering platform readiness, required tools, server connectivity, image building, and publication in a safe order. Recommend practical improvements and keep privileged host preparation an explicit administrator action rather than an automatic release step.
