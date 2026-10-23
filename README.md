# Container release template

- [Container release template](#container-release-template)
  - [Use](#use)
  - [Development](#development)

Version 0.2.4 provides pinned Gitea release tooling with committed project-update notes, annotated-tag verification identity, explicit repository package linking, and guarded local image removal. It builds once and promotes verified multi-platform digests. Final registry tags default to `latest`; Git tags remain versioned. Remote deletion stays blocked without fresh deployment-specific evidence. See [release notes](docs/releases/0.2.4.md).

## Use

Start with [installation and updates](docs/installation.md), then select an [example configuration](examples/) and read [configuration and hooks](docs/configuration.md), [credentials and TLS](docs/credentials.md), [publication and recovery](docs/publication.md), and [retention safety](docs/retention.md).

The [Ubuntu release test](docs/ubuntu-release-test.md) is opt-in and targets this project's approved Gitea repository. Do not copy its live configuration into another consumer without reviewing the target and permissions.

Read [image usage](docs/image-usage.md) for authentication and pull/run commands, [package linking](docs/package-linking.md) for the repository Packages tab, and [local image removal](docs/local-images.md) for ownership and retry limits. Consumers must commit their own `release_notes` before publishing with this pin.

The token-file default is `~/.config/git/token`. `GIT_TOKEN` overrides the **path**, not the token value. Set only `GIT_USERNAME` to the token owner's login. Read [Gitea migration](docs/gitea-migration.md) for the breaking schema-2 and credential changes.

No existing project is installed into or migrated automatically. The historical v0.2.3 Ubuntu fixture passed live publication, AMD64/ARM64 execution, and same-checkpoint retry on Gitea 28.2.0. That result does not verify v0.2.4 or other deployments. Live deletion remains unverified and blocked without fresh same-server, exact-version disposable-test evidence.

## Development

Requires Python 3.11+ on Linux/POSIX with local filesystem `flock`, durable atomic rename, and directory `fsync`. Publication additionally needs Git, Docker with Buildx, configured builder platforms, trusted TLS, and each configured hook's tools. The engine has no Python package dependencies.

```sh
python3 -B -m unittest discover -s tests -v
bash -n scripts/release.sh
python3 -B scripts/launch.py validate --config examples/explicit.json
```

See [verification](docs/verification.md) for test boundaries and live checks. Template versions use `VERSION` and `release_template.__version__`; changes to those values must agree. Consumer pins use immutable Git commits rather than mutable branch names.
