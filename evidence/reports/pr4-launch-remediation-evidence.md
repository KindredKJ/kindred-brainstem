# BRAINSTEM PR #4 launch remediation evidence

Assessment date: 2026-08-17. Scope: local PR branch `feat/dcml-complete-learning-loop` at starting and final HEAD `7d2085efd35aae50cc32d2e62b67c65517e3d99f`, compared with `main` at `7ec86653a73c635b5bff69c4819ff050fafb6976`. No commit, push, merge, deployment, application/provider request, or production mutation was performed. Network use was limited to validation dependency/tool installation and the vulnerability-advisory query.

## Threat model and enforced invariants

The protected actions are native learning approval/promotion/activation, learning and cognitive rollback, experience admission to training, DCML policy promotion/rollback, and Strata egress. Threats considered are a caller forging the founder's public name, submitting a signed rejection as approval, modifying an action or payload after signature, crossing tenant/environment boundaries, using an expired/revoked/superseded/malformed record, replaying a nonce, racing duplicate deliveries, reusing an idempotency key for different content, manufacturing impossible audit transitions, and shipping a distribution that imports an undeclared dependency.

Authorization now requires an Ed25519 signature verified by `cryptography` over a canonical version 2 envelope containing the exact decision and action, SHA-256 action and payload digests, scope, configured environment and tenant, public-key-derived approver identity, issued/expiry timestamps, and a random nonce. Only the expected decision can authorize its exact operation. Constant-time comparison is used for bound strings and digests. The unique nonce ledger is consumed atomically. Public names and caller-controlled identity fields are display/audit data only.

Learning approval, promotion, and activation each consume a separate signed decision for their exact transition and immutable learning digest. The initial approval cannot be replayed as a general lifecycle grant.

The advanced skill-record helper does not treat a caller-supplied approval reference as authority: it retains that value as unverified audit input and writes only a `PROPOSED` skill record.

Chat and learning-decision submissions use durable SQLite claims keyed by type and idempotency key. The request hash and scope must match. `PROCESSING` prevents concurrent duplicate work, `COMPLETED` returns the original response, conflicting content fails closed, and failed/abandoned work is not silently retried under the same key.

## State transitions

The Strata boundary permits only these edges:

| Prior | Allowed next states |
|---|---|
| `CREATED` | `IDENTITY_VERIFIED`, `BLOCKED`, `CANCELLED`, `EXPIRED` |
| `IDENTITY_VERIFIED` | `POLICY_APPROVED`, `BLOCKED`, `CANCELLED`, `EXPIRED` |
| `POLICY_APPROVED` | `ROUTE_AUTHORIZED`, `BLOCKED`, `CANCELLED`, `EXPIRED` |
| `ROUTE_AUTHORIZED` | `SUBMITTED_TO_PORT_ZERO`, `BLOCKED`, `CANCELLED`, `EXPIRED` |
| `SUBMITTED_TO_PORT_ZERO` | `PORT_REPORTED`, `FAILED`, `EXPIRED` |
| `PORT_REPORTED` | `RECONCILIATION_PENDING`, `FAILED` |
| `RECONCILIATION_PENDING` | `RECONCILED`, `FAILED`, `CANCELLED` |
| `RECONCILED` | `EVIDENCE_VERIFIED`, `FAILED` |
| `EVIDENCE_VERIFIED` | `COMPLETED`, `FAILED` |
| Terminal states | No outgoing transitions |

The transition writer validates the declared edge, reads the current durable state under `BEGIN IMMEDIATE`, rejects stale state, and commits the state update and audit event together. Gateway success now enters each represented intermediate state instead of fabricating unreachable prior states.

## Canary definition

A canary evaluates the last `N` supplied cases in caller order, including both recorded boundary indices. A regression is `baseline correct AND candidate incorrect` for the same case. Passing requires `candidate success rate - baseline success rate > minimum_success_lift` and `regression_count <= max_regressions`. Defaults are a strict positive lift and zero regressions. The supplied baseline must match a fresh active-policy evaluation over the identical window. Records persist the definition, window, thresholds, baseline/candidate metrics, lift, and count.

## Targeted test matrix

| Risk | Evidence |
|---|---|
| Rejected decision / forged founder name | Approval remains `EVALUATED`; execution is denied |
| Modified or malformed signed payload / Strata request field | Canonical hash/signature verification fails |
| Wrong tenant or environment | Constant-time binding comparison fails |
| Expired, revoked, or superseded record | Verification and execution fail closed |
| Replay | First atomic nonce consumption succeeds; second fails |
| Duplicate delivery | Original completed response is returned; no second model call |
| Concurrent delivery | Two callers produce one model invocation / one decision transition |
| Canary boundaries and thresholds | Last-`N` boundaries, regression count, zero/one thresholds covered |
| Strata transitions | Every declared pair succeeds validation; every other enum pair is rejected |
| Installed distribution | Wheel installs into a fresh venv and imports model authority, runtime API, and Strata gateway outside the source tree |

## Commands and results

