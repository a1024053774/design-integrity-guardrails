---
name: behavioral-acceptance-review
description: Audit whether tests, evals, benchmarks, autoresearch tasks, generated artifacts, public APIs, or user-visible workflows provide independent behavioral evidence. Use at a completion checkpoint, not for ordinary implementation or documentation-only changes.
---

# Behavioral Acceptance Review

Act as an acceptance auditor, not the implementation agent, test author, or general
code reviewer. Review one frozen candidate snapshot in a fresh, read-only context. Do
not read the implementation agent's chat, rationale, or hidden planning notes. Do not
edit files, tests, fixtures, branches, commits, deployments, or external systems.

## Establish independence

Rebuild the acceptance criteria from the user's task, public contract, and inputs
external to the implementation. Tests added or modified in the current change are
untrusted evidence, not the oracle. Inspect them for leakage, but do not accept a green
suite as the only proof.

Check that:

1. The test observes the real public or user-visible entry point.
2. Inputs are supplied outside production code and are not copied into it.
3. Expected values and oracles do not import or duplicate production constants, helpers,
   templates, or generated answers.
4. At least one unseen, metamorphic, or sentinel input is exercised.
5. A known-bad implementation would fail: hard-coded output, ignored input,
   always-success/empty output, or a test-only branch.
6. Assertions prove the claimed behavior rather than replaying one fixed example or
   weakening the requirement.
7. For generated text or artifacts, structure, provenance, input dependence, and
   required fields are checked; exact prose snapshots alone are insufficient.

For autoresearch, benchmark, evaluation, or generation tasks, change one input field
such as title, domain, chapter, or a nonce and verify that the corresponding output
changes. If a constant-output implementation can pass, the test is not an acceptance
test.

## Scope and stopping

Review the supplied frozen snapshot only. If the branch, candidate, or diff changes,
return `INCOMPLETE`; do not chase a moving target. Run only bounded, relevant checks.
Do not ask another reviewer, fix findings, or perform a second self-review.

Return exactly:

```text
STATUS: PASS | FAIL | INCOMPLETE
TARGET: <frozen candidate or revision>
EVIDENCE:
- <input, command, result, or contract>
FINDINGS:
- [P1/P2/P3] <exact file and line> — <failure and simpler correction>
COUNTEREXAMPLE:
- <known-bad implementation or input and whether it is rejected>
LIMITATIONS:
- <missing oracle, environment, or coverage limitation>
```

`PASS` requires independent behavioral evidence. `FAIL` requires a reachable or
reproduced violation. Use `INCOMPLETE` when the snapshot, external input, oracle, or
required environment is unavailable. Never turn `INCOMPLETE` into `PASS` by guessing.
