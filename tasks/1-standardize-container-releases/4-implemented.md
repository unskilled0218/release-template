# Implementation results

- [Implementation results](#implementation-results)
  - [Outcome and scope](#outcome-and-scope)
  - [Changes](#changes)
  - [Verification](#verification)
  - [Limits and operational gates](#limits-and-operational-gates)
  - [Version and repository workflow](#version-and-repository-workflow)

## Outcome and scope

Implemented a new local repository at `~/workdir/container-release-template`, intended for `dev/container-release-template`, on the new branch `1-standardize-container-releases`. Only the template received implementation changes. All seven existing repositories were checked with read-only Git status and remained clean: `dev-docker`, `home-web`, `yt-web`, `my-library`, `my-rss`, `baikal-docker`, and `ntr-server`. No consumer migration or installation into those projects occurred. The goal, plan, and review artifacts were not changed during implementation.

## Changes

- Added a Python 3.11+ standard-library engine with separate configuration/identity policy, Git/Docker/HTTP adapters, durable release state, publication orchestration, and cleanup modules. Added a stable Bash/Python launcher and explicit pinned installer/updater.
- Implemented `validate`, `publish`, `resume`, `cleanup-plan`, `cleanup`, and explicitly selected `abandon` modes. Configuration never defaults to a production repository or image.
- Default credentials come from the protected file `~/.config/forgejo/forgejo-token`; `FORGEJO_TOKEN` overrides the path, not the raw token. Account login uses `FORGEJO_USERNAME` with conflict-checked `FORGEJO_USER` compatibility. Tokens are not printed, committed, passed as command arguments, or stored in release state.
- Preserved early platform preflight, clean-main/source/tag identity checks, trusted HTTPS, credential isolation, selected Docker context/builder settings, and latest-only final registry publication by default. Explicit current-version aliases are optional. Docker authentication prevents implicit native-helper autodetection and uses private temporary storage.
- Default builds use private captured-commit snapshots, not ignored local files, credentials, release state, or Git metadata. Build hooks receive the snapshot and exact parent digests. Added synthetic dependent-image support and Node, explicit-tag, version-file, Cargo-hook, and multi-image examples.
- Implemented build-once immutable preparation, digest-preserving promotion, zero-attachment Forgejo release descriptions, schema-bound checkpoints, durable operation intent, pending-operation reconciliation, and explicit stops when build evidence cannot be recovered. An older checkpoint cannot silently acquire a new predecessor or roll `latest` backward.
- Added paginated scoped retention planning, protected nested manifest/attestation graphs, protection for unfinished outputs and accepted-but-uncheckpointed staging builds, successful-run staging retirement, explicit bounded abandoned-run alias cleanup, and retryable cleanup results. Git tags, unrelated packages, drafts/prereleases, uncertain identities, and current required manifests remain protected.
- Implemented immutable-commit installation pins, checksummed managed inventories, dry-run/verification modes, destination-scoped updater/release locking, staged journal/backups, lock-last file replacement, obsolete-file checks, completion/restoration recovery, and pre-import installation verification. Bootstrap changes require a separately reviewed migration.
- Added a concise README and dedicated configuration, credentials/TLS, publication/recovery, retention, installation/update, and verification documents. All Markdown files include tables of contents.

## Verification

- `TMPDIR=/tmp/opencode python3 -B -m unittest discover -s tests`: passed all 59 tests on Python 3.12.3. Tests use disposable Git repositories, protected fixture token files, an external fake Docker executable, synthetic workflow adapters, and loopback HTTP/OCI fixtures. No test read the real token or contacted production.
- Publication tests cover stale/equal-version conflicts, matching partial-suite resume, source drift, conflicting local tags, lost source/tag/build/promotion/release responses, build verification failures, and no rebuilding or historical deletion during recovery failures.
- Retention tests cover server-capped/repeated pagination, digest integrity, nested indexes/attestations, mutable-descriptor rejection, repository association, shared/current digests, unfinished runs, repeated staging retirement, partial deletion retry, ambiguous versions, and missing deletion evidence.
- Update tests cover immutable pins, modified/missing/unexpected managed content, escaping paths/symlinks, upstream removals, interruption after each destination write including lock replacement, recovery conflicts, restoration of an existing installation, shared locks, and installed-launcher verification before engine import. A child-process `os._exit` test verifies durable operation intent; simulated termination exceptions exercise workflow/update restart paths.
- All five example configurations passed credential-free CLI validation. Python source parsed successfully, Bash syntax passed, Markdown contents/whitespace checks passed, and `VERSION` agrees with `release_template.__version__` at `0.1.0`.
- Git staged whitespace validation passed before commit. A committed-source smoke check at `65505b8a7a2c206fe79cabc0bf7879b59a4520e8` passed installer dry-run, actual installation into a disposable `/tmp/opencode` destination, installed-inventory verification, and the installed launcher's credential-free configuration validation. No bytecode appeared in the managed installation. The template repository's final working tree is clean.

## Limits and operational gates

- No remote repository was created or pushed. No real Docker image was built/published, no Forgejo release was published, and no live package/release was deleted. Remote repository visibility and publication still need approval.
- Real Docker/Buildx multi-platform behavior and Forgejo 17 deletion semantics remain unverified. Container deletion is blocked without a trusted operator's same-server disposable-test attestation and matching running server version. No passing production attestation is shipped. Mock tests do not satisfy this gate.
- The attestation is an explicit trusted operational input, not a cryptographic proof; operators must retain actual disposable-test results and reverify after relevant server/storage changes. Live verification instructions are in `docs/verification.md` and `docs/retention.md`.
- POSIX `flock`, same-filesystem atomic replacement, and file/directory `fsync` are required. Network filesystems and external writers/publishers ignoring the protocol are unsupported. Local locks do not provide cross-host transactions.
- Unknown legacy publication metadata needs a separately reviewed adoption procedure. Ambiguous historical digests remain protected and can report cleanup incomplete. An uncertain build without recoverable digest evidence stops for operator investigation rather than silently rebuilding. Submodule/LFS materialization and real application-specific runtime hooks are not supplied automatically.
- The task artifacts remain under `~/workdir/tasks/1-standardize-container-releases/`, outside the new repository. The workspace itself is not a Git repository; it was not initialized or used to commit these artifacts.

## Version and repository workflow

This is the new template's initial version, `0.1.0`, recorded in `VERSION`, `release_template/__init__.py`, and README. The implementation branch name exactly matches the task directory and did not reuse an existing branch. Implementation code, tests, examples, and documentation are committed only in the new local template repository; existing projects and remote repositories remain untouched.

Commit: `65505b8a7a2c206fe79cabc0bf7879b59a4520e8` — `feat: add reusable Forgejo container release template`. No remote is configured or published. This results file remains outside the implementation commit because the shared task directory is not a Git repository.
