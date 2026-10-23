# Gitea migration

- [Gitea migration](#gitea-migration)
  - [Breaking configuration changes](#breaking-configuration-changes)
  - [Credentials and package authority](#credentials-and-package-authority)
  - [Checkpoint and release identities](#checkpoint-and-release-identities)
  - [Fresh deletion verification](#fresh-deletion-verification)
  - [Separate adoption approval](#separate-adoption-approval)

## Breaking configuration changes

Version 0.2.0 supports Gitea only. Configuration schema 1 and any `forgejo` key, including mixed old/new keys, fail before credentials or network clients. There is no provider compatibility alias. The origin remains credential-free HTTPS and must match the registry host/port. Keep all other version, image, hook, secret, and source-push settings unchanged unless separately reviewed.

Before, in a schema-1 configuration:

```json
{"schema": 1, "forgejo": "https://forgejo.example.invalid", "registry": "forgejo.example.invalid"}
```

After, in a complete schema-2 configuration (these are origin fragments, not complete runnable files):

```json
{"schema": 2, "gitea": "https://gitea.example.invalid", "registry": "gitea.example.invalid"}
```

Use the [complete examples](../examples/) and credential-free `./scripts/release.sh validate`. Validation does not require login or read a token.

## Credentials and package authority

The former default `~/.config/forgejo/forgejo-token` and `FORGEJO_*` settings are retired. The only supported settings are `GIT_TOKEN` (protected token-file path) and `GIT_USERNAME` (explicit authentication account, not Git author). The new default path is `~/.config/git/token`. An explicit empty path/login fails. `GIT_USER`, `GITEA_TOKEN`, `GITEA_USERNAME`, `GITEA_USER`, `FORGEJO_TOKEN`, `FORGEJO_USERNAME`, and `FORGEJO_USER` fail whenever present, including empty values, before file access. Remove these settings from the release environment; do not retain them as aliases.

```sh
GIT_USERNAME=your-login GIT_TOKEN="$HOME/.config/gitea/approved-token" ./scripts/release.sh publish
```

An operator may explicitly select an existing protected file only if it contains a valid Gitea token. The tool never copies, moves, rewrites, creates, or searches for credentials. It never interprets `GIT_TOKEN` as a raw secret. Follow [credentials and TLS](credentials.md) for file protections and scoped `write:repository`/`write:package` permissions; check any additional read scope required by the installed version rather than granting blanket admin access.

Gitea packages belong to owners, not repositories. Push success, matching image names, source labels, or repository existence alone do not grant deletion authority. Missing/foreign links protect the entire reachable graph and report cleanup incomplete. Repository linking changes the whole package and requires separate operator-controlled adoption approval. No automatic linking or reassignment is performed. Exact credential names are stripped from subprocess environments; unrelated native Git SSH and author/committer settings remain available.

## Checkpoint and release identities

The outer checkpoint schema, operation IDs, retirement metadata, publication marker, and bootstrap protocol remain unchanged. Schema-2 configuration changes the canonical configuration hash; a new template pin also changes identity. Old-config or old-pin checkpoints are refused without rewriting them. Preserve original checkpoints, retirement schedules, release metadata, and provenance for separately reviewed recovery. Do not delete state, rewrite identities, roll source backward, or use vulnerable old cleanup code as a workaround. No cross-revision adoption command exists.

Recognized imported release identity metadata remains readable regardless of old prose. New descriptions name Gitea. Imported aliases, source commits, and image identities still need exact predecessor and current-source checks. Unknown records are an adoption problem, not permission to bypass forward-only publication or first-publication guards. Same-revision schema-2 publish/resume/cleanup remains supported. Use the existing [pinned installer](installation.md); stable launcher bytes are unchanged.

## Fresh deletion verification

Old Forgejo schema-1 or `server_major: 17` evidence cannot enable deletion, even at a renamed host. Fresh schema-2 evidence must attest `product: "gitea"`, the exact origin and full server version, a distinct disposable repository, operator/date metadata, and all required successful deletion/pullability observations. Full `MAJOR.MINOR.PATCH` strings may include prerelease/build suffixes, which are retained and compared exactly. Patch/build drift requires reverification. Major-only values, malformed responses, API failures, wrong product/origin, and absent evidence stop before DELETE for normal cleanup, retries, and abandoned runs.

Follow [retention safety](retention.md) and the separately authorized [live checks](verification.md#live-contract-checks) against the actual version/storage environment. The operator attests product identity; `/version` is not automatic product detection. Public API documentation and loopback fixtures do not certify live deletion semantics, supported deployment versions, or storage safety. Historical Forgejo test records remain historical. No production attestation is shipped or generated from fixtures. Publication can succeed without evidence while returning cleanup incomplete.

## Separate adoption approval

This template change performs no consumer installation/migration, remote reconfiguration, private deployment probe, registry login, live build, tag push, publication, or deletion. Obtain separate approval for each consumer and disposable live test. Preserve single-publisher operation, trusted TLS, explicit BuildKit secrets, local durable filesystem requirements, and the unsupported external-redirect boundary documented in [publication](publication.md) and [credentials](credentials.md).
