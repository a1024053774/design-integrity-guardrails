---
name: evidence-first-testing
description: Preserve failure evidence and prove that tests detect the behavior they claim to cover. Use for bug fixes, regression coverage, test changes, flaky-test investigation, and behavior changes with a concrete acceptance contract; do not use for documentation-only or formatting-only work.
---

# Evidence-First Testing

A green test proves only that the current code satisfies that test. To call a test regression
evidence, show the counterfactual: the focused signal rejects the faulty behavior and accepts
the repaired behavior.

## Choose the claim and evidence

First classify what the red state means:

- **Defect reproduction:** the current implementation violates an existing contract.
- **Contract test:** requested new or changed behavior is not implemented yet; an expected red
  state is not proof of a pre-existing defect.
- **Flaky or environment-specific failure:** logs, inputs, seeds, timing, versions, and
  environment details must travel with the result.

Before implementing or repairing the claimed behavior, obtain the smallest reliable signal:

- an existing failing test;
- a new focused test or minimal reproducer;
- a build, type-check, request, trace, or command that exposes the defect;
- for flaky or environment-specific failures, preserved logs, inputs, seeds, timing, and environment details.

Record the exact command or procedure, inputs, expected result, observed result, environment,
and exit status. Confirm that the signal fails for the expected reason. An unrelated setup,
fixture, import, or environment failure is not red-state evidence.

## Enforce the gate

For bug fixes, regression tests, and behavior changes with a testable contract, use this order:

1. Inspect and diagnose without changing the relevant behavior.
2. Run the focused signal against the current code and record the red-state result.
3. Make the smallest justified implementation change.
4. Re-run the same signal and confirm it turns green.
5. Run the smallest broader suite or check that is required by the repository, the user, or
   a still-credible failure category. Broaden only when the changed contract, boundary, or
   failure mode requires it; do not use a fixed test count or line-count comparison as a
   substitute for evidence.

Do not begin the implementation step until a focused signal exists. A bug fix requires
defect-specific red-state evidence; a new behavior may use an expected-red contract test.
If no safe red state or counterfactual can be established, report the evidence as INCOMPLETE
instead of calling the test regression-proof. Reading code, adding diagnostic logging, or
creating a test fixture is allowed when it does not repair or bypass the claim.

When a plan or task-status interface is available, keep implementation pending until the
evidence step is complete.

## Validate the test itself

When adding or changing tests:

- Make assertions observable and specific to the claimed behavior.
- Keep the expected result independent from production code, constants, helpers, or generated
  answers where practical; a test should not merely restate the implementation.
- Verify that a new regression test fails on the faulty implementation.
- Check that a repaired flaky test is stable across enough repetitions to support the claim.
- Add coverage for distinct acceptance conditions or credible failure modes, not to reach a
  preset number of cases.
- A test may be more involved than the implementation when it exercises a real boundary or
  independent oracle; explain that evidence need instead of judging by code length.
- Avoid weakening, deleting, skipping, or broadly mocking a failing assertion merely to make the suite green.
- Distinguish product defects, test defects, and environment defects before editing.

## Recover when the fix came first

If behavior was already changed, restore the missing counterfactual by running the test against one of:

- the parent or known-bad revision;
- the implementation with the relevant fix temporarily reverted;
- a targeted mutation that recreates the defect.

Preserve unrelated working-tree changes while doing this. If no safe counterfactual is feasible,
state that the post-change pass is real but the regression proof is unverified; a first-run pass
is not sufficient.

## Report evidence

Report:

- **Focused signal:** command or procedure and the input;
- **Before change:** red result and why it is the expected failure;
- **Change:** the smallest behavior change made;
- **After change:** green result from the same signal;
- **Broader checks:** the relevant suite or check and its result;
- **Limitations:** missing reproduction, unsafe counterfactual, or environment constraint.

State limitations plainly when the original failure could not be reproduced.
