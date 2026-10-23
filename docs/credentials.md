# Credentials and TLS

- [Credentials and TLS](#credentials-and-tls)
  - [Token file](#token-file)
  - [Trust and Docker isolation](#trust-and-docker-isolation)

## Token file

When `GIT_TOKEN` is absent, the default file is `~/.config/git/token`. `GIT_TOKEN` selects a file path, not a token value. A quoted `~/...` expands using the current user's home. An explicit empty value is an error. The file must be readable, user-owned, private (mode 600 or 400), nonempty, and contain one token without embedded whitespace. The tool never creates, copies, moves, changes, or prints it. Read [Gitea migration](gitea-migration.md) before upgrading.

Use Gitea `write:repository` and `write:package` scopes restricted to approved targets where supported. Check the deployed version's Swagger/token documentation for any additional read scope required by version/repository/package endpoints; do not grant blanket administrator access. Package permissions are owner-scoped, not isolated by repository links. Set only `GIT_USERNAME` to the token account login, including for organization-owned packages; this does not set Git author identity. The repository owner is never assumed to be the account login. `GIT_USER`, `GITEA_TOKEN`, `GITEA_USERNAME`, `GITEA_USER`, `FORGEJO_TOKEN`, `FORGEJO_USERNAME`, and `FORGEJO_USER` are rejected whenever present, even empty, before file access. There are no aliases or old-default fallback.

```sh
GIT_USERNAME=your-login ./scripts/release.sh publish
GIT_USERNAME=your-login GIT_TOKEN="$HOME/.config/gitea/other-token" ./scripts/release.sh resume
```

Do not inject raw token contents into `GIT_TOKEN`. It selects a file, not a secret value. Keep credentials out of Git, `.env`, Compose, hook arguments, Docker build arguments, image layers, release descriptions, and checkpoints. BuildKit secret files are an explicit separate adapter setting when builds need their own protected credentials.

## Trust and Docker isolation

Gitea API and registry reads use Python's default system TLS trust (including its standard `SSL_CERT_FILE`/`SSL_CERT_DIR` configuration). Registry Bearer token challenges must remain on the configured HTTPS origin. HTTP redirects are rejected, so credentials are never forwarded to external storage or token servers. Server setups relying on external blob redirects are deliberately unsupported. Manifest/config reads are bounded; image layers are not downloaded by verification.

Git, the Docker CLI, the daemon, and BuildKit need their own configured TLS/SSH trust. A successful API call does not configure daemon or builder trust. The release tool does not install certificates, disable TLS, change daemon settings, or install emulation. Ask the host administrator to follow [platform preparation](platform-preparation.md) for AMD64/ARM64 binfmt setup or provide native builder nodes; no privileged setup runs automatically.

Docker login uses password-stdin and an automatically removed private temporary configuration with no inherited auths or credential helpers. A nonempty target-registry auth inventory prevents implicit native-helper autodetection. Context connection metadata/TLS files are copied privately so named builder-node contexts remain available; a selected-context export/import fallback supports configurations without that directory. The selected Buildx state and user plugin path remain available. Existing `DOCKER_HOST`, TLS, context, and builder choices are preserved. Context files may contain TLS keys and stay inside the private temporary directory. Uncatchable process termination can leave that directory; inspect and remove only a verified abandoned auth directory, never broad temporary paths. Run only one publisher across hosts.
