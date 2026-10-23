# Container release template

- [Container release template](#container-release-template)
  - [Use](#use)
  - [Development](#development)

Version 0.2.6 provides pinned Gitea release tooling with committed project notes, exact annotated-tag recovery after Git pruning, dispatch-time package-link authority, and guarded local image removal. Historical notes are verified from their captured commit, independent of current checkout layout. It builds once and promotes verified multi-platform digests. Remote deletion stays blocked without fresh deployment-specific evidence. See [release notes](docs/releases/0.2.6.md).

## Use

Start with [installation and updates](docs/installation.md), then select an [example configuration](examples/) and read [configuration and hooks](docs/configuration.md), [credentials and TLS](docs/credentials.md), [publication and recovery](docs/publication.md), and [retention safety](docs/retention.md).

The [Ubuntu release test](docs/ubuntu-release-test.md) is opt-in and targets this project's approved Gitea repository. Do not copy its live configuration into another consumer without reviewing the target and permissions.

Read [image usage](docs/image-usage.md) for authentication and pull/run commands, [package linking](docs/package-linking.md) for the repository Packages tab, and [local image removal](docs/local-images.md) for ownership and retry limits. Consumers must commit their own `release_notes` before publishing with this pin.

The token-file default is `~/.config/git/token`. `GIT_TOKEN` overrides the **path**, not the token value. Set only `GIT_USERNAME` to the token owner's login. Read [Gitea migration](docs/gitea-migration.md) for the breaking schema-2 and credential changes.

No existing project is installed into or migrated automatically. Historical live v0.2.5 passed project-note/tag verification, repository package visibility, AMD64/ARM64 execution, no-write retry, and guarded local removal on Gitea 28.2.0/Docker 29.9.2. That result does not verify v0.2.6, which has local-only verification. Earlier release history and pre-existing local images remain preserved; live remote deletion stays unverified and evidence-gated.

## Development

Requires Python 3.11+ on Linux/POSIX with local filesystem `flock`, durable atomic rename, and directory `fsync`. Publication additionally needs Git, Docker with Buildx, configured builder platforms, trusted TLS, and each configured hook's tools. The engine has no Python package dependencies.

```sh
python3 -B -m unittest discover -s tests -v
bash -n scripts/release.sh
python3 -B scripts/launch.py validate --config examples/explicit.json
```

See [verification](docs/verification.md) for test boundaries and live checks. Template versions use `VERSION` and `release_template.__version__`; changes to those values must agree. Consumer pins use immutable Git commits rather than mutable branch names.
