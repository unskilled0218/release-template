# Container release template

- [Container release template](#container-release-template)
  - [Use](#use)
  - [Development](#development)

Version 0.2.0 provides pinned, reusable Gitea container release tooling. It builds once, promotes verified digests, publishes text-only releases, and cleans older versions only after verified publication. Final registry tags default to `latest` only; versioned Git tags remain. Cleanup protects surviving graphs and retires referring manifests before dependencies; publication verifies every runnable platform.

## Use

Start with [installation and updates](docs/installation.md), then select an [example configuration](examples/) and read [configuration and hooks](docs/configuration.md), [credentials and TLS](docs/credentials.md), [publication and recovery](docs/publication.md), and [retention safety](docs/retention.md).

The token-file default is `~/.config/git/token`. `GIT_TOKEN` overrides the **path**, not the token value. Set only `GIT_USERNAME` to the token owner's login. Read [Gitea migration](docs/gitea-migration.md) for the breaking schema-2 and credential changes.

No existing project is installed into or migrated automatically. Live Gitea/Docker publication and deletion remain unverified. Destructive container cleanup is blocked unless an operator supplies fresh Gitea same-server, exact-version disposable-test evidence.

## Development

Requires Python 3.11+ on Linux/POSIX with local filesystem `flock`, durable atomic rename, and directory `fsync`. Publication additionally needs Git, Docker with Buildx, configured builder platforms, trusted TLS, and each configured hook's tools. The engine has no Python package dependencies.

```sh
python3 -B -m unittest discover -s tests -v
bash -n scripts/release.sh
python3 -B scripts/launch.py validate --config examples/explicit.json
```

See [verification](docs/verification.md) for test boundaries and live checks. Template versions use `VERSION` and `release_template.__version__`; changes to those values must agree. Consumer pins use immutable Git commits rather than mutable branch names.
