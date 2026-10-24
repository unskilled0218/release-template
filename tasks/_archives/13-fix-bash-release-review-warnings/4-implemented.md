# Implementation

- [Implementation](#implementation)
  - [Outcome](#outcome)
  - [Changes](#changes)
  - [Verification](#verification)
  - [Compatibility And Limits](#compatibility-and-limits)
  - [Preserved Resources](#preserved-resources)

## Outcome

Implemented B1–B3 on new branch `13-fix-bash-release-review-warnings`, created from plan-review commit `19edb71`. Prepared version 0.3.1. The jq-free single-command workflow remains unchanged at the interface; no live release, real credential read, Docker daemon operation, or production mutation was performed.

## Changes

- **B1 — Explicit prerequisite status:** The promotion-decision read now uses a named variable with an explicit failure branch, then validates that same successful result against the captured predecessor/prepared digests before comparison. A foreign later alias refuses instead of becoming overwrite permission; a prepared alias skips duplicate promotion. Source, staging, tag creation, inventory, observed tag/release fields, and alias guards also propagate prerequisite failures explicitly. Conditional guard callers cannot suppress those failures through Bash errexit semantics. Intentional lost-response handling stays restricted to already dispatched writes.
- **B2 — Confirmed-tag lifecycle:** Fresh invocations initialize an in-memory confirmation flag, set only after the existing exact object/peeled-commit/release-state reconciliation following tag push. Subsequent guards require the same tag object and source commit; absence or replacement cannot regain pre-push permission, alter intended identity, trigger repush, or allow release POST. Accepted promotion is left intact if later tag evidence fails. Completed startup verification and ambiguous tag-only/release-only startup refusals remain unchanged.
- **B3 — Connection/auth separation:** Capture the original context selection before private auth isolation. Export a context only for an actual named/config-selected context or an explicitly nonempty caller selection; do not newly export default over a host-only selection. Keep host/TLS variables and relative path semantics unchanged, retain explicit buildx selection, and keep default buildx state under the original Docker directory. Normalize empty DOCKER_CONFIG to the home Docker directory in the helper as well as the shell, preserving config-selected context metadata. The only production Python helper change is that narrow empty-value normalization.
- **Tests:** Added 25 methods to the existing Bash family: prerequisite read/foreign/prepared alias cases, confirmed-tag loss/replacement/peeled evidence, effective Docker connection/builder/TLS cases, and conditional-caller failure propagation. Extended only the owned external-command ports to log injection events, model Docker precedence and synthetic context metadata, and change owned fixture tags. Test environments clear inherited connection variables and use temporary public TLS placeholders rather than real Docker settings or keys.
- **Version/docs:** Updated root/module version metadata and the Bash notes path to 0.3.1, added project-focused `docs/releases/0.3.1.md`, and updated README, Bash configuration/publication guidance, and verification documentation. Earlier notes, image name, Dockerfile, schemas, canonical annotation fields, legacy formats, and previous task evidence remain intact.

## Verification

- **Baseline:** Before production edits, `python3 -B -m unittest discover -s tests -q` passed 297 tests in 143.124 seconds.
- **Failing before fixes:** Added tests/fixture behavior first. The focused command selecting `test_promotion_read_overflow_blocks_later_writes`, `test_confirmed_tag_disappearance_stops_before_promotion`, and `test_host_only_connection_is_preserved` failed all three in 18.103 seconds. B1 printed a byte-limit refusal yet returned zero and declared publication verified; B2 performed promotion/release POST after the tag injection; B3 selected both the synthetic host and default local endpoint across phases. These failures reproduce the recorded warnings, not unrelated setup errors.
- **Passing after fixes:** The same three selected methods passed in 14.897 seconds. Each requires its precise injection/selection condition and verifies the resulting behavior, including absence of later writes, immutable intended identity, and effective endpoint consistency.
- **Expanded focused checks:** `python3 -B -m unittest tests.test_bash_release -q` passed the then-current 62 Bash tests in 211.248 seconds. A later seven-method focused run passed in 28.879 seconds, covering conditional helper callers, empty Docker config, tag loss after promotion, foreign/prepared alias decisions, explicit builder selection, and unusable context refusal. Timeout faults in the full-entry fixture use curl's timeout-equivalent exit status; actual bounded timeout/process cleanup remains covered by the retained data-helper tests.
- **Final suite:** `python3 -B -m unittest discover -s tests -q` passed all 322 tests in 265.092 seconds. Static inventory confirms 65 Bash methods, including 25 new methods, and retention of all 297 original methods. No tests were skipped to hide a failure.
- **Static checks:** Python AST checks, individual shell syntax checks, all six legacy example validations, root/module/README version and notes-heading/path agreement, Markdown TOC/file-link checks, and `git diff --check` passed. ShellCheck is not installed; it was neither installed nor run.
- **Serial entry-point checks:** Root `./scripts/release.sh --validate`, then `./scripts/legacy-release.sh validate --config examples/explicit.json`, then the same legacy validation with `examples/ubuntu-hello/release.json` each passed with no-credentials/no-remote-operations messages. `env -i PATH=/nonexistent /bin/bash scripts/release.sh --help` passed without external tools. These were validation/help calls only, not production publication.
- **Isolation:** Actual Bash commands, bounded helper subprocesses, and real Git object/ref operations ran only inside new owned fixtures. Docker/curl were PATH-injected ports. No real TLS handshake, image runtime, deployed registry behavior, or real daemon routing was verified.

## Compatibility And Limits

The Bash settings schema remains 1 and annotated identity remains `container-release-bash/1` with unchanged fields/serialization. The legacy Python configuration/publication/checkpoint/retirement formats and exact source/config/script/template pin checks are unchanged. A new source/version/config notes path is a different publication identity, not authority to adopt or rewrite an older transaction.

Confirmation is process-local and one-way; it is not a durable journal or automatic restart repair. A checked read is still not atomic with a remote write. Operator-controlled single-writer exclusion must span in-flight completion, and the checkout lock does not exclude other writers. If a later check fails after promotion, the accepted alias remains rather than being rolled back. No deletion, package reassignment, force tag update, repush repair, source rollback, or privileged setup is introduced.

The Docker matrix checks effective selection using explicit fixture precedence and metadata, including empty context/config values, named contexts, synthetic host TLS, relative paths, and default/explicit builder paths. This is local behavioral evidence, not native Docker routing/TLS certification. Byte/page/item/time budgets, credential protections, and private temporary cleanup are unchanged; SIGKILL/power-loss limits remain as previously documented. A live 0.3.1 experiment requires separate explicit target/version/source/image/release approval.

## Preserved Resources

Compared with `19edb71`, all legacy implementation modules other than repository version metadata, the stable legacy launcher/updater, every example, Dockerfile, earlier release notes, archived tasks, task 11/12 records, task 13 goal/plan/review, and dashboard history are unchanged. `todo.md`, home-web, real credentials/Docker config/TLS keys, published tags/bodies/packages, and preserved live checkouts/checkpoints were not accessed or modified. Tag deletion/replacement and connection-file creation affected only newly created test-owned fixtures, preferably under `/tmp/opencode`; no Git pruning or image deletion was performed.
