# Legacy Python releases

- [Legacy Python releases](#legacy-python-releases)
  - [Existing transactions](#existing-transactions)
  - [Old managed installations](#old-managed-installations)

## Existing transactions

The pre-0.3.0 Python release engine remains under `release_template/`; `scripts/legacy-release.sh` explicitly invokes `scripts/launch.py` with its original CLI arguments. For example, local validation is `./scripts/legacy-release.sh validate --config examples/explicit.json`. The new default Bash command does not interpret those arguments or import this engine.

Keep existing transactions on the exact captured source/config/template pin and preserved checkout. A new wrapper or unchanged schema does not authorize adopting an old checkpoint under new code. Historical Ubuntu fixture settings and release notes remain unchanged; their root-version reference must not be used to publish an old notes version from a newer checkout. Use the original captured checkout for old transactions, not current `VERSION` with old notes.

The legacy engine's checkpoint recovery, package linking, local ownership/removal, suites, and evidence-gated remote retirement remain legacy-only features. The new Bash identity is not a Python schema-2 annotation. No automatic conversion, deletion ownership transfer, or legacy cleanup of new-format history is supplied.

## Old managed installations

Protocol-1 managed installations verify the exact original bootstrap bytes. Changing `scripts/release.sh` therefore breaks that upgrade boundary intentionally: `scripts/update.py` refuses installing a Bash-template revision as a Python inventory before touching the destination. Old compatible immutable revisions remain separately installable/verifiable with the legacy updater. No hash rewrite, bootstrap migration, or installation into another project occurs automatically.

For a new consumer, review/copy the small [Bash file set](bash-configuration.md) through that project's own approved adoption task. Do not use the legacy updater against current Bash source or replace launchers in an existing managed destination. Follow [legacy installation/recovery](installation.md) only with an appropriate original immutable revision and separately authorized target.
