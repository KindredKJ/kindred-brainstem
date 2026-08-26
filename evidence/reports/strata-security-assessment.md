# Strata boundary security assessment

## Verified controls

* Deny by default when Port Zero URL, CA, client certificate, or key is missing.
* HTTPS and mutual TLS are mandatory.
* Ed25519 authorization binds the exact submit action, payload hash, environment, tenant, scope, approver key identity, issuance/expiry, and one-time nonce.
* Expired, tampered, duplicate-conflicting, self-declared external-source, and unconfigured requests fail closed.
* Request payloads are referenced and hashed; append-only transition records exclude the sensitive payload reference.
* Durable idempotency keys, outbox records, transition hashes, tenant identifiers, and nonce consumption survive restart and concurrent delivery.
* A closed transition map rejects every undeclared or stale transition; request state and append-only audit transition commit in one SQLite transaction.
* No direct provider adapter or simulated production transport exists in the Strata package.

## Remaining blockers

The authoritative Port Zero server, registry attestation, UQR route policy, callback verification, domain reconciliation, Emit Core signatures, certificate rotation service, encryption-at-rest key management, rate limiting, and production deployment controls are unavailable. Loopback diagnostic APIs inherit the runtime's current lack of caller authentication and must not be exposed remotely.
