---
name: reality-first-engineering
description: Establish a short reality and decision gate before implementation when missing facts, requirements, external behavior, or acceptance criteria could change the direction. Use only for consequential or materially uncertain work.
---

# Reality-First Engineering

Use this before architecture or broad implementation when a wrong assumption would cause
meaningful rework, data loss, security exposure, irreversible side effects, or a false
acceptance result. It is a small decision gate, not a second project manager, code review,
test suite, or reason to delay a cheap reversible probe.

Do not use it for a small change with known inputs, contracts, and environment, or for
documentation/formatting-only work.

## Gate protocol

1. **State the decision.** Write the goal, non-goals, acceptance condition, and the exact
   decision that must be made before implementation.
2. **Separate facts from guesses.** Label each relevant item `observed`, `measured`,
   `inferred`, or `unknown`. An implementation assumption is not evidence.
3. **Choose the smallest probe.** For each unknown that could change the direction, define
   one falsifiable experiment with real inputs, a pass condition, a failure condition, a
   stop condition, an owner, and an evidence location. Test the highest-impact unknowns
   first; do not build the whole system to discover them.
4. **Gate the direction.** Return `PASS` only when the architecture/plan follows from the
   available evidence. If a decisive fact is unavailable or a probe fails, return
   `BLOCKED` or `INCOMPLETE` and report what is needed. Do not cover the gap with a
   fallback, compatibility path, mock-only branch, or speculative abstraction.
5. **Keep the boundary testable.** Put external effects behind the existing boundary that
   owns them and keep deterministic domain/state logic driven by supplied inputs. Add a
   layer only when a concrete caller or boundary needs it.

## One ledger, one epoch

If `project-to-act` is available, run its `--check` first and follow its mode. It owns goals,
scope, durable progress, versions, evidence, and acceptance. Record this gate in the existing
canonical source; never create `REALITY.md`, a second plan, or a parallel status file.

For a managed project, use the existing files (or their equivalent sections):

- overview: constraints, facts, and current unknowns;
- progress: probes, blockers, owners, and next action;
- versions: decisions changed by evidence;
- acceptance: experiment evidence, gate result, and validity.

For an unconfigured one-off project, keep the brief in the task response. Do not initialize
project management merely because this skill loaded. Read the target section again before
writing and validate through `project-to-act` after writing.

Run one gate per decision batch. Edits and test iterations under the same assumptions do not
restart it. Re-open only when new evidence invalidates an assumption, scope changes, or a new
direction is proposed.

## Required brief

```text
REALITY GATE: PASS | BLOCKED | INCOMPLETE
GOAL / NON-GOALS:
DECISION:
OBSERVED:
MEASURED:
INFERRED:
UNKNOWN:
PROBE: input, method, pass/fail, stop condition, owner, evidence
DECISION CONSEQUENCE:
LEDGER / NEXT:
```

After `PASS`, derive the smallest implementation plan and use normal testing. At completion,
invoke `design-integrity-review` only when its structural-risk route applies; evaluation or
generation surfaces go through its single behavioral-acceptance route. Neither reviewer
replaces this gate or creates another ledger.

The honest result may be a stop. A clean `BLOCKED`/`INCOMPLETE` with a precise next probe is
better than a polished implementation of an unverified premise.
