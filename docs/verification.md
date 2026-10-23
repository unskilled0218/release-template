# Verification

- [Verification](#verification)
  - [Local checks](#local-checks)
  - [Live contract checks](#live-contract-checks)

## Local checks

```sh
python3 -B -m unittest discover -s tests -v
bash -n scripts/release.sh
python3 -B scripts/launch.py validate --config examples/explicit.json
git diff --check
```

Tests use temporary Git repositories, private disposable token files, fake Docker commands, and loopback HTTP/OCI fixtures. They never read the actual default token, contact production, create live images, or install into existing projects. Faults cover accepted-but-response-lost registry/tag/release writes, durable intent after a child process exits, stale publication retries, staged graph protection, and interruption after each installer destination write. Simulated abrupt exceptions test workflow restart behavior; these are not all real Docker-process kill or filesystem power-loss tests.

The external fake Docker test checks private auth configuration, builder/host preservation, password-stdin, and cleanup. OCI fixtures check nested indexes, runnable labels, attestations, digest integrity, and same-origin Bearer challenges. Fake tests do not prove installed Docker CLI diagnostics, runtime emulation, real multi-platform execution, or Gitea deletion behavior. Keep hooks' application runtime tests in future consumers.

Version 0.1.1 adds regressions for extra/unlabeled runnable architectures, malformed and duplicate platforms, conflicting shared descriptors, explicit Buildx attestations, OCI empty-config artifacts, subject-only reachability, and artifact markers that cannot hide runnable images. The workflow fake now uses real platform/identity verification rather than accepting a supported subset. Retention cases cover completed older checkpoints, skipped aliases sharing older graphs, uncertain digest roots, same-name foreign associations, unscheduled older aliases introduced before or between deletions, recreated completed candidates, and differently ordered saved inventories. CLI tests distinguish same-revision retry from old-pin/new-pin refusal and assert unchanged state and zero remote mutations on rejection. Legacy-shaped inventory fixtures retain matching identity; they do not demonstrate cross-revision adoption.

Version 0.1.2 adds `tests/test_retirement.py` with a real loopback registry and removal-aware package fixture: deleting a child actually makes an undeleted parent graph fail. Tests exercise child-first/reversed/shuffled inventories, nested indexes, shared children, transitive unlisted intermediates, subject dependencies, and preserved attestations. Termination/lost-response injections surround every digest deletion and completion flush, reopen durable checkpoints, and assert unchanged approval, no duplicate deletion of confirmed-absent targets, and retained current publication. Further cases cover metadata corruption or omitted dependencies, cycles/bounds, initial schedule persistence, recreated completed parents, newly protected references, changed association, inconsistent absence, authentication failures, and conservative legacy handling. These are synthetic scoped deletions and simulated termination exceptions, not live Forgejo contract checks or power-loss tests.

Version 0.2.0 adds schema-2 Gitea configuration and credential rejection, subprocess isolation with native Git preservation, real loopback release/package/version request contracts, exact full-version evidence gating, legacy checkpoint refusal, and explicit missing/foreign package-link diagnostics. The preceding 0.1.1/0.1.2 records describe historical Forgejo-era testing, not Gitea deployment verification. Public Gitea API documentation and local fixtures establish endpoint expectations only; no deployed version range or storage behavior is certified.

Version 0.2.1 adds loopback null/non-object lookup rejection and real Gitea status/JSON decoding connected to publication, listed/omitted package retirement, older release retirement, and abandoned-run processing through an injected HTTP transport. Durable-state assertions prevent false completion and release POST after malformed evidence. A removal-aware loopback registry case stops dependent deletion after malformed post-delete confirmation, then resumes with verified 404 without repeating the parent DELETE or fetching its retired graph. Valid collection arrays, object lookups, allowed 404 absence, required 404 errors, and build-once publication retry remain covered. These are local regressions, not deployed-server verification.

## Live contract checks

No live release, push, remote repository creation, or deletion is authorized implicitly by implementation. Obtain approval for a disposable repository/package namespace on the actual target Gitea server, separate from all existing projects. Confirm the installed product and its exact Swagger/API contract. Keep fixture source and state isolated, use scoped credentials, and record exact full server/Docker/Buildx versions and storage settings. `/version` alone does not prove product identity.

Before attesting deletion safety, publish synthetic two-platform content and verify index/config digests and pulls on appropriate native/emulated runtime daemons. Confirm owner-scoped permissions and exact repository linkage; separately approve any whole-package linking action. Create multiple aliases to a shared index, remove one alias through the Gitea Packages API, and prove the retained alias and every platform/attestation digest remain retrievable. Separately test old `sha256:` version deletion, nested/shared dependencies, and absence of cascading deletion into retained graphs. Interrupt dependency-safe cleanup before and after parent deletions, then retry and verify remaining dependencies and retained pulls. Verify text-only releases, paginated inventories, and lost-response recovery without rewriting source tags. Preserve results, not only command success codes.

If any retained reference becomes unavailable, do not enable cleanup. Without an authorized environment, report live checks unavailable and leave the evidence gate closed. A trusted operator may produce the attestation described in [retention safety](retention.md) only after these checks actually pass. This implementation ships no production attestation and performs no automatic remote probing that mutates a server.
