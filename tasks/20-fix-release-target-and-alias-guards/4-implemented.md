# Implementation results

- [Implementation results](#implementation-results)
  - [Changes](#changes)
  - [Verification](#verification)
  - [Baseline replay](#baseline-replay)
  - [Compatibility and remaining limits](#compatibility-and-remaining-limits)

## Changes

Implemented task 20 on branch `20-fix-release-target-and-alias-guards`, created from `acbf40f`. Prepared version 0.6.2 without changing configured repository/image/login/token/platform settings.

- **F1:** `source()` now reads `git remote get-url --push --all origin` through the bounded Git helper. It requires one nonempty, control-free effective URL before normalization, rejecting duplicates, fan-out, malformed output, decoding/command failures, and foreign destinations. First-fetch, clean-main, captured-source, and remote-main checks remain intact. Every subsequent source scan rechecks the complete effective push set; no remote configuration is changed and the exact non-force tag push is retained.
- **F2:** fresh publication initializes `promotion_confirmed=false`, then transitions once to true after a checked read proves the prepared digest at `latest`. This includes skipped promotion and accepted-but-response-lost reconciliation. Later alias guards require exactly the prepared digest on their first checked read; predecessor reversion, disappearance, foreign state, or read failure stops before release creation without repromotion or rollback.
- **Regressions:** added 14 tests: real-Git explicit/fallback URL cardinality, duplicate destinations, URL rewriting, SSH/HTTPS normalization, invalid/failed push evidence, post-build destination change, six post-confirmation fault cases, skipped/reconciled-promotion reversion, and conditional-shell guard checks. Fixture additions are test-only; no production test hooks were introduced.
- **Documentation:** updated README, current configuration/publication/process/verification/image docs, root version, configured notes path, and new `docs/releases/0.6.2.md`. Active warnings distinguish resolved F1/F2 from remaining F3–F5. Historical release notes, reviews, plans, and goals remain unchanged.

## Verification

- All 14 focused new tests passed in 53.258 seconds, including real Git URL expansion, full-entry refusal/injection, accepted-state preservation, and both alias-guard phases inside Bash conditionals.
- `python3 -B -m unittest discover -s tests -v` passed all 131 tests in 882.564 seconds: 5 interface/tree/version, 96 publication-flow, and 30 helper cases, including all 117 pre-existing tests. This harness result does not resolve F5's missing-parent portability limitation.
- Both shell scripts passed `bash -n`. All current Python source/test files passed AST parsing. Local `./scripts/release.sh --validate` passed without credential or remote operations. `git diff --check` passed.
- Active README/docs/current release notes passed relative-file links, heading anchors, and table-of-contents checks. Version 0.6.2 agrees across root `VERSION`, README, configured notes path, and release-note heading.
- Tests used owned temporary repositories and bare remotes, fake Docker/curl executables, synthetic registry state, and disposable tokens. Real-Git URL checks isolated system/global configuration and omitted only remote-main network lookup through `source(..., remote=False)`. No real Docker operation, production credential access, privileged preparation, publication, rollback, or unrelated project mutation occurred.

## Baseline replay

Replayed two new regressions with all three pre-fix release scripts from `acbf40f` copied into owned fixtures, committed and pushed only to their owned bare remotes. Both failed for the intended behavioral reasons, with no setup errors:

- **F1:** `test_push_urls_changed_after_build_block_tag_dispatch` observed the post-build destination change but the old entry returned zero, failing the expected nonzero-exit assertion. The new entry refuses before tag dispatch and preserves staging.
- **F2:** `test_post_confirmation_predecessor_reversion_blocks_release` reached the intended post-confirmation injection, but the old entry still emitted `release-post`, failing the no-later-write assertion before its final refusal. The new entry stops before that POST.

The replay driver initially expected a zero exit for both old behaviors; it was corrected to accept F2's precise late-write assertion failure because the original final check correctly returned nonzero. The final driver verified exactly one expected assertion failure and zero setup errors per case. No tracked baseline file was modified.

## Compatibility and remaining limits

Multiple effective push entries, including identical URLs, are deliberately unsupported. Git still owns URL rewriting; SSH-port normalization, configuration schema 1, `container-release-bash/1`, package association gates, completed verification, and conservative retry authority remain unchanged. Script/config hashes change with this version; preserve original checkout/pins for old or partial publications instead of adopting them through these scripts.

F3/N2 config-local Buildx discovery, F4 early setup guidance, and F5's harness-specific temporary parent remain unresolved and outside this task. Checks do not provide cross-service atomicity or prevent unseen configuration/alias edits after a read; retain operator-enforced writer and checkout-configuration exclusion. No live 0.6.2 publication, UI, native Docker routing, runtime emulation, deployed Gitea behavior, or power-loss guarantee is claimed. `todo.md` is untouched.
