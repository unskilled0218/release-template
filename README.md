# Container release template

- [Container release template](#container-release-template)
  - [Use](#use)
  - [Development](#development)

Version 0.1.0 provides pinned, reusable Forgejo container release tooling. It builds once, promotes verified digests, publishes text-only releases, and cleans older versions only after verified publication. Final registry tags default to `latest` only; versioned Git tags remain.

## Use

Start with [installation and updates](docs/installation.md), then select an [example configuration](examples/) and read [configuration and hooks](docs/configuration.md), [credentials and TLS](docs/credentials.md), [publication and recovery](docs/publication.md), and [retention safety](docs/retention.md).

The token-file default is `~/.config/forgejo/forgejo-token`. `FORGEJO_TOKEN` overrides the **path**, not the token value. Set `FORGEJO_USERNAME` to the token owner's login.

No existing project is installed into or migrated automatically. Live Forgejo/Docker publication and deletion have not been verified for this initial implementation. Destructive container cleanup is blocked unless an operator supplies same-server disposable-test evidence.

## Development

Requires Python 3.11+ on Linux/POSIX with local filesystem `flock`, durable atomic rename, and directory `fsync`. Publication additionally needs Git, Docker with Buildx, configured builder platforms, trusted TLS, and each configured hook's tools. The engine has no Python package dependencies.

```sh
python3 -B -m unittest discover -s tests -v
bash -n scripts/release.sh
python3 -B scripts/launch.py validate --config examples/explicit.json
```

See [verification](docs/verification.md) for test boundaries and live checks. Template versions use `VERSION` and `release_template.__version__`; changes to those values must agree. Consumer pins use immutable Git commits rather than mutable branch names.
