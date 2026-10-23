# Image usage

- [Image usage](#image-usage)
  - [Authenticate and run](#authenticate-and-run)
  - [Platforms and immutable references](#platforms-and-immutable-references)

## Authenticate and run

The existing image is `git.lan/dev/container-release-template-hello:latest`; `example-image` is illustrative, not a published rename. The package requires authorized access. Use your own Gitea login and a protected token with package-read permission; never paste it into logs or command arguments.

```sh
docker login git.lan --username dev --password-stdin < "$HOME/.config/git/token"
docker pull git.lan/dev/container-release-template-hello:latest
docker run --rm git.lan/dev/container-release-template-hello:latest
```

The default command prints `Hello World` and exits zero. Registry login may persist credentials through Docker's configured store; use a private temporary `DOCKER_CONFIG` when temporary authentication is required, while preserving the selected daemon/context. The release tool isolates its authentication automatically and does not log the caller in permanently.

## Platforms and immutable references

Docker automatically selects AMD64 or ARM64 from the multi-platform index. Explicit checks require a matching native daemon or administrator-prepared emulation:

```sh
docker pull --platform linux/amd64 git.lan/dev/container-release-template-hello:latest
docker run --rm --platform linux/amd64 git.lan/dev/container-release-template-hello:latest
docker pull --platform linux/arm64 git.lan/dev/container-release-template-hello:latest
docker run --rm --platform linux/arm64 git.lan/dev/container-release-template-hello:latest
```

For reproducibility, replace `:latest` with `@sha256:<verified-index-digest>` obtained from independently verified registry/tag evidence. `latest` is mutable, and separately approved remote retention may eventually retire older content. The Ubuntu fixture's local-finalization setting removes only proven task-owned local copies after release; later use may need another pull. See [platform preparation](platform-preparation.md), [package linking](package-linking.md), and [local ownership](local-images.md). Image instructions do not belong in the project's release description.
