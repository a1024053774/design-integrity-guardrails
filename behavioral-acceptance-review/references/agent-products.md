# Agent products

Read this only when the target is a model-driven Agent product (support, sales, knowledge,
workflow, coding, voice, computer-use, batch). It adds what a generic acceptance audit misses.

## Capability profile

Answer each axis for the product. Only a `yes` adds checks; a `no` is written as `N/A` with a reason.

| Axis | Applies when the product has | Verify |
| --- | --- | --- |
| Orchestration / state | workflows, state machines, queues, sub-tasks | real registered steps; replay, cancel, crash recovery; side effects happen at most once |
| Streaming / async | streamed output, events, callbacks, long jobs | event order, termination, reconnect, duplicates; no draft or unsafe content leaks early |
| Retrieval / memory | search, RAG, vector stores, memory, citations | answers change when sources change; source, version, and scope checked externally; deleted or expired memory stops applying |
| Identity / scope | accounts, roles, tenants, resource scopes | identity comes from a trusted boundary, never from client fields or model output; cross-scope access through lists, downloads, caches, errors, replays; revocation |
| Interaction surface | web, desktop, mobile, public API, CLI | the real user journey per entry point; visible state reconciles with backend state |
| Files / media | text, tables, PDF, images, audio, video in or out | real decoding and field-level content; parse failures classified, never replaced by placeholder output |
| External side effects | write tools, messages, record changes, payments | authorization and idempotency before; read back from the authoritative record after; accepted, processed, sent, and delivered kept distinct |
| Operations | deploy, canary, monitoring, rate limits, rollback | recovery from cold start and dependency loss; rollback checked against the real candidate, config, and data |

## Evidence layers

| Layer | Can prove | Cannot be extrapolated to |
| --- | --- | --- |
| L0 static | call graph, config, packaged resources | runtime behavior |
| L1 isolated logic | contracts, state machine, permissions, idempotency, fault injection | real model understanding, real external systems |
| L2 local real dependencies | actual model, parser, or store on isolated data | real network, channels, production accounts |
| L3 real entry point | separate process, socket, UI, event transport, full journey | production writes |
| L4 pre-production | real auth, gateway, channels, sandboxed authoritative records | production traffic |
| L5 production canary | authorized small-scope business under monitoring | future inputs |

A fix found through the real entry point is closed only by a rerun through that entry point on a
build that contains the fix, not by an in-process test turning green.

## Weak assertions that must not pass alone

| Weak assertion | How it lies | Check instead |
| --- | --- | --- |
| HTTP 200 plus a status field present | the status is `error` | the product's real success state, input counts, and safe-degradation contract |
| Two 200s with equal `message_id` means idempotent | both IDs are missing or empty | a non-empty correlation ID, persisted response, execution count, side-effect readback |
| `intent_method=model` means the model understood | every input gets the same intent or answer | external truth, paired variants, unseen inputs, action boundaries |
| Import `count > 0` means success | wrong items, scope, or body | item-by-item reconciliation with the source and authoritative record |
| Health 200 means the UI works | the page is an empty shell | the real journey plus visible and backend state together |
| Non-empty output after a parse failure | placeholder or fallback text | independent parsing, content truth, failure classification |
| A trace shows the tool or node name | the log was written, the call never happened | real calls, persisted state, side-effect counts |

## AI-typical wrong implementations

For each key contract, ask what wrong implementation would still turn the checks green, and make
sure at least one check rejects it: fixed output or ignored input; always refuse, escalate, or
succeed; a faked log or trace; configuration that is written but not applied; swallowed
exceptions or silent downgrade; a test that knows the answer; missing N−1/N/N+1, empty,
wrong-type, duplicate, or revoked-permission boundaries. The target check must fail on a business
assertion; an empty collection, missing dependency, or crash does not count as catching it.

## Severity and release verdict

- `P0`: security, permissions, sensitive data, unauthorized critical actions, data integrity. Any valid failure blocks release.
- `P1`: core committed tasks, key configuration, important facts, duplicate side effects, recovery. The affected scope cannot ship.
- `P2`/`P3`: record impact, owner, deadline, and retest condition before accepting.

Per case, use `PASS`, `FAIL`, `BLOCKED`, `INCOMPLETE`, `NOT_RUN`, or `N/A`. When asked for a release
decision, add `RELEASE: FULL_GO | LIMITED_GO | NO_GO | INCOMPLETE` to the report. `FULL_GO` needs every
committed P0/P1 case passing at the committed layer on the current candidate. `LIMITED_GO` names the
exact internal or pre-production scope and lists what is deferred; it never implies production readiness.
Identify the candidate by commit or tag; do not compute digests of candidates or evidence folders.
Save raw inputs, outputs, and exit codes before judging, and never overwrite an earlier red result.

## Automated judges

A new automated judge (an LLM grader, a review agent, an auto-approval rule) starts in shadow mode:
it only suggests, and a human confirms its verdicts until it meets an accuracy bar written down in
advance. After that, sample its automatic approvals with a risk-weighted rate (higher tiers sampled
more), record misjudgments as evidence, and return it to shadow mode when the error rate rises.
