# BRAINSTEM-native typed workforce execution

This design preserves the authoritative BRAINSTEM state database. EMIT Core is an optional local execution transport and must never be treated as an independent intelligence or proof of external agent execution.

## Built-in executable contracts

| Contract | Input | EMIT worker | Signed output |
| --- | --- | --- | --- |
| `runtime.snapshot@v1` | Empty JSON object | A live `foundation.signal` worker | Foundation readiness, lane count, observed live lane count, UTC timestamp |
| `signal.deliver@v1` | `{"signal":"..." }` | Any live EMIT signal-lane worker | Accepted lane, SHA-256 of signal, processed-count checkpoint |

A registered agent record is a declaration only and never enters the execution candidate set. Candidate selection requires a fresh `kindred_emit_core` signal-lane observation and an explicitly advertised matching capability.

## API contract

BRAINSTEM uses `X-Brainstem-Awareness-Key` equal to `BRAINSTEM_AWARENESS_KEY` for protected orchestration endpoints. EMIT uses `X-Kindred-Internal-Key` equal to `KINDRED_INTERNAL_SERVICE_KEY`. Never print either secret.

- `GET /contracts`: list immutable versions.
- `POST /contracts`: register an immutable new version (identical repeats are idempotent).
- `GET /contracts/{contract_id}`: inspect a version including retired versions.
- `DELETE /contracts/{contract_id}`: retire from *new dispatch*, preserving the historical schema for verifying receipts from tasks already leased.
- `POST /orchestration/dispatch`: submit a typed payload with `idempotency_key`, `contract_id`, optional `depends_on`, and `lease_seconds`. No goal or payload generation occurs in the operator.
- `GET /orchestration/tasks/{task_id}`: read durable task state and verified receipt.
- `POST /orchestration/tasks/{task_id}/renew`: extend an active lease within bounded budget if the worker is recently online.
- `GET /orchestration/cognitive-summary`: active leases and verified outcomes used in BRAINSTEM's `/world` and cognitive prompt context.
- `GET /orchestration/operator-events`: audited lifecycle decisions.

EMIT's already-implemented protected endpoints are `POST /runtime/workers/execute` (synchronously returns a durable signed queue receipt) and `GET /runtime/workers/tasks/{task_id}` (idempotent recovery). These intentionally differ from the proposed asynchronous callback shape: they avoid callback ordering races and reuse the **actual running** EMIT lane-worker queues.

## Execution verification

Each EMIT receipt signs canonical JSON using HMAC-SHA256 over all fields except `signature`. BRAINSTEM verifies the signature and binds task ID, worker ID, action, input digest, timestamp, allowed status and JSON Schema Draft 2020-12 output before atomically committing `task_receipts`. A verified outcome means **authenticated EMIT local queue execution**. It does **not** independently verify any of the 5 registered external agents or arbitrary filesystem/network side effects.

BRAINSTEM task states are `blocked`, `queued`, `leased`, `dispatched`, `verified_complete`, `failed`, `expired`, and `dead_letter`. The deterministic operator requeues bounded failures with exponential backoff, quarantines exhausted attempts, and releases DAG successors only when predecessor tasks have **both** a verified status and a stored receipt. A worker's circuit opens after 3 recorded failures with a 60-second cooldown. Retry always retains the same task ID and payload: EMIT's idempotency record prevents re-executing a previously completed task.

## Windows live integration

The isolated Windows test runner in `scripts/run_workforce_integration_e2e.ps1` clones or reuses both feature branches, installs and runs EMIT's worker tests and BRAINSTEM's awareness+orchestration tests, boots two loopback services, verifies authenticated inventory and rejection of anonymous requests, dispatches a real `runtime.snapshot@v1`, checks idempotent replay and its signed evidence in `/world`, then stops only the isolated EMIT process and checks the 65-second observation-expiry path.

Example on a machine with the previously verified test workspace:

```powershell
$repo = Join-Path $env:TEMP 'kindred-brainstem-integration'
$work = Join-Path $env:TEMP 'Kindred-Workforce-E2E-2a303bebd9e647609f8bdcee2cfa21c7'
git -C $repo pull --ff-only
if ($LASTEXITCODE -ne 0) { throw 'Integration runner update failed' }
pwsh -NoProfile -File (Join-Path $repo 'scripts/run_workforce_integration_e2e.ps1') -ReuseWorkspace $work
```

### Current evidence boundary

The earlier awareness-only live E2E passed (14 EMIT lane instances, 14 BRAINSTEM observations, 0 after isolated EMIT shutdown, 14 records retained). The **new typed-contract + queue-execution** E2E has been committed and must be run before claiming this new milestone passes. Likewise, do not extrapolate 10,000-worker throughput or <50ms detection from unbenchmarked code.
