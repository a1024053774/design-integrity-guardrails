---
name: design-integrity-review
description: Route one frozen candidate change through a focused structural-integrity review, or to behavioral-acceptance-review when tests, evals, benchmarks, autoresearch, generated artifacts, or other acceptance surfaces changed. Use at a completion checkpoint, not after every edit; do not use for documentation-only or formatting-only changes.
---

# Design Integrity Review

Review one candidate change at a completion checkpoint. This skill is a router and a
focused structural review, not a general QA pass. It is read-only: do not edit files,
tests, fixtures, commits, branches, deployments, or external systems.

## Choose one route

Inspect the task, active instructions, the candidate diff, and changed paths first.

- If the change touches `autoresearch`, `eval`, `benchmark`, `harness`, `grader`,
  `golden`, `oracle`, or another explicit evaluation surface, invoke the
  `behavioral-acceptance-review` skill and delegate exactly one review to the
  configured `acceptance-auditor`.
- Otherwise, review only structural risks introduced by the candidate: broad or
  swallowed exception handling, fallback/retry paths, compatibility branches,
  duplicate or parallel APIs, and local patches that bypass root-cause ownership.
- If both kinds of risk are present, use one `acceptance-auditor` call and include
  the scanner's structural markers as review context. Do not start a second reviewer.
- Documentation-only, formatting-only, screenshot-only, and test-fixture maintenance
  changes do not require this skill unless the task explicitly requests review.

## Freeze the candidate

The candidate must be a stable commit, patch, or read-only worktree snapshot. The
implementing agent must not edit, commit, or deploy while the review is running. If
the target changes, stop and report `INCOMPLETE`; do not chase a moving diff.

Multiple edits or commits in one answer are one review epoch when they are part of the
same planned change. The lifecycle hook uses the host-provided `turn_id` to keep that
budget scoped to one user request: a new turn starts a fresh baseline after the prior
epoch is acknowledged, while an unresolved pending review is retained. Wait until that
cohesive batch is ready. A new epoch is justified only when a later checkpoint introduces
a new structural risk scope or a new explicit acceptance surface. Do not re-review the
same risk scope merely because a line, commit, or test count changed.

## Structural gates

For each confirmed structural risk, establish:

- **Reachability:** the real caller, input, contract, or observed failure;
- **Ownership:** whether this layer owns recovery, degradation, cleanup, or translation;
- **Architecture:** why the existing abstraction cannot carry the correct behavior;
- **Proportion:** whether the fix is limited to the root cause.

Scanner output is a routing signal, not proof. Inspect relevant callers and contracts,
but do not turn this review into a broad behavior audit. Tests added or modified by the
implementing agent are evidence to inspect, not a reason to expand the scope.

## Review budget and report

Use one bounded reviewer call per epoch. If it returns confirmed findings, the
implementing agent may fix the batch and request at most one targeted re-review of the
changed scope. A timeout, unavailable reviewer, moving snapshot, or missing evidence is
`INCOMPLETE`; do not poll, interrupt, close, and respawn automatically.

Report only confirmed, actionable findings with exact file and line, reachable evidence,
concrete failure or maintenance cost, and the simpler coherent correction. Return one of:

- `PASS`: no confirmed finding in the selected scope;
- `FAIL`: at least one reachable or reproduced finding;
- `INCOMPLETE`: the scope, oracle, snapshot, or reviewer was unavailable.

Do not claim `PASS` because a deterministic scanner is quiet or a test suite is green.
Do not create a project ledger entry for a one-off review.
