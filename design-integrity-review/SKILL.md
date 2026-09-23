---
name: design-integrity-review
description: Review one frozen candidate change for structural shortcuts — swallowed or broad exception handling, fallback/retry paths, compatibility branches, parallel APIs, and patches that bypass root-cause ownership — or route to behavioral-acceptance-review when an evaluation surface changed. Use once at a completion checkpoint; not for documentation-only, formatting-only, or routine test maintenance.
---

# Design Integrity Review

A read-only, bounded structural review of one candidate change. Do not edit files, tests,
commits, branches, or external systems while reviewing.

If the direction itself rests on unverified facts, send the work to
`reality-first-engineering` first; this review does not rationalize an unverified design.

## Route

- Change touches an evaluation directory (`eval`, `benchmark`, `harness`, `grader`, `golden`,
  `oracle`, `autoresearch`) or another explicit acceptance surface → use
  `behavioral-acceptance-review` instead, passing any structural markers as context.
- Otherwise review only the structural risks introduced by the candidate.

Run the scanner on the working tree to locate candidates quickly:

```bash
python3 <skill-dir>/scripts/design_integrity.py --cwd <repo> [--format json]
```

It reports newly added exception boundaries, swallowed exceptions, and default returns after
an exception. It is a locator, not proof: a quiet scanner is not `PASS`, and a name such as
`fallback`, `V2`, or `Compat` is not evidence of a problem.

## Structural gates

The candidate must be a stable commit, patch, or snapshot; if it changes during review,
return `INCOMPLETE`. For each suspected risk, establish:

- **Reachability** — the real caller, input, contract, or observed failure;
- **Ownership** — whether this layer owns recovery, degradation, cleanup, or translation;
- **Architecture** — why the existing abstraction cannot carry the correct behavior;
- **Proportion** — whether the change is limited to the root cause.

## Report

Report only confirmed, actionable findings: exact file and line, reachable evidence, the
concrete failure or maintenance cost, and the simpler correction. Return one of:

- `PASS` — no confirmed finding in scope;
- `FAIL` — at least one reachable or reproduced finding;
- `INCOMPLETE` — snapshot, scope, or evidence unavailable.

One review per candidate. After fixes, at most one targeted re-review of the changed scope.
