# Release process

- [Release process](#release-process)
  - [Prepare the project](#prepare-the-project)
  - [Check prerequisites](#check-prerequisites)
  - [Check platform readiness](#check-platform-readiness)
  - [Check service readiness](#check-service-readiness)
  - [Build and publish](#build-and-publish)
  - [Progress and verification](#progress-and-verification)
  - [Troubleshooting](#troubleshooting)
  - [Recommendations](#recommendations)

## Prepare the project

1. Follow [configuration and credentials](bash-configuration.md) when copying this template. Replace its sample Dockerfile, repository/image targets, Git remote, and account settings before running publication. No other project is updated automatically.
2. Run your application's tests separately. Set root `VERSION` and prepare the configured committed release notes with the matching heading. Commit all release inputs and push clean `main` to the configured repository; the release command does not push source.
3. Arrange exclusive publication and package-association access through completion, including other checkouts, UI actions, and in-flight requests. The checkout lock alone does not exclude those writers.

## Check prerequisites

Check installed tools before invoking Docker or contacting servers: Bash, Python 3.11+ with its standard library, Git, curl, Docker with Buildx, standard Linux utilities, and working local filesystem locks. There are no jq, Node, or pip dependencies. The command checks Python and availability of Git/Docker/curl; builder inspection checks usable Buildx. It does not install missing tools or certify every tool version.

Provision the private token and independent Git authentication as described in [credentials and prerequisites](bash-configuration.md#credentials-and-prerequisites). Keep Git/curl/Docker HTTPS trust enabled. Do not put tokens in arguments, shell history, Git, or copied project files.

```sh
./scripts/release.sh --validate
```

Validation checks configuration, version, and local paths only. It does not read credentials, inspect Docker, lock the checkout, test connectivity, prove publication permissions, or write remote objects.

## Check platform readiness

Confirm the intended Docker context/host and selected Buildx builder before publication. The release command runs `docker buildx inspect --bootstrap` and requires advertised `linux/amd64` and `linux/arm64` support. Bootstrap may start the selected builder; it does not configure host emulation. A working Docker connection is required before platform advertising can be checked.

Use native builder nodes where possible. If emulation is needed, only an authorized administrator may run this optional preparation on the relevant daemon host:

```sh
docker run --privileged --rm tonistiigi/binfmt --install amd64,arm64 && docker buildx inspect --bootstrap
```

This changes host kernel handlers and requires privileged access. Verify the selected host first, especially with remote builders. The release command never runs it automatically. See [platform preparation](platform-preparation.md) for host scope and separately approved runtime checks.

Advertised platforms do not prove that your application's Dockerfile compiles on both architectures or that containers execute on the runtime host. The actual build and immutable image checks establish different evidence; native/emulated runtime execution requires separate verification.

## Check service readiness

Run `./scripts/release.sh` only when ready to publish. There is no separate network-only preflight mode. Existing bounded reads establish the following evidence before the fresh build:

- Docker: selected builder inspection/bootstrap and context selection establish builder access and advertised platforms, not application build success.
- Git: effective fetch/push destinations must match the configured target; `git ls-remote` must show remote `main` at the captured source commit. Independent Git authentication must work.
- Gitea: complete authenticated tag/release inventories classify the requested version before staging lookup or publication writes. Failed, malformed, oversized, or incomplete evidence stops the command.
- Registry: predecessor and staging manifest reads verify registry access and matching evidence. Login precedes a fresh build or staging reuse; read access and login do not prove that a later push will be authorized.

Ping, open ports, and one successful HTTP response are not substitutes for these service-specific checks. Reads cannot guarantee every future write permission or continued service availability. Repository/package access, stable Gitea 1.25.x authority for a new package link, and exact association evidence are checked after publication under the existing [package association rules](bash-publication.md#package-association); they are not early-readiness guarantees.

## Build and publish

```sh
./scripts/release.sh
```

For a fresh version, the command reuses verified staging evidence or builds both platforms from a private committed snapshot. `docker buildx build --push` builds and pushes the staging image together; there is no separate local build followed by a later independent push command. Staging content may exist even if the build command reports failure.

After immutable image and build-metadata verification, the command publishes the exact annotated Git tag, promotes the verified digest to `latest` without rebuilding, creates the notes-only Gitea release, verifies publication, associates the configured package, and rechecks publication and association. See [publication sequence and recovery](bash-publication.md) for exact guards, retry classifications, and resource limits. There is no automatic image deletion, retention, rollback, package reassignment, or host setup.

Completed matching publications take a verification path with no build, staging lookup, promotion, tag push, or release POST. Only a missing package association may be completed under the existing scoped rules. Tag-only/release-only startup states stop for inspection instead of automatic repair.

## Progress and verification

`Release progress:` messages go to stderr before each major stage, including builder/platform checks, source/notes, credentials, remote inventory, staging lookup, login, build/staging push, tag publication, promotion, release creation, package association, and final verification. Reused staging and already-matching promotion are reported explicitly. Completed retries report verification rather than announcing a new build.

These are milestone logs, not live Docker build output, continuous heartbeats, or percentage estimates. A long build can remain at the same milestone until completion or timeout. Raw command output, server bodies, credential paths, and auth files are not relayed; shell tracing stays disabled. Build completion is reported only after immutable image and metadata verification. Final stdout retains `Publication verified` with the version, immutable image, `latest` alias, and release URL; only that summary announces successful publication.

Failures print fixed stage-specific next steps. Before publication writes, messages say that this invocation sent none, while noting that older remote state may still exist. After a possible staging/publication write, they warn that publication may be incomplete or uncertain and direct you to inspect exact remaining objects without rollback.

Changes to release scripts alter annotation-bound script identity. Keep the original checkout/pin for historical retries; changed scripts cannot adopt publications bound to an older script hash. Passing local tests is not live publication approval. The [known publication warnings](bash-publication.md#known-limits) remain unresolved.

## Troubleshooting

- Missing tools: install the named command and make it available on `PATH`; Docker also requires Buildx. Ask your environment administrator to install prerequisites if you lack access. Re-run local validation after setup; do not change host configuration automatically.
- Unusable Docker/builder: check daemon availability, socket permissions, selected context or `DOCKER_HOST`, TLS metadata, and Buildx installation. Diagnose access before changing emulation. Do not use privileged binfmt setup as a remedy for a generic connection failure. Config-local Buildx-plugin discovery remains a [known limit](bash-publication.md#known-limits).
- Missing ARM64/AMD64 advertisement: check the selected builder's nodes and advertised platforms. Use native nodes or arrange administrator-approved emulation as described in [platform preparation](platform-preparation.md). Do not silently select a different host or drop an architecture.
- Dirty/unpushed source or invalid notes: review `git status`, current branch, effective remotes, root `VERSION`, and committed notes. Commit and push the intended source separately before a new release. If partial publication already exists, inspect its captured identity before changing release inputs.
- Credential failures: check token ownership, permissions, location outside the project, account resource permissions, and independent Git authentication. Do not print tokens or credential paths into support logs; do not weaken file permissions or HTTPS checks to continue.
- DNS/TLS/service failures: check resolution, network routing, service availability, trusted certificates, and account access for the selected Git/Gitea/registry endpoints. API access and registry access are separate; a successful inventory does not prove push or link permissions. Never bypass trust or follow an unexpected auth redirect as a workaround.
- Build/staging-push failure: review your Dockerfile, architecture-specific application dependencies, builder resources, and registry push permissions. No raw compiler/build logs are streamed by this workflow. Application-specific diagnostics must be gathered separately in an approved environment without release credentials. Staging may have been accepted; inspect exact state before retrying the unchanged identity.
- Partial or ambiguous publication: follow [retry states](bash-publication.md#retry-states). A failed response can follow an accepted image, tag, alias, release, or link write. Preserve those objects. Do not blindly retry, rewrite tags, delete evidence, roll back aliases, reassign packages, or change source/scripts to force adoption. Manual completion needs separate review.

## Recommendations

Run application tests before committing release source, prefer native ARM64 build nodes where practical, store credentials outside the checkout, and maintain exclusive writers through final verification. Review copied target settings and release notes for every adopting project. Consider separately approved runtime checks when execution on both architectures matters. These recommendations are operator responsibilities, not extra automatic checks or installation steps.
