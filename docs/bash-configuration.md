# Bash release configuration

- [Bash release configuration](#bash-release-configuration)
  - [Files and setup](#files-and-setup)
  - [Settings](#settings)
  - [Credentials and prerequisites](#credentials-and-prerequisites)

## Files and setup

Copy and review `scripts/release.sh`, `scripts/release-common.sh`, `scripts/release-data.py`, and `scripts/release.json`. Add a root `Dockerfile`, `.dockerignore`, `VERSION`, and committed Markdown release notes. Ignore `.template-operation.lock`, `.release-template/`, and `.template-transaction/`.

Replace the sample Hello World Dockerfile, Git remote, and target settings before publishing a copied template. This repository targets `dev/container-release-template` and `git.lan/dev/container-release-template-hello`. Commit the setup and push clean `main`; publication does not push source or update other projects.

`origin` must have exactly one effective push URL matching the target. Checks use `git remote get-url --push --all origin`, including rewrites and fallback URLs. Multiple entries, even duplicates, are refused. The first effective fetch URL must also match. Keep Git configuration unchanged and exclude other writers through completion; repeated checks are not atomic locks.

Follow the [release checklist](release-process.md) before publication.

## Settings

`scripts/release.json` accepts exactly these schema 1 fields:

- `schema`: `1`.
- `gitea`: credential-free HTTPS origin.
- `repository`: `owner/repository`.
- `image`: `host/owner/name`, with matching host/owner scope.
- `username` and `token_file`: login and private token path.
- `notes`: relative regular-file path.
- `platforms`: `["linux/amd64", "linux/arm64"]`.

Use simple lower-case repository/image names; nested image namespaces are unsupported. Unknown/duplicate fields, control characters, traversal, symlinks in active paths, and inconsistent scopes are refused. Settings are JSON, not shell code.

Root `VERSION` is `MAJOR.MINOR.PATCH`, without leading zeroes and at most 16 characters. The Git tag is `v<version>`. Notes must be committed UTF-8, at most 64 KiB, beginning `# Release v<version>`. After newline normalization, they become the entire public release body. Image identity is stored separately in the annotated Git tag.

- `--validate` checks local settings/version/paths without credentials, state, Docker, network calls, or remote checks.
- `--help` needs only Bash.
- No arguments publishes; all other arguments are refused before external effects.

The script uses its own project root regardless of the calling directory. Old installation/checkpoint markers stop publication; historical transactions require their preserved original checkout/pin. No installer, updater, or migration is provided.

## Credentials and prerequisites

Store the token outside the project in a user-owned, readable, non-symlink file with mode 0600 or 0400. Default: `~/.config/git/token`. `GIT_TOKEN` overrides the file path, never the token value; `GIT_USERNAME` overrides the login. Never put tokens in Git, `.env`, shell history, arguments, or logs.

The account/token needs repository and package read/write access, release creation, and target repository package-unit write permission. Git authentication is separate. Token scopes and a supported server version do not grant missing account permissions.

New package links require stable Gitea `1.25.x` or exact stable `28.2.0`; correct existing links stay read-only without a version check. See [package association](bash-publication.md#package-association) for API contracts, permissions, and mandatory exclusion of other association writers, including UI actions and in-flight requests.

Runtime requires Linux/POSIX, Bash, Python 3.11+ standard library, Git, curl, Docker Buildx, standard utilities, and filesystem locks. No jq, Node, or pip packages are needed. The builder must advertise both platforms before remote Git/auth/build operations; this does not prove runtime execution. See [platform preparation](platform-preparation.md).

Keep HTTPS trust enabled. Authenticated curl ignores ambient configuration and does not follow redirects; registry Bearer realms must be same-origin. Docker authentication uses a private directory without inherited credentials/helpers. Normal exit, failure, and handled signals remove only run-owned temporary files. SIGKILL cannot clean up; inspect leftovers securely, without broad cache deletion.

Private authentication preserves Docker selection:

- Host-only selection keeps `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, and `DOCKER_CERT_PATH`; it does not add a default context. Explicit contexts, including `default`, retain precedence.
- Config-selected named contexts retain endpoint/TLS metadata. Empty or unset `DOCKER_CONFIG` uses `$HOME/.docker`.
- Explicit Buildx state paths remain selected; default state stays under the original Docker directory. Relative paths retain caller-working-directory semantics.
- Plugin search order is original `cliPluginsExtraDirs`, original config-local `cli-plugins`, then native system directories. Relative extras become absolute; spaces and symlinks are supported. Binaries and unrelated auth/helpers/proxies/aliases are not copied.

Original Docker config must be a regular JSON object within 1 MiB. Missing config uses defaults; unreadable, malformed, duplicate-key, oversized, or wrong-shaped config is refused. Only canonical `cliPluginsExtraDirs` is accepted: absent/null means no extras; otherwise use a list of nonempty, control-free paths. Unlike Docker, alternate casing is refused. Diagnostics do not relay paths or config contents.

Keep plugin files and tool configuration unchanged through publication: preserved search order does not pin executable contents. Discovery follows reviewed Docker CLI v29.0.0 [manager code](https://github.com/docker/cli/blob/v29.0.0/cli-plugins/manager/manager.go), not native deployment certification.

Setup failures give fixed next steps. Never delete or bypass an active checkout lock. Check permissions, filesystem locks, and a writable `TMPDIR` parent with enough space. Invalid caller-selected temporary storage is refused, not silently replaced. No publication writes are sent by that invocation, but older remote state may remain.
