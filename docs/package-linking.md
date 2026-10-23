# Repository package linking

- [Repository package linking](#repository-package-linking)
  - [Scope and confirmation](#scope-and-confirmation)
  - [Single-writer window](#single-writer-window)
  - [Recovery and contract limits](#recovery-and-contract-limits)

## Scope and confirmation

Gitea container packages are owner-scoped. A pullable image can be absent from a repository's Packages tab until linked. `link_packages: true` explicitly authorizes linking each exact configured image name to its configured owner/repository. This affects all versions of that package, not only the prepared release. It never authorizes foreign reassignment, visibility changes, unlinking, or deletion. The default is false; the approved Ubuntu fixture enables it.

The deployed route inspected for Gitea 28.2.0 is `POST /api/v1/packages/{owner}/container/{name}/-/link/{repo_name}`, expecting 201. There is no expected-association argument in that contract. Replacement/conflict behavior is therefore treated as unknown and potentially replacing a link, not as atomic compare-and-swap. Do not test replacement against the live package; any disposable contract experiment needs separate approval.

After prepared-output verification, the engine validates the complete paginated package inventory and scoped version lookups. An already matching association needs no POST. Foreign, missing, contradictory, malformed, or unauthorized evidence stops later publication writes. Durable link intent precedes the mutation, and fresh confirmation precedes tag push, final alias promotion, and release creation. Final publication verification checks the association again. API confirmation is not a fabricated browser/UI check; report browser availability separately.

## Single-writer window

Before any POST, the operator must actually exclude all other writers for the exact owner/package, including other checkouts, CI, UI users, and API clients. Repository-local locks cannot provide that exclusion. Establish permissions/coordination outside the engine, then pass a bounded record with `publish` or `resume --package-link-window /protected/link-window.json`. It is required only when a POST is necessary and does not change immutable config/checkpoint identity.

```json
{
  "schema": 1,
  "origin": "https://git.lan",
  "server_version": "28.2.0",
  "owner": "dev",
  "packages": ["container-release-template-hello"],
  "repository": "dev/container-release-template",
  "operator": "responsible operator",
  "starts_at": "2026-10-23T12:00:00Z",
  "expires_at": "2026-10-23T12:30:00Z",
  "exclusion_procedure": "Describe actual permission restrictions and coordination excluding every other UI/API/CI writer for these packages, including in-flight requests.",
  "exclusion_confirmed": true
}
```

This example is not current authority. Set genuine timestamps and procedure after establishing exclusion. Records are at most 64 KiB with exactly these fields, exact origin/owner/repository/full server version, unique configured package names, nonempty operator/procedure (at most 2048 characters each), and exact UTC-second timestamps. The start is inclusive, expiry exclusive, and the duration cannot exceed 24 hours. Keep exclusion effective through request completion/confirmation, not merely until a request starts. Missing, unconfirmed, expired, malformed, or mismatched evidence blocks the POST; the engine rechecks immediately before it and performs a final scoped association lookup.

## Recovery and contract limits

An accepted-but-response-lost link is reconciled from fresh matching evidence without another POST or rebuild. A still-unlinked package needs a fresh valid exclusion window before any retry. Renewed authority is recorded separately from immutable link intent, so renewal cannot redirect a package or change its prepared digest. The engine never unlinks first or rolls back by reassignment. A 201 without confirmed association remains incomplete.

The record documents operator-established exclusion; it does not enforce permissions, prove the procedure was followed, or replace a distributed lock. If exclusion cannot be established, do not mutate. Correctly linked packages remain verifiable without a record. The four existing Ubuntu package versions were previously linked to `dev/container-release-template` by separate user request; that historical action is not concurrency certification or remote deletion evidence. Its repository Packages URL is `https://git.lan/dev/container-release-template/packages`. Linking can change ownership eligibility, but all [remote deletion gates](retention.md) remain intact.
