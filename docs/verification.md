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

Tests use temporary Git repositories, private disposable token files, fake Docker commands, and loopback HTTP/OCI fixtures. They never read the actual default token, contact Forgejo production, create live images, or install into existing projects. Faults cover accepted-but-response-lost registry/tag/release writes, durable intent after a child process exits, stale publication retries, staged graph protection, and interruption after each installer destination write. Simulated abrupt exceptions test workflow restart behavior; these are not all real Docker-process kill or filesystem power-loss tests.

The external fake Docker test checks private auth configuration, builder/host preservation, password-stdin, and cleanup. OCI fixtures check nested indexes, runnable labels, attestations, digest integrity, and same-origin Bearer challenges. Fake tests do not prove installed Docker CLI diagnostics, runtime emulation, real multi-platform execution, or Forgejo deletion behavior. Keep hooks' application runtime tests in future consumers.

## Live contract checks

No live release, push, remote repository creation, or deletion is authorized implicitly by implementation. Obtain approval for a disposable repository/package namespace on the target Forgejo 17 server, separate from all seven existing projects. Keep the fixture source and state isolated, use scoped credentials, and record exact server/Docker/Buildx versions and storage settings.

Before attesting deletion safety, publish synthetic two-platform content and verify index/config digests and pulls on appropriate native/emulated runtime daemons. Create multiple aliases to a shared index, remove one alias through the Forgejo Packages API, and prove the retained alias and every platform/attestation digest remain retrievable. Separately test old `sha256:` version deletion, nested/shared dependencies, and absence of cascading deletion into retained graphs. Verify text-only releases, paginated inventories, lost-response recovery, and cleanup retries without rewriting source tags. Preserve results, not only command success codes.

If any retained reference becomes unavailable, do not enable cleanup. Without an authorized environment, report live checks unavailable and leave the evidence gate closed. A trusted operator may produce the attestation described in [retention safety](retention.md) only after these checks actually pass. This implementation ships no production attestation and performs no automatic remote probing that mutates a server.
