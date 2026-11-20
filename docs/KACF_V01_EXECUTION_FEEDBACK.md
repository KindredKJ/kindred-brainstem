# KACF v0.1 + PoECL batch writer — measured and verifiable upgrade

This change extends the existing live Kindred workforce path. It does **not**
create a parallel brain, second worker pool, fictitious economic value, or
unverified capabilities.

## Implemented BRAINSTEM integration

- `brainstem/fabric/autopoietic.py` creates `kacf_forks`,
  `kacf_metabolics`, and `kacf_capability_incidents` in the **same**
  `StateStore` as the workforce tasks, immutable contracts and signed receipts.
- Every newly accepted workforce task prepares deterministic, bounded,
  **inert** candidate state deltas for `succeeded`, `failed`, `timed_out`.
  No candidate executes workers, makes payments or mutates the cognition model.
- BRAINSTEM collapses `succeeded` in the **same SQLite transaction** as
  its already-validated EMIT receipt and `verified_complete` transition.
  A replay does not double-count the outcome, a modified branch digest fails,
  and an unsigned or invalid receipt cannot enter that transaction.
- `@v2` receipts include measured local EMIT operation elapsed nanoseconds.
  KACF records a deliberately labelled **unit utility proxy per observed
  execution second**. This is not net economic value, calibrated intelligence
  growth, compute joules, power savings or financial profit.
- After a capability has at least three measured successful executions,
  the deterministic branch policy may choose `speculative`. This creates
  an **inert precomputed branch map**, not parallel inference.
- The deterministic operator can create **recovery proposals** only for
  actual dead-letter/expired tasks. This does not synthesize, compile or
  promote unknown worker programs and does not mark unobserved workers online.
- The cognitive orchestration summary (and `/world`) exposes the KACF
  evidence projection, with statuses and provenance.

## Implemented EMIT batching alternative

- `cloud/api/causal_batch.py` signs and verifies **1–128 actual queued
  completion receipts** under one `BEGIN IMMEDIATE` SQLite transaction.
  It enforces matching immutable task IDs, worker/action/input hashes, unique
  IDs, strict sequence and previous-hash chaining, tamper rejection and
  all-or-nothing rollback.
- No SQLite durability setting is weakened and no live worker queue behavior
  is silently changed. The existing single-completion commit path remains
  authoritative until head-to-head measurements and live E2E results justify
  an optional backpressure-controlled batch queue.
- `scripts/benchmark_poecl_batch.py` measures **single vs batched**
  persistence throughput using two separate temporary databases and
  validates each complete ledger after all writes. It produces JSON and
  records whether the live worker path uses batching (currently false).

## Tests

```powershell
# BRAINSTEM checkout:
python -m pytest -q tests/test_autopoietic_fabric.py tests/test_workforce_orchestration.py

# EMIT checkout:
python -m pytest -q cloud/tests/test_causal_batch.py cloud/tests/test_causal_attestation.py
python scripts/benchmark_poecl_batch.py --records 250 --batch-size 25 --output benchmark-poecl-batch.json
```

The cross-service PowerShell runner `scripts/run_workforce_integration_e2e.ps1`
also validates that a genuine `runtime.snapshot@v2` task collapses an ESCCB
branch in `/world` and records elapsed-time evidence without inventing energy.

## Evidence boundary

Local isolated core tests have passed, but the latest new BRAINSTEM/EMIT
integration changes and batch path need testing on the founder's Windows
Python environments. The previous measured durable throughput (27.49
receipts/sec, 500 samples) was on the old **single-receipt path**. It
must not be presented as the speed of the new batch writer.

Full recursive ZK proof, HCM arbitrary worker synthesis, calibrated MCVP
cost-to-value pricing, zero-consensus federation, and hardware attestation
are not implemented by these changes.
