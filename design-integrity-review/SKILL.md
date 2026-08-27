---
name: design-integrity-review
description: Review a current code diff in an isolated context for unjustified catch/except handling, fallbacks, compatibility paths, duplicate or parallel APIs, and local patches that bypass root-cause ownership. Use before finishing non-trivial changes when these constructs appear or when a completion gate requests the review. Do not use for documentation-only or formatting-only changes.
---

# Design Integrity Review

Review the current diff or the range named by the caller. This is a read-only review: do not edit files, create commits, or write a clean-review ledger entry.

## Preserve Context Independence

- If the host already started this skill in an isolated or forked context, review directly.
- Otherwise, when fresh subagents are available, delegate the review to one fresh subagent. Give it the original task, diff or range, active repository instructions, and read-only repository access. Do not give it the implementing agent's rationale or conclusions.
- If isolation is unavailable, disclose that limitation and still apply the evidence requirements below.

## Establish the Evidence

1. Inspect the original task and active `AGENTS.md`, `CLAUDE.md`, or repository rules.
2. Inspect the diff, then read only the relevant callers, tests, contracts, and neighboring abstractions needed to judge it.
3. Run `scripts/design_integrity.py` from this skill directory against the repository as a routing aid. Treat its output as risk markers, not findings.
4. Independently inspect newly added public symbols and alternate entry points even when the scanner reports none.

## Apply the Gates

For every added catch/except, fallback, retry or compatibility path, duplicate API, or special branch, determine:

- **Reachability:** Which real caller, input, current contract, observed failure, or credible risk requires it?
- **Ownership:** Does this layer actually own recovery, degradation, cleanup, or error translation? Is the original cause preserved and observable?
- **Architecture:** Why can the existing abstraction or interface not carry the correct behavior? Would changing the root-cause layer and its required callers yield one clearer production path?
- **Proportion:** Is the change scoped to the root cause without unrelated cleanup or a bug-sized architectural rewrite?

A comment or an implementing-agent explanation is not evidence by itself. Missing evidence means the construct is unjustified.

## Report

Report only confirmed, actionable findings. Each finding must contain:

1. exact file and line;
2. the reachable caller, input, failure, or contract;
3. the concrete maintenance or behavioral failure;
4. the simpler coherent correction.

If no item meets that standard, report that the review passed. If the only correct fix exceeds current scope or authorization, report the root cause, required change, impact, and smallest options; do not propose a side path and do not call the unimplemented repair complete.

Create or update a project ledger only after a real recurring class is confirmed and the current task authorizes that documentation change. Promote mechanically decidable classes to deterministic checks; keep semantic classes in this review.
