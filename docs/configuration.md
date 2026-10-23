# Configuration and hooks

- [Configuration and hooks](#configuration-and-hooks)
  - [Configuration](#configuration)
  - [Version sources](#version-sources)
  - [Hooks and image suites](#hooks-and-image-suites)

## Configuration

Copy an example to a future consumer's `release.json` only during an explicitly approved adoption task. Generic examples use invalid endpoints; the explicitly opt-in Ubuntu fixture targets the approved real project. Run `scripts/release.sh validate` to validate without credentials or remote operations.

Schema 2 requires `gitea` (credential-free HTTPS origin), `registry` (same host/port), `repository` (owner/repository), `version`, `release_notes` (safe relative Markdown path), and nonempty `images`. Version 0.2.4 deliberately tightens the input contract without changing configuration schema: older consumers must add their own committed notes before publication. Schema 1 and retired or mixed `forgejo` keys are rejected before credential access; see [migration](gitea-migration.md). `source_push` defaults to false. `checks` contains command argument arrays executed in the project root. Both effective Git fetch and push destinations must identify this exact repository; SSH port is independent of registry HTTPS port. Git rewrites are resolved by `git remote get-url` before identity validation.

`release_notes` is read from the captured source commit as a regular UTF-8 blob of at most 64 KiB. Require `# Release v<requested-version>` as its first line, followed by project changes. Normalize CRLF/CR to LF and trailing newline count only. The normalized text is the entire public description; no image catalog, generated Docker commands, hidden metadata, attachments, or provenance footer is appended. Curate notes for the consuming project; `examples/project-notes.md` is only a replace-before-publication sample. Validation checks path safety without credentials or Git/network access; publication validates committed bytes before remote writes.

`link_packages` and `remove_local_images` are booleans defaulting to false. The Ubuntu fixture explicitly enables both. Linking affects every version of an owner-scoped package; [package linking](package-linking.md) explains scoped approval and the operator exclusion window. [Local image removal](local-images.md) explains durable provenance, daemon binding, safe skips, and mandatory non-pruning removal. Neither setting grants remote deletion authority.

Each image requires a unique simple `name` and nonempty `platforms` selected from `linux/amd64` and `linux/arm64`. `context` defaults to `.`, `dockerfile` defaults to `Dockerfile`, `dependencies` defaults to an empty list, and `retain_version` defaults to false. Names are an exact package deletion allowlist; nested image namespaces are not supported in schema 2. `retain_version: true` adds only the current `vMAJOR.MINOR.PATCH` registry alias alongside `latest`. Old version aliases are eligible for verified cleanup. Dependency cycles and unknown parents are rejected.

Default builds use Buildx, source/version/revision OCI labels, an ignored metadata file, and release-unique `rt-<run-id>-<image>` staging tags. Build contexts come from a private snapshot of the captured Git commit, excluding ignored local credentials, release state, and `.git` metadata. This internal Git source export is not an image archive or release attachment. Submodule/LFS materialization is not automatic; an application needing it requires a separately reviewed adapter. `secrets` may contain `{"id":"name","file":"/protected/path"}` entries, passed as BuildKit secret mounts, never build arguments. Relative secret paths resolve from the project root; keep secret files outside source/build contexts. Do not place tokens in configuration.

`test_http` is exclusively for in-process unittest fixtures on loopback; the CLI refuses it. Configuration is trusted executable project input, not a sandbox for untrusted repositories or hooks.

## Version sources

- `{"kind":"package","path":"package.json"}` reads the version and requires both root lockfile versions to match.
- `{"kind":"file","path":"VERSION"}` reads a committed file.
- `{"kind":"explicit"}` requires `--tag vMAJOR.MINOR.PATCH` for publication and recovery.
- `{"kind":"command","command":["python3","hooks/cargo_version.py","package-name"]}` reads a command's single version output; a locked Cargo example is included.

Versions must be stable `MAJOR.MINOR.PATCH`, optionally prefixed with `v`. Prerelease publication is not supported; existing prerelease records are preserved. Unknown current published identities require a separately reviewed migration, not automatic inference. Do not use mutable `latest`, timestamps, or listing order as a source version.

## Hooks and image suites

Commands are argument arrays with an explicit working directory at the project root. Shell evaluation occurs only if a configuration deliberately invokes a shell. The engine strips exact supported and rejected credential names listed in [credentials](credentials.md) from subprocess environments, preserves native Git settings such as `GIT_SSH_COMMAND` and author/committer variables, retains Docker context/builder settings, and does not print raw command failures.

Optional per-image `build` replaces the default builder. It receives `RELEASE_INPUT_JSON` with schema, captured commit, version, source URL, private `source_root` snapshot directory, exact staging reference, required platforms, pinned parent image references, and metadata-file destination. It must build from that snapshot, push the staging identity, and preserve OCI source/version/revision labels. Write Buildx's `containerimage.digest` metadata when possible; the engine independently verifies the registry graph and runnable configurations. A build hook with dependencies must consume the supplied parent digests, not ambient `latest` tags. Hooks are trusted adapters; their Dockerfile semantics cannot be proven by checking labels alone.

Verification compares the complete runnable platform multiset with `platforms`, rejects extra or duplicate images, and checks source/version/revision labels on every runnable member. Unsupported architectures do not disappear from verification. Descriptor OS/architecture and optional matching variant evidence must agree with the configuration. OCI and Docker schema-2 image manifests/configurations and explicitly typed nested indexes are supported; missing or contradictory media types/platforms fail closed.

Supported non-runnable evidence is deliberately narrow. Buildx attestations require `vnd.docker.reference.type: attestation-manifest`, a known image digest in `vnd.docker.reference.digest`, an `unknown/unknown` descriptor and configuration, and nonempty `application/vnd.in-toto+json` layers. An optional manifest subject must match that image. OCI image-manifest artifacts require a nonempty `artifactType`, an `application/vnd.oci.empty.v1+json` configuration containing `{}`, and no contradictory platform/attestation descriptor. A lone annotation, an `unknown` architecture, or an artifact marker on a runnable image never exempts it. Unknown encodings stop publication; this is not universal OCI artifact support. Subject-only images remain reachable dependencies rather than additional published platform members.

Optional `verify` receives schema, immutable `image` reference, commit, version, and platforms. It must exit successfully only after project-specific checks pass; it may run again during resume. It must not mutate source, tags, release records, or aliases. Add runtime/sandbox/platform verification appropriate to the application rather than treating advertised builder capability as execution proof.

With local removal enabled, the input also contains `local_images` with schema 1, the run identifier, exact immutable `reference`, and private `journal` path. The engine checkpoints the pull intent before invocation. A cooperating hook durably writes `{schema, run, reference, observations}`, where `observations` maps declared platform strings to inspected local `sha256:` image IDs, after each successful pull. Use atomic rename and file/directory fsync, mode 600, and at most 64 KiB; do not log this file or include credentials. The Ubuntu hook implements this protocol. Registry index digests are not assumed to equal local image IDs. Opaque custom hooks remain supported, but unproven local effects are reported and skipped rather than deleted. See the complete [local ownership contract](local-images.md).

`examples/suite.json` and `examples/hooks/dependent_build.py` show a synthetic base/child suite. The child Dockerfile must declare `ARG PARENT` followed by `FROM ${PARENT}`. Every image is built/verified before any final alias promotion. No actual tool-suite project is modified or automatically supported by this example.
