---
name: review-md
description: Create or update a repository's REVIEW.md, the review contract that lists frozen acceptance surfaces, sensitive paths, what failure looks like in each area, and paths to skip. It scans the repository for candidates and asks the owner only what the code cannot answer. Use only when the user asks for it by name (review-md, "初始化/更新 REVIEW.md"). Do not run it on your own while doing other work.
---

# REVIEW.md

`REVIEW.md` at the repository root says how changes here are judged. The owner writes it; this
skill drafts it. Run it only when the user asks for it.

Who reads it:

- `design_integrity.py` and the Stop hook read only `## Acceptance surfaces`. Those paths are
  frozen while a change is implemented, and `REVIEW.md` itself is always frozen.
- `design-integrity-review` and `behavioral-acceptance-review` read all of it.

## Steps

1. **Read what exists.** An existing `REVIEW.md` means update mode. Also read `AGENTS.md` or
   `CLAUDE.md`, the README, the CI configuration, and the test layout.
2. **List candidates with evidence.** Name only paths that exist:
   - acceptance surfaces: end-to-end or contract tests, golden outputs, eval or benchmark
     directories, fixtures that encode the requirement;
   - sensitive paths: authentication, billing or payments, migrations and schemas, CI
     workflows, release or installer code, permissions, data deletion;
   - paths to skip: generated code, vendored code, lockfiles, snapshots;
   - the main areas of the code.
3. **Ask the owner one round**, and only what the code cannot answer:
   - which candidates are acceptance surfaces;
   - what failure looks like in each area, in one line;
   - which paths are sensitive.

   Do not guess these. A guessed contract that the owner approves at a glance is the failure
   this file exists to prevent.
4. **Write the draft** from the template below. Keep it short, about 40 lines. Show it to the
   owner and save it only after approval. Saving it changes an acceptance surface, so the Stop
   check flags it once: say in the reply that the user asked for it.
5. **Update mode.** When reviews keep raising the same kind of comment in an area, add one line
   under that area. Remove lines that no longer match the code. An acceptance surface changes
   only on the owner's word.

## Template

```markdown
# REVIEW.md

## Acceptance surfaces

Frozen during implementation. Changing one changes the requirement: revert it or ask the owner.

- `tests/e2e/**`

## Sensitive paths

A change here gets the high review tier: both reviews, then the owner reads the evidence.

- `src/billing/**` — failure looks like: a double charge or a lost refund

## What matters

- `src/api/` — failure looks like: <one line>
- `docs/` — failure looks like: it lies

## Skip

- `generated/**`
```

## Glob rules

- `**` crosses directories. `*` and `?` stay inside one directory.
- A path without a wildcard, or a path that ends in `/`, covers everything below it.
- Only list items whose first token is in backticks, or contains `/`, `*`, or `.`, count as
  paths. Write prose as a paragraph, not as a list item.
- An empty `Acceptance surfaces` section means the repository has none. Without the section,
  the scanner falls back to its directory convention (`eval`, `benchmark`, `golden`, `oracle`,
  and similar directory names).
