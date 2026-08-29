---
name: reality-first-engineering
description: Establish a bounded reality and decision gate before implementation when incomplete facts, assumptions, external behavior, or acceptance criteria could invalidate the direction. Coordinate with project-to-act as the sole persistent ledger; do not use for ordinary isolated edits or documentation-only work.
---

# Reality-First Engineering

AI can turn an unverified assumption into a complete system faster than a person can test
the assumption. This skill is a **pre-implementation gate**, not a general code review,
project manager, or second test suite. Its job is to make reality measurable before the
agent commits the project to an architecture.

## When to use it

Use this gate before architecture or broad implementation when any of these are true:

- the request, domain rule, acceptance condition, or user intent is incomplete in a way
  that could change the solution;
- an external API, deployment environment, data source, permission, schema, timing,
  quota, cost, or operational constraint is not yet verified;
- reliability, performance, security, scale, migration, or compatibility assumptions
  are being treated as facts without a measurement or authoritative source;
- the system touches a non-deterministic external system or environment;
- a test, harness, benchmark, autoresearch task, or generated artifact could pass while
  ignoring real inputs, an independent oracle, or the user-visible behavior;
- a wrong assumption would cause expensive rework, data loss, security exposure,
  irreversible side effects, or a large rewrite.

Do not invoke it for a small, isolated change whose inputs, contracts, and execution
environment are already known, or for documentation/formatting-only work. Do not use it
as a reason to delay a cheap, reversible probe.

The optional `scripts/reality_prompt_hook.py` can be attached to a harness's
`UserPromptSubmit` event. It only adds a short reminder when a prompt combines a
high-impact decision with an action or an explicit uncertainty. It is advisory, does not
prove that the gate ran, and never replaces this workflow.

## Non-negotiable rules

1. **Facts outrank plausibility.** Separate `observed`, `measured`, `inferred`, and
   `unknown`. An agent assumption is not a fact merely because it makes the design
   coherent. Never fabricate a measurement, external behavior, user decision, or oracle.
2. **Unknown is a valid result.** Every unknown that could change the architecture gets
   either a small falsifiable experiment or an explicit owner and stop condition. If it
   remains unresolved, return `BLOCKED` or `INCOMPLETE`; do not silently choose a
   production architecture and retrofit a fallback around the uncertainty.
3. **One reality epoch.** Run one gate for one architecture decision batch. Several edits
   or test iterations under the same assumptions do not restart it. Re-open only when a
   measurement invalidates an assumption, the scope changes, or a new architecture is
   proposed.
4. **The source of truth can be outside the repository.** If only a person, domain owner,
   production system, customer, or private data can supply a fact, ask for that
   evidence or report the exact blocker. “Could probably work” is not a passing result.
5. **No bypass paths.** Do not add a catch, default, compatibility API, mock-only branch,
   or speculative retry merely to avoid validating the premise. Fix the assumption at
   the layer that owns it, or stop and report the required change.

## Workflow

### 1. Find the project’s one ledger

If the `project-to-act` skill is available, first run its project-management `--check`
for the actual project root and follow the reported mode:

- `managed`: read `PROJECT_OVERVIEW.md` first, then only the progress, versions,
  features, or acceptance files relevant to this task;
- `external-ledger`: use only the configured canonical ledger;
- `legacy-managed`: inspect the migration dry-run before changing anything;
- `unconfigured`: do not initialize a project ledger just because this skill loaded.
  For a one-off task keep the brief in the response; for a durable project, ask for or
  use the project’s explicitly authorized initialization/adoption path.

`project-to-act` owns goals, scope, durable progress, versions, features, evidence, and
acceptance. This skill never creates `REALITY.md`, a second plan, or a parallel status
file. If multiple ledgers are found, stop and resolve the conflict before writing.

### 2. Write a short Reality Brief

Keep one compact brief for the current decision batch. Use this shape in the canonical
ledger when one exists, or in the task response when it does not:

