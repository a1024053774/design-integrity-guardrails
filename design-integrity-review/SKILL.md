---
name: design-integrity-review
description: Self-check your own change for structural shortcuts — swallowed or broad exception handling, fallback/retry paths, compatibility branches, parallel APIs, and patches that bypass root-cause ownership — before you report it done, and route to behavioral-acceptance-review when an evaluation surface changed. Use once at a completion checkpoint; not for documentation-only, formatting-only, or routine test maintenance.
---

# Design Integrity Review

A completion checklist that the implementing agent runs on its own change, in its own context,
before it reports the change done. There is no separate reviewer. Judge the change against the
task's goal, non-goals, and acceptance condition, not against a design you would have preferred.

If the direction itself rests on unverified facts, send the work to
`reality-first-engineering` first; this review does not rationalize an unverified design.

## Route

- Change touches an evaluation directory (`eval`, `benchmark`, `harness`, `grader`, `golden`,
  `oracle`, `autoresearch`) or another explicit acceptance surface → finish this checklist,
  then send the acceptance claim to `behavioral-acceptance-review`, which audits it independently.
- Otherwise check only the structural risks introduced by the change.

Run the scanner before you commit to locate candidates quickly. It compares the working tree
with `HEAD`, so it cannot see changes you already committed; read `git diff <base>` for those.

```bash
python3 <skill-dir>/scripts/design_integrity.py --cwd <repo> [--format json]
```

It reports newly added exception boundaries, swallowed exceptions, and default returns after
an exception. It is a locator, not proof: a quiet scanner is not `PASS`, and a name such as
`fallback`, `V2`, or `Compat` is not evidence of a problem.

## Structural gates

For each scanner hit and each fallback, retry, compatibility branch, parallel API, or new
layer you added, establish:

- **Reachability** — the real caller, input, contract, or observed failure;
- **Ownership** — whether this layer owns recovery, degradation, cleanup, or translation;
- **Architecture** — why the existing abstraction cannot carry the correct behavior; a new
  layer must be a **deep module** (a small interface hiding substantial implementation), so a
  shallow pass-through wrapper or an interface with a single implementation is a finding;
- **Proportion** — whether the change is limited to the root cause.

## Act and report

Fix each confirmed finding in the same change: remove what nothing reaches, and move handling
to the layer that owns it. Keep legitimate handling; never delete it just to silence the
scanner. A finding that falls under a non-goal or outside the task becomes a separate ticket,
not part of this change.

In the completion report, give each item its conclusion (kept, with the caller or failure that
reaches it; removed; moved; or deferred to a ticket) and return one of:

- `PASS` — no confirmed finding remains in scope;
- `FAIL` — a confirmed finding remains unfixed: exact file and line, reachable evidence, the
  concrete failure or maintenance cost, and the simpler correction;
- `INCOMPLETE` — reachability or ownership needs evidence you do not have.

Run it once per completion checkpoint; edits it causes do not restart it.

## Close the loop

When a confirmed finding repeats a failure class this project has hit before, name the
check that would have caught it (a test, a lint or dependency rule, a script, or a hook) and
where it runs. Only when no check can detect the failure, name a prose rule instead, say why
it cannot be checked, and where it belongs: the project's `AGENTS.md` or the living doc that
owns the area. Recommend it in the report; add it only when it is in the task's scope. With a project
map, it is added through a `task` ticket (see `project-map`).
