# goal

- [command](#command)
- [goal](#goal-1)

## command

Handle the deployed Gitea server version `28.2.0` at `https://git.lan/api/v1/version`. Review its exact API and package-link behavior before extending the current stable `1.25.x` gate. Verify repository/package identities, permission-hidden associations, existing-link refusal, and POST/read-back behavior. Update the version check, regression tests, and reference documentation while preserving conflict refusal, concurrent-writer exclusion, and fail-closed handling of unsupported versions. Distinguish local contract tests from live-server verification.

## goal

Support package linking on the deployed `28.2.0` server only after verifying its API and association safety contract, without blindly bypassing the version gate or weakening existing safeguards. Provide regression coverage and documentation that other projects can follow, clearly stating what was verified locally versus on the live server. This task stage records the goal only; it makes no implementation changes or live writes.
