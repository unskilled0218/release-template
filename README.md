# Container release template

- [Container release template](#container-release-template)
  - [Use](#use)
  - [Development](#development)

Version 0.3.1 builds and publishes one AMD64/ARM64 container image with a Bash command, checked prerequisite reads, confirmed-tag guards, and preserved Docker connection selection. Python's standard library handles strict data and bounded I/O; no jq, Node, or Python packages are needed. See [release notes](docs/releases/0.3.1.md).

## Use

Review [configuration and credentials](docs/bash-configuration.md) once, set your target/login in `scripts/release.json`, and provision a private `~/.config/git/token` file. This repository's settings explicitly target its existing Gitea project and Hello World image; change them before copying it elsewhere. Replace the root Hello World Dockerfile with your application when adopting the template.

```sh
./scripts/release.sh --validate
./scripts/release.sh
```

Run publication only from clean, already-pushed `main`, with Git authentication, trusted HTTPS, and a Buildx builder advertising both platforms. The command publishes real Git/image/release changes. Read [publication and partial failures](docs/bash-publication.md) first. It never deletes images, reassigns packages, or performs retention cleanup.

The old Python CLI and managed installer are [legacy workflows](docs/legacy-release.md), not an automatic upgrade path. Existing transactions must keep their original pin. The 0.3.1 workflow has local-only verification, not a new live deployment or deletion attestation.

## Development

Requires Bash and Python 3.11+ on Linux/POSIX. Publication additionally needs Git, curl, Docker Buildx, and working local filesystem locks. Tests use fake command ports and temporary Git repositories, not production services.

```sh
python3 -B -m unittest discover -s tests -v
for script in scripts/*.sh; do bash -n "$script"; done
./scripts/release.sh --validate
```

See [verification](docs/verification.md) for test boundaries. Keep `VERSION`, module version metadata, and committed versioned notes consistent; no other project is modified automatically.
