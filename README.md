# Container release template

- [Container release template](#container-release-template)
  - [Use](#use)
  - [Development](#development)

Version 0.6.3 publishes one AMD64/ARM64 container image and links its package to a Gitea repository. See [release notes](docs/releases/0.6.3.md).

## Use

Follow [configuration and credentials](docs/bash-configuration.md). When copying the template, replace the sample Dockerfile, Git remote, and target/login settings in `scripts/release.json`. Store your token privately in `~/.config/git/token`.

```sh
./scripts/release.sh --validate
./scripts/release.sh
```

Publication writes real Git tags, images, releases, and package links. Use clean, already-pushed `main` and exclude other writers through completion. Package linking uses the Gitea API directly without checking the server version. Read the [release checklist](docs/release-process.md) and [recovery rules](docs/bash-publication.md) first.

Only the Bash workflow is supported. It does not migrate old transactions, update itself, delete images, or reassign packages. Verification is local only; see [known limits](docs/bash-publication.md#known-limits).

## Development

Requires Bash and Python 3.11+ on Linux/POSIX. Publication also needs Git, curl, Docker Buildx, and filesystem locks. No jq, Node, or Python packages are needed.

```sh
python3 -B -m unittest discover -s tests -v
for script in scripts/*.sh; do bash -n "$script"; done
./scripts/release.sh --validate
```

Root `VERSION`, README, and committed release notes must agree. See [verification](docs/verification.md), [image usage](docs/image-usage.md), and [platform preparation](docs/platform-preparation.md).
