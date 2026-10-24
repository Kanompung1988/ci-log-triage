# CI Log Triage

Source: `/mnt/data/areazero_lab/2026-10-24/agent-skills/examples/synthetic-ci.log`

Inspected 9 line(s) — 3 signal group(s).

## typescript — compiler
Evidence hits: 1. Confidence hint: high (pattern specificity only).
**Hypothesis:** TypeScript compile/type-check error.
**Next verification:** Run the exact typecheck command locally and inspect the cited source location.

Evidence (redacted):
- Line 4: `src/api/client.ts:42:11 - error TS2345: Argument of type string is not assignable to number.`

## missing-dependency — dependency
Evidence hits: 1. Confidence hint: high (pattern specificity only).
**Hypothesis:** Dependency resolution failed.
**Next verification:** Verify lockfile, package install step, module name and execution working directory.

Evidence (redacted):
- Line 8: `ModuleNotFoundError: No module named 'payment_client'`

## test-assertion — test
Evidence hits: 1. Confidence hint: moderate (pattern specificity only).
**Hypothesis:** Test expectation failed.
**Next verification:** Re-run the single named test and compare actual versus expected behavior; avoid changing expectations without evidence.

Evidence (redacted):
- Line 6: `FAILED tests/test_payments.py::test_create_payment - AssertionError: expected 201, got 200`

This tool does not assert a root cause or execute code, tests, network access, or repairs.
