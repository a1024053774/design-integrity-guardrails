---
name: design-integrity-review
description: Review one candidate change in a fresh, read-only context for structural shortcuts — swallowed or broad exception handling, fallback/retry paths, compatibility branches, parallel APIs, and patches that bypass root-cause ownership — judged against the task's goal and non-goals, and route acceptance-surface changes to behavioral-acceptance-review. Use once at a completion checkpoint; not for documentation-only, formatting-only, or routine test maintenance.
context: fork
agent: Explore
background: false
---

# Design Integrity Review

A read-only, bounded structural review of one candidate change. Do not edit files, tests,
commits, branches, or external systems while reviewing.

Review in a fresh context. The caller passes the repository path, the candidate (a commit, a
patch, or the working tree with the revision it started from), and the task's goal, non-goals,
and acceptance condition (`none` when there are none). Do not take the implementing session's
chat or rationale: the contract says what the change is for, and the rationale would only argue
that it passes. Without a repository path, a candidate, and a goal, return `INCOMPLETE`. Judge
the change against that contract, not against a design you would have preferred. A violation
that falls under a non-goal is not a finding.

When the repository root has a `REVIEW.md`, read it first: what matters in each area, what
failure looks like there, sensitive paths, and paths to skip.

If the direction itself rests on unverified facts, send the work to
`reality-first-engineering` first; this review does not rationalize an unverified design.

## Route

- The candidate changes an acceptance surface (listed in `REVIEW.md`, or under an evaluation
  directory such as `eval`, `benchmark`, `harness`, `grader`, `golden`, `oracle`, or
  `autoresearch` when there is no `REVIEW.md`) → finish this review, then the caller sends the
  acceptance claim to `behavioral-acceptance-review`. An acceptance surface changed without
  the user's approval is a finding: changing it changes the requirement.
- Otherwise review only the structural risks the candidate introduces.

Run the scanner to locate candidates quickly. Pass the revision the change started from, so
changes that are already committed stay visible:

```bash
python3 <skill-dir>/scripts/design_integrity.py --cwd <repo> --base <start-revision> [--format json]
```

It reports newly added exception boundaries, swallowed exceptions, default returns after an
exception, and `acceptance_changes`. It is a locator, not proof: a quiet scanner is not `PASS`,
and a name such as `fallback`, `V2`, or `Compat` is not evidence of a problem.

## Structural gates

The candidate must be a stable commit, patch, or snapshot; if it changes during review,
return `INCOMPLETE`. For each suspected risk, establish:

- **Reachability** — the real caller, input, contract, or observed failure;
- **Ownership** — whether this layer owns recovery, degradation, cleanup, or translation;
- **Architecture** — why the existing abstraction cannot carry the correct behavior; a new
  layer must be a **deep module** (a small interface hiding substantial implementation), so a
  shallow pass-through wrapper or an interface with a single implementation is a finding;
- **Proportion** — whether the change is limited to the root cause.

## Findings

- Handling that a real caller or failure reaches, in the layer that owns it, is legitimate: it
  is not a finding, and never recommend deleting it just to silence the scanner.
- A `FAIL` finding names the input, caller, or event that reaches the flagged code and what
  then goes wrong. A finding argued only from reading the code goes under LIMITATIONS as
  unverified; on its own it makes the status `INCOMPLETE`, not `FAIL`.
- Keep the modality of an unverified finding: write "may", never state it as a fact. This is
  the same rule as listing it as unverified.
- Tag a finding in code the candidate did not introduce `[pre-existing]`. It does not change
  the status; report it so it can become a separate ticket.
- Name the class of a finding and list every instance in the candidate, not only the first one.
- When the caller passes an earlier report for the same work, check whether its findings were
  fixed and do not repeat them.

## Report

Return exactly:

```text
STATUS: PASS | FAIL | INCOMPLETE
SUMMARY: <number of findings by severity and how many are pre-existing, or "No findings.">
TARGET: <candidate and the revision it started from>
FINDINGS:
- [P1/P2/P3 | pre-existing] <exact file and line> — <class>: <what reaches it, what goes wrong, and the simpler correction>
LIMITATIONS:
- <unverified findings, written with "may", and the input that would show them; scope or evidence gaps>
RULE:
- <only when a finding repeats a known failure class: the check that would catch it and where it runs>
```

- `PASS` — no confirmed finding in scope;
- `FAIL` — at least one finding reached by a real caller, input, or event;
- `INCOMPLETE` — the candidate, scope, or evidence is unavailable, or only unverified findings remain.

One review per candidate. After fixes, at most one targeted re-review of the changed scope.

## Close the loop

When a confirmed finding repeats a failure class this project has hit before, name the
check that would have caught it (a test, a lint or dependency rule, a script, or a hook) and
where it runs. Only when no check can detect the failure, name a prose rule instead, say why
it cannot be checked, and where it belongs: the area's line in `REVIEW.md` for what reviews
should look at, otherwise the project's `AGENTS.md` or the living doc that owns the area.
Recommend it in the report; the review itself stays read-only. With a project map, it is added
through a `task` ticket (see `project-map`).