```text
REALITY GATE: PASS | BLOCKED | INCOMPLETE
SCOPE: what decision is being made and what is explicitly out of scope
OBSERVED: directly seen or supplied facts
MEASURED: value, method, time, environment, and evidence location
INFERRED: conclusions derived from the facts (label them as inference)
UNKNOWN: unresolved facts that could change the design
EXPERIMENTS: smallest falsifiable probe, pass/fail condition, stop condition, owner
ARCHITECTURE: decisions justified by the current evidence
LEDGER: where the brief and evidence were recorded
NEXT: the next bounded action or the exact blocker to report
```

Do not turn every thought into a document. Update the brief when a fact, decision,
blocker, or evidence status changes; consolidate stale or duplicated notes instead of
adding another Markdown file.

### 3. Test the assumptions that can move the architecture

Rank unknowns by **decision impact × cost of being wrong**, then design the smallest
probe that can falsify the leading assumption. Record:

- the real input and setup (account, data, network, timing, user, or deployment
  environment);
- what is measured or observed, not what the implementation expects;
- a concrete pass condition, failure condition, and stop condition;
- evidence ID, timestamp, command or method, version/environment, result, location,
  and validity/expiry when the project ledger supports it.

Check only the constraints relevant to the boundary—availability, data shape, permissions,
timing, rate limits, cost, side effects, recovery, observability, and safety. The probe
may be a real API call, representative data sample, permission check, load measurement,
migration rehearsal, external-user check, or black-box input. A small probe is often more
valuable than another complete implementation layer. If the required source or environment
is unavailable, keep the affected item `unknown` and design an explicit seam rather than
pretending the test passed.

### 4. Keep the architecture testable at the boundary

Where applicable, separate:

1. external/platform adapters (APIs, filesystems, cloud, browsers, or tools);
2. pure domain logic, state transitions, and deterministic transformations;
3. persistence, transport, presentation, and acceptance adapters.

Make deterministic logic testable with externally supplied inputs. Reserve smoke, soak,
permission, migration, and black-box checks for the real boundary and record their
evidence. This is a guideline, not permission to introduce layers without a concrete
boundary or caller.

### 5. Hand off to the existing completion flow

After the Reality Gate is `PASS`, derive the implementation plan from the recorded facts
and proceed with the project’s normal implementation and evidence-first testing. At a
completion checkpoint:

- use `design-integrity-review` once for newly introduced structural risk;
- if evals, benchmarks, autoresearch, harnesses, generated artifacts, or acceptance
  surfaces changed, let it route once to `behavioral-acceptance-review` and the
  configured `acceptance-auditor`;
- do not restart either review for every edit in the same architecture epoch.

If a new measurement disproves the architecture, pause implementation, update the
canonical ledger, mark the gate `BLOCKED`/`INCOMPLETE`, and re-plan. Do not preserve a
wrong direction by accumulating compatibility paths.

## Project-to-act write mapping

When the project is managed, keep the records in the existing files:

| Reality information | Canonical destination |
| --- | --- |
| constraints, observed/measured facts, current unknowns | `PROJECT_OVERVIEW.md` |
| active probes, blockers, owners, next action | `PROJECT_PROGRESS.md` |
| architecture choice caused by evidence, route change | `PROJECT_VERSIONS.md` |
| experiment evidence, Reality Gate result, expiry | `PROJECT_ACCEPTANCE.md` |
| feature impact, if a feature’s scope/status changes | `PROJECT_FEATURES.md` |

For an external ledger, use its equivalent sections and nothing else. Read the section
again immediately before writing, preserve history, and validate after writing according
to `project-to-act`.

## Documentation contract

Humans should get one current summary: the project overview plus a concise task result.
Agents may need detailed measurements and decision history, but those belong in the one
canonical ledger with status, source, and last-verified time. Derived notes are disposable
and must never outrank code, measurements, or the canonical ledger. When documentation
is stale or duplicated, consolidate it as part of the relevant scope; do not reward the
agent for producing more pages.

## Required result

Before broad implementation, report `PASS`, `BLOCKED`, or `INCOMPLETE` and make the
decisive facts, unknowns, experiment, architecture consequence, ledger location, and
next action visible. A clean, honest stop is a successful gate outcome when the correct
implementation is not yet justified.
