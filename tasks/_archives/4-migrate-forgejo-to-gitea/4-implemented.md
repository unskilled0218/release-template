# Implementation results

- [Implementation results](#implementation-results)
  - [Outcome](#outcome)
  - [Changes](#changes)
  - [Verification](#verification)
  - [Preserved boundaries](#preserved-boundaries)
  - [Remaining operational work](#remaining-operational-work)

## Outcome

Implemented the approved Gitea-only migration on branch `4-migrate-forgejo-to-gitea`. Template version is `0.2.0` in `VERSION`, the Python package, and README. This is an intentional breaking configuration/credential change, not a consumer or checkpoint migration.

## Changes

- Configuration requires schema 2 with `gitea`; schema 1 and legacy/mixed `forgejo` keys fail before credentials or clients. All five synthetic examples use the new contract.
- Credentials support only `GIT_TOKEN` as a protected file-path override and `GIT_USERNAME` as explicit authentication login. The default is `~/.config/gitea/gitea-token`. `GIT_USER` and the listed provider-specific credential names are rejected, including empty settings, before file access. No old-path fallback or secret migration exists.
- Runner environments remove exact supported/rejected credential names while preserving native Git SSH and author/committer settings. Existing stdin login, temporary Docker auth, redaction, and builder/context handling remain intact.
- The service adapter and workflow/cleanup attributes are named `Gitea`/`gitea`. API paths, payloads, header authentication, exhaustive pagination, OCI verification, and same-origin protections remain. Release lookup rejects non-object successful JSON. New release prose names Gitea; old recognized metadata remains readable.
- Deletion evidence requires schema 2, product `gitea`, exact origin, exact full server version, a distinct disposable owner/repository, nonempty operator/date metadata, and all three successful verification results. A dedicated bounded version validator preserves prerelease/build suffixes. Old evidence, major-only fields, malformed/unavailable runtime versions, and version drift cannot authorize deletion.
- Missing/foreign same-name package repository links preserve survivor graphs and produce explicit skipped diagnostics, including protected current digest records. Cleanup cannot silently report complete. No package link/reassignment API was introduced.
- Added `tests/test_gitea_migration.py`, CLI legacy/mixed configuration rejection and old-config checkpoint refusal, and old release-prose parsing coverage. Renamed existing fixtures without removing safety scenarios. Updated README and all relevant documentation, including dedicated `docs/gitea-migration.md`.

## Verification

- Initial two migration tests failed against the old implementation, then passed after the contract change.
- Focused migration suite passed 19 tests after its initial expansion; the final suite additionally includes legacy release-prose coverage.
- `TMPDIR=/tmp/opencode python3 -B -m unittest discover -s tests`: 132 tests passed in 36.036 seconds. The previous baseline contained 110 tests. Existing removal-aware retirement, installer, build-once, stale-resume, platform/label, survivor protection, and lost-response scenarios remain covered.
- Real loopback Gitea-shaped HTTP tests cover release POST/GET/DELETE, package GET/DELETE and capped pagination, version responses, URL encoding, token headers, malformed JSON/shapes, 404 absence, and authentication/server failures. Existing repeated-page and redirect tests remain.
- Negative evidence tests assert zero deletions and unchanged checkpoint bytes. CLI rejection tests assert no credential/client construction for retired configuration; old-pin and old-config checkpoint tests assert unchanged state, releases, aliases as applicable, and no login/build/promotion/push operations. Same-revision publish/resume/cleanup and disposable installed schema-2 validation pass separately.
- All five examples passed credential-free validation through `scripts/launch.py`.
- Python AST syntax checks passed for engine, scripts, tests, and example hooks. Version consistency checks passed for `0.2.0`.
- `bash -n scripts/release.sh` passed. README and all seven documentation pages passed table-of-contents and local-link checks. `git diff --check` passed.
- Active runtime/examples scans found no operative Forgejo settings; remaining runtime mentions explicitly reject retired inputs. Documentation retains only migration/rejection context and historical testing statements.

## Preserved boundaries

The outer checkpoint schema, identity construction, release marker/structured schema, nested retirement protocol, stable launcher/bootstrap bytes, and managed-installation protocol remain unchanged. State/launcher/updater files have no diff. Historical task archives and prior health records have no changes. The remote remains `git@git.lan:dev/container-release-template.git`; no remote configuration was changed. Existing untracked `todo.md` remains untouched and excluded from the commit.

No actual credential file was read or changed, private deployment probed, consumer migrated, real Docker build/login performed, source tag pushed, live release published, package linked, or live deletion attempted. All credential files, registries, package deletions, and consumer installations used disposable local fixtures. The implementation commit is local only; no push is authorized.

## Remaining operational work

The installed Gitea product/version, deployed Swagger behavior, token scopes, package linkage/import state, and storage deletion behavior remain unknown. Public documentation and synthetic versions do not establish a supported deployment range. Obtain separate approval for consumer adoption and disposable tests on the actual target version/storage environment. Verify shared aliases, nested/shared manifests, retained platform pullability, repository linkage, text-only releases, and dependency-safe interruption/retry before producing fresh product/origin/full-version evidence. Deletion remains disabled without that evidence; publication may succeed with an explicit cleanup-incomplete result. Preserve old checkpoints and provenance for separately reviewed recovery rather than rewriting identities or using old cleanup code.
