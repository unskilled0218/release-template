# Container release template

- [Container release template](#container-release-template)
  - [Use](#use)
  - [Development](#development)

Version 0.5.0 builds and publishes one AMD64/ARM64 container image, then links its package to the configured Gitea repository for the Packages tab. Python's standard library handles strict data and bounded I/O; no jq, Node, or Python packages are needed. See [release notes](docs/releases/0.5.0.md).

## Use

Review [configuration and credentials](docs/bash-configuration.md) once, set your target/login in `scripts/release.json`, and provision a private `~/.config/git/token` file. This repository's settings explicitly target its existing Gitea project and Hello World image; change them before copying it elsewhere. Replace the root Hello World Dockerfile with your application when adopting the template.

```sh
./scripts/release.sh --validate
./scripts/release.sh
```

Run publication only from clean, already-pushed `main`, with Git authentication, trusted HTTPS, and a Buildx builder advertising both platforms. New package links require stable Gitea 1.25.x. The command publishes real Git/image/release/package-link changes. Read [publication and partial failures](docs/bash-publication.md) first, including exclusive package-writer requirements. It never deletes images, reassigns packages, or performs retention cleanup.

Only the Bash workflow is supported in this checkout. Historical transactions require their preserved original checkout/pin; no migration or managed updater is provided. Verification is local only. Two [known publication warnings](docs/bash-publication.md#known-limits) remain unresolved.

## Development

Requires Bash and Python 3.11+ on Linux/POSIX. Publication additionally needs Git, curl, Docker Buildx, and working local filesystem locks. Tests use fake command ports and temporary Git repositories, not production services.

```sh
python3 -B -m unittest discover -s tests -v
for script in scripts/*.sh; do bash -n "$script"; done
./scripts/release.sh --validate
```

See [verification](docs/verification.md) for test boundaries, [image usage](docs/image-usage.md), and [platform preparation](docs/platform-preparation.md). Root `VERSION` is the sole project version source; README and committed versioned notes must agree with it. No other project is modified automatically.
