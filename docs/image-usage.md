# Image usage

- [Image usage](#image-usage)
  - [Authenticate and run](#authenticate-and-run)
  - [Platforms and immutable references](#platforms-and-immutable-references)

## Authenticate and run

The image is `git.lan/dev/container-release-template-hello:latest`. Use your Gitea login and a protected package-read token. The example below uses login `dev`; replace it as needed. Never put tokens in arguments or logs.

```sh
docker login git.lan --username dev --password-stdin < "$HOME/.config/token/git"
docker pull git.lan/dev/container-release-template-hello:latest
docker run --rm git.lan/dev/container-release-template-hello:latest
```

The container prints `Hello World` and exits zero. `docker login` may persist credentials; for temporary authentication, use a private `DOCKER_CONFIG` while preserving your daemon/context. The release tool isolates its own authentication automatically.

Publication verifies the package link to `dev/container-release-template` for its Packages tab. The link covers all package versions; conflicting links are refused. See [association rules](bash-publication.md#package-association). No live 0.7.0 publication or UI result is certified.

## Platforms and immutable references

Docker selects AMD64 or ARM64 automatically. Explicit runtime checks need a matching native daemon or approved emulation:

```sh
docker pull --platform linux/amd64 git.lan/dev/container-release-template-hello:latest
docker run --rm --platform linux/amd64 git.lan/dev/container-release-template-hello:latest
docker pull --platform linux/arm64 git.lan/dev/container-release-template-hello:latest
docker run --rm --platform linux/arm64 git.lan/dev/container-release-template-hello:latest
```

Select a specific release with its plain version tag (for example, `:1.2.3`); only Git tags have the `v` prefix. For reproducibility, replace mutable `:latest` with `@sha256:<verified-index-digest>` from verified registry/tag evidence. Runtime checks and live package inspection need separate approval. See [platform preparation](platform-preparation.md) and [publication limits](bash-publication.md#known-limits). Keep image instructions here, not in release notes.
