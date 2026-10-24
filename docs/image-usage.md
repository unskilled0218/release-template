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

Version 0.5.0 verifies that the configured package is associated with `dev/container-release-template` after publication, so authorized users can find it in that repository's Packages tab. Association applies to every version of the package, preserves an existing correct link, and refuses observed links elsewhere. A verified completed-publication retry may finish a missing link without republishing; see [package association and writer exclusion](bash-publication.md#package-association). This checkout has no live 0.5.0 publication or UI verification evidence.

## Platforms and immutable references

Docker automatically selects AMD64 or ARM64 from the multi-platform index. Explicit checks require a matching native daemon or administrator-prepared emulation:

```sh
docker pull --platform linux/amd64 git.lan/dev/container-release-template-hello:latest
docker run --rm --platform linux/amd64 git.lan/dev/container-release-template-hello:latest
docker pull --platform linux/arm64 git.lan/dev/container-release-template-hello:latest
docker run --rm --platform linux/arm64 git.lan/dev/container-release-template-hello:latest
```

For reproducibility, replace `:latest` with `@sha256:<verified-index-digest>` obtained from independently verified registry/tag evidence. `latest` is mutable. The release command performs no remote retention, package reassignment, or local-image removal. Live package visibility and runtime checks need separate approval; these instructions are not permission for a live experiment. See [platform preparation](platform-preparation.md) and the [known publication limits](bash-publication.md#known-limits). Image instructions do not belong in the project's release description.
