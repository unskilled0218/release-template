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

1. Follow [configuration and credentials](bash-configuration.md). Replace copied sample Dockerfile, target, remote, and account settings.
2. Run application tests. Set root `VERSION` and matching release notes, commit all inputs, and push clean `main`. Publication does not push source.
3. Exclude other publication/package writers, UI actions, and in-flight requests through completion. Keep checkout/tool configuration and plugin files unchanged; the local lock cannot enforce this elsewhere.

## Check prerequisites

Install Bash, Python 3.11+, Git, curl, Docker Buildx, and standard Linux utilities; ensure filesystem locks work. No jq, Node, or pip packages are needed. The command checks tools before builder access but installs nothing.

Provision a [private token and separate Git authentication](bash-configuration.md#credentials-and-prerequisites). Keep HTTPS trust enabled and tokens out of arguments, history, Git, and logs.

```sh
./scripts/release.sh --validate
```

Validation checks local settings/version/paths only, without credentials, Docker, locks, or network access. It does not prove publication permissions.

## Check platform readiness

Confirm the Docker context/host and Buildx builder. Publication runs `docker buildx inspect --bootstrap` and requires advertised `linux/amd64` and `linux/arm64`. Bootstrap may start the builder, but does not configure host emulation.

Prefer native nodes. If emulation is needed, arrange administrator-approved [platform preparation](platform-preparation.md) on the correct hosts. Advertising does not prove application build or runtime success; runtime checks are separate.

## Check service readiness

There is no network-only preflight mode. Run publication only when ready for writes. Before a fresh build, bounded reads check:

- Docker: builder access and advertised platforms.
- Git: [matching fetch/push destinations](bash-configuration.md#files-and-setup) and remote `main` at the captured commit.
- Gitea: complete authenticated tag/release inventories for the requested version.
- Registry: predecessor/staging manifests and matching evidence; login precedes build or staging reuse.

Failed or incomplete evidence stops publication. Successful reads/login do not guarantee later write permissions or availability. Package permissions, server-version gates, and association evidence are checked **after publication** under the [association rules](bash-publication.md#package-association), not as early-readiness guarantees.

## Build and publish

```sh
./scripts/release.sh
```

The command reuses verified staging or builds both platforms from committed source with `docker buildx build --push`. Staging may exist even when the build reports failure.

It verifies the immutable image, pushes the annotated tag, promotes the digest without rebuilding, creates the notes-only release, and verifies publication and package association. See [publication and recovery](bash-publication.md) for guards and limits. No image deletion, retention, rollback, reassignment, or host setup runs automatically.

Completed matching publications are verified without rebuilding or republishing; only a missing package link may be completed. Partial/ambiguous states stop under the [retry rules](bash-publication.md#retry-states).

## Progress and verification

`Release progress:` milestones appear on stderr before major stages. They report staging reuse and skipped promotion, but are not live build logs, heartbeats, or percentages. A long build may remain at one milestone until completion or timeout.

Raw command output, server bodies, credential paths, and auth files are not relayed. Build completion follows immutable-image verification. Only final `Publication verified` announces success, with version, immutable image, latest alias, and release URL.

Failures print stage-specific next steps, including early lock/storage failures. They distinguish no writes by this invocation from possible accepted writes; older remote state may exist in either case. Inspect uncertain state without rollback.

Keep the original checkout/pin for historical retries: changed script hashes cannot adopt old publications. Passing local tests is not live approval; see [known limits](bash-publication.md#known-limits).

## Troubleshooting

- **Missing tools:** install the named command on `PATH`, or ask your administrator. Docker needs Buildx.
- **Docker access:** check daemon, socket permissions, context/host, TLS, and Buildx. Emulation setup is not a connectivity fix. Review [Docker config restrictions](bash-configuration.md#credentials-and-prerequisites).
- **Lock/storage:** wait for the lock owner; check permissions and filesystem support. Never delete/bypass an active lock. Check writable `TMPDIR`, free space, and permissions; invalid storage is not silently replaced.
- **Missing platform:** use native nodes or approved [emulation setup](platform-preparation.md). Do not silently change hosts or drop an architecture.
- **Source/notes:** check `git status`, branch, remotes, `VERSION`, and committed notes. Inspect any partial publication before changing inputs.
- **Credentials/services:** check token ownership/mode, resource permissions, separate Git authentication, DNS, and trusted HTTPS. Do not expose tokens/paths or weaken trust/permissions.
- **Build/push:** check Dockerfile, architecture dependencies, builder resources, and registry permissions. Gather application logs separately in an approved environment without release credentials. Inspect possibly accepted staging before retrying.
- **Partial publication:** follow [retry states](bash-publication.md#retry-states). Preserve accepted objects; do not force adoption by deletion, rollback, tag rewriting, reassignment, or changed inputs. Manual completion needs review.

## Recommendations

Prefer native ARM64 nodes and separately approved runtime checks when both architectures matter. Application tests, host preparation, and writer exclusion remain operator responsibilities, not automatic release steps.
