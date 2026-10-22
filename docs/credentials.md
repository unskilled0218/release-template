# Credentials and TLS

- [Credentials and TLS](#credentials-and-tls)
  - [Token file](#token-file)
  - [Trust and Docker isolation](#trust-and-docker-isolation)

## Token file

The default is `FORGEJO_TOKEN=~/.config/forgejo/forgejo-token`, interpreted as a file-path setting when the variable is absent. A quoted `~/...` expands using the current user's home. An explicit empty value is an error. The file must be readable, user-owned, private (mode 600 or 400), nonempty, and contain one token without embedded whitespace. The tool never creates, changes, or prints it.

The token needs repository write and package write access to the exact configured target. Set `FORGEJO_USERNAME` to its account login, including for organization-owned packages. `FORGEJO_USER` is a compatibility alias; conflicting values fail. The repository owner is never assumed to be the account login.

```sh
FORGEJO_USERNAME=your-login ./scripts/release.sh publish
FORGEJO_USERNAME=your-login FORGEJO_TOKEN="$HOME/.config/forgejo/other-token" ./scripts/release.sh resume
```

Unlike the read-only `home-web` reference, do not inject raw token contents into `FORGEJO_TOKEN`. It selects a file, not a secret value. Keep credentials out of Git, `.env`, Compose, hook arguments, Docker build arguments, image layers, release descriptions, and checkpoints. BuildKit secret files are an explicit separate adapter setting when builds need their own protected credentials.

## Trust and Docker isolation

Forgejo API and registry reads use Python's default system TLS trust (including its standard `SSL_CERT_FILE`/`SSL_CERT_DIR` configuration). Registry Bearer token challenges must remain on the configured HTTPS origin. HTTP redirects are rejected, so credentials are never forwarded to external storage or token servers. Server setups relying on external blob redirects are deliberately unsupported. Manifest/config reads are bounded; image layers are not downloaded by verification.

Git, the Docker CLI, the daemon, and BuildKit need their own configured TLS/SSH trust. A successful API call does not configure daemon or builder trust. The release tool does not install certificates, disable TLS, change daemon settings, or install emulation. Ask the host administrator to prepare binfmt or native builder nodes when required; no privileged setup runs automatically.

Docker login uses password-stdin and an automatically removed private temporary configuration with no inherited auths or credential helpers. A nonempty target-registry auth inventory prevents implicit native-helper autodetection. Context connection metadata/TLS files are copied privately so named builder-node contexts remain available; a selected-context export/import fallback supports configurations without that directory. The selected Buildx state and user plugin path remain available. Existing `DOCKER_HOST`, TLS, context, and builder choices are preserved. Context files may contain TLS keys and stay inside the private temporary directory. Uncatchable process termination can leave that directory; inspect and remove only a verified abandoned auth directory, never broad temporary paths. Run only one publisher across hosts.
