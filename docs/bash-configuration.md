# Bash release configuration

- [Bash release configuration](#bash-release-configuration)
  - [Files and setup](#files-and-setup)
  - [Settings](#settings)
  - [Credentials and prerequisites](#credentials-and-prerequisites)

## Files and setup

For a newly approved consumer, copy/review `scripts/release.sh`, `scripts/release-common.sh`, `scripts/release-data.py`, and `scripts/release.json`. Add your root `Dockerfile`, `.dockerignore`, `VERSION`, and committed Markdown release notes. Ignore `.template-operation.lock`, `.release-template/`, and `.template-transaction/`. Commit the complete setup and push its clean `main` before publication. No managed installation or network self-update runs during release.

The sample root Dockerfile runs Ubuntu's `echo "Hello World"`. It is not your application's Dockerfile. This repository explicitly configures `dev/container-release-template` and `git.lan/dev/container-release-template-hello`; do not publish a copied template until you have changed its target settings and Git remote.

## Settings

`scripts/release.json` has exactly schema 1 fields: `schema`, credential-free HTTPS `gitea` origin, `repository` as `owner/repository`, full `image` as `host/owner/name`, `username`, `token_file`, relative regular-file `notes`, and `platforms` as `["linux/amd64", "linux/arm64"]`. The host/owner scopes must agree. Simple lower-case repository/image names are supported; nested image namespaces are not. Unknown/duplicate fields, controls, traversal, symlinks in active paths, and inconsistent scopes are refused. Configuration is JSON data, never executable shell code.

Root `VERSION` supplies `MAJOR.MINOR.PATCH` without leading zeroes, at most 16 characters; the Git tag is derived as `v<version>`. Notes must be a committed UTF-8 regular blob, at most 64 KiB, beginning `# Release v<version>` followed by project updates. Narrow newline normalization is applied; the resulting text is the entire public release body. Image/digest identity lives separately in a distinct annotated Git tag.

`./scripts/release.sh --validate` checks local settings/version/paths without reading credentials, creating state, contacting services, or invoking Docker. `--help` needs only Bash. No arguments selects publication; other arguments, including old subcommands and configuration flags, are refused with current usage before credentials or external effects. Invocation from another directory still selects the root containing the script. The old Python CLI, examples, and installer/updater are not shipped. Historical transactions require their preserved original checkout/pin; old installation/checkpoint markers remain refusals, never migration authority.

## Credentials and prerequisites

Use a non-symlink, user-owned, readable mode-0600 or mode-0400 token file outside the project. Default: `~/.config/git/token`; `GIT_TOKEN` optionally overrides the file path, never the token value. Optional `GIT_USERNAME` overrides the configured login. No inline environment assignment is needed for the configured default. Provision the token privately, never in Git, `.env`, shell history, command arguments, or this documentation. It needs the intended repository/package permissions; independent Git authentication is also required.

Runtime requires Bash, Python 3.11+ standard library, Git, curl, Docker Buildx, and standard Linux utilities. There is no jq, Node, pip dependency, or separate engine package. Python handles strict JSON/UTF-8, hashing, bounded pipes, locks, private auth preparation, and source archive validation. Bash owns the publication sequence. Root `VERSION` is the only project version source; no module-version metadata is required.

Keep HTTPS trust enabled for Git/curl/Docker. Authenticated curl requests disable ambient curl configuration and do not follow redirects; registry bearer-token realms must be same-origin. Docker uses a private minimal auth directory with no inherited credential helpers, preserving the selected context and builder connection. Normal exit/failure/signals remove only the run-owned private temporary directory. SIGKILL cannot run cleanup; inspect any leftover private temporary directories securely, not with broad cache deletion.

Auth isolation captures the original connection selection before replacing `DOCKER_CONFIG`. A host-only selection keeps `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, and `DOCKER_CERT_PATH` without newly exporting a default context over it; empty context values also remain unselected. An explicitly selected context retains its precedence, including explicit `default`. A non-default context selected through the original config is carried into the private environment with its required endpoint/TLS metadata, never with the original registry auth/helper inventory. An unset or empty `DOCKER_CONFIG` uses the caller's home Docker directory. Explicit buildx state paths are retained; default buildx state remains rooted in the original Docker directory, not the temporary auth directory. Relative connection paths retain the caller's working-directory semantics. This does not preserve config-local plugin executable discovery: see the unresolved [known limits](bash-publication.md#known-limits). Local fixtures model connection precedence and metadata use; they do not certify native plugin discovery, daemon routing, or TLS behavior.

The builder must advertise both platforms before remote Git/auth/build operations. This does not prove emulated runtime execution. Host preparation needs separate administrator action; the release command never installs privileged emulation support.