* `.venv\\Scripts\\python.exe -m pytest -q --basetemp build\\pytest-final-closure-3` — **62 passed in 34.51 seconds**.
* `.venv\\Scripts\\ruff.exe format --check brainstem\\adapters\\models brainstem\\model brainstem\\runtime brainstem\\strata brainstem_build_backend.py tests` — **32 files already formatted**.
* `.venv\\Scripts\\ruff.exe check brainstem\\adapters\\models brainstem\\model brainstem\\runtime brainstem\\strata brainstem_build_backend.py tests` — **all checks passed**, including the repository-configured security rules; justified suppressions are limited to parameterized/allowlisted SQL, deterministic non-security RNG, validated URL schemes, and list-form resolved subprocess calls.
* `.venv\\Scripts\\mypy.exe --ignore-missing-imports brainstem\\model\\authority.py brainstem\\runtime\\store.py brainstem\\runtime\\service.py brainstem\\runtime\\app.py brainstem\\strata\\contracts.py brainstem\\strata\\gateway.py brainstem\\model\\advanced.py brainstem\\model\\dcml.py brainstem\\model\\core.py` — **success, no issues in 9 source files**.
* `.venv\\Scripts\\python.exe -m compileall -q brainstem tests brainstem_build_backend.py` — **passed**.
* Tracked JSON/YAML/TOML parser sweep — **32 files parsed successfully**.
* AST runtime import-to-`pyproject.toml` reconciliation — third-party imports are `cryptography`, `fastapi`, `pydantic`, `rich`, `typer`, and `yaml`; **no undeclared imports**. (`uvicorn` is the declared runtime command dependency.)
* `.venv\\Scripts\\python.exe -m build --wheel --sdist --outdir dist` — built `kindred_brainstem-0.1.0a0-py3-none-any.whl` (SHA-256 `1F24AECC052DC0EA7028ADCFCDA61400298DDEFE95D8EAE0DDFCD2041270FFE3`) and `kindred_brainstem-0.1.0a0.tar.gz` (SHA-256 `1A1DF9B73E307019A47518A1FEC3F8E27CBA63AAA5C1ACE86314F9435AB5B274`).
* Wheel and sdist metadata inspection — both declare all seven runtime dependencies, including `cryptography>=46.0.0`; the wheel also declares the `dev` extra.
* Fresh isolated wheel install/import from a non-source working directory — **passed**, importing from `build/installed-smoke-final/Lib/site-packages` at version `0.1.0-alpha`; installed metadata contains `cryptography>=46.0.0`.
* `.venv\\Scripts\\python.exe -m pip check` — **no broken requirements**.
* `.venv\\Scripts\\pip-audit.exe --local --progress-spinner off` after upgrading validation-environment pip to `26.2.1` — **no known vulnerabilities found**; the unpublished local project itself is skipped because it is not on PyPI.
* `git diff --check` — **passed**.

## Deployment compatibility and migration

Migration 5 is additive: it creates `approval_nonces` and `submissions`; legacy session/model/learning/Strata tables are retained. Old binaries ignore the new tables, but rollback to an old binary would also remove enforcement from newly exposed calls and is not an acceptable production operating mode. Back up the SQLite database and Ed25519 keypair together before rollout.

The `/chat` and `/dcml/cycle` HTTP contracts now require a 16–200 character `idempotency_key`; the bundled client generates one and permits callers to retain/reuse it for retry. Learning approve/reject/promote/activate/rollback and cognitive rollback accept `approval_id`, not a founder name. Promotion and activation request bodies are therefore a security-required compatibility change. Version 1 decisions and legacy unsigned approvals cannot be migrated into authority; issue new version 2 decisions. Configure `KINDRED_ENVIRONMENT` and `KINDRED_TENANT` consistently before signing and executing decisions. Strata signers must use action `strata:submit:<request_id>`, scope `strata-egress`, the request environment/tenant, and `PortRequest.authorization_digest()`, which covers every request field except the signature reference.

## Rollback plan

Stop the loopback runtime and preserve the database, WAL/SHM files, JSONL audit, and authority keypair. Roll back application code and artifacts together. Migration 5 tables may remain because the migration is additive; do not delete nonce/submission records or copy consumed nonces into a fresh database. Restore the pre-rollout database/key backup only as one matched set. Rebuild and inspect both artifacts, then rerun the full suite and installed import smoke before restart. Keep external Strata routing disabled unless every external dependency gate is independently satisfied.

## Remaining limitations and blockers

Port Zero, UQR route policy, authoritative registry attestation, callback signatures, provider/rail receipts, reconciliation, certificate rotation, encryption-at-rest, and production deployment controls remain unavailable and unverified. The loopback runtime still lacks caller authentication and must not be exposed remotely. Private-key protection is filesystem permission based; no HSM/TPM integration or remote approval ceremony exists. A process crash after a durable `PROCESSING` claim remains fail-closed and requires operator reconciliation/new idempotency identity rather than automatic re-execution. No external production launch readiness, provider success, revenue, physical execution, or deployment is proven by these local checks.
