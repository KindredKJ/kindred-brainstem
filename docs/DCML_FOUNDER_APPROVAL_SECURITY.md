# Founder approval security

Local founder authority uses Ed25519 through Python `cryptography`. The private key is generated outside the repository under `~/.kindred/authority` with mode `0600`; the approver identity is derived from the SHA-256 fingerprint of the trusted public key, never from a public name or request field. Version 2 signed envelopes bind the decision (`APPROVED` or `REJECTED`), exact action and action digest, scope, immutable payload digest, configured environment and tenant, approver key identity, issuance and mandatory expiry, and a cryptographically random nonce. Modified or malformed payloads fail signature/hash validation. Security-sensitive string and digest bindings use constant-time comparison; Ed25519 verification uses the established library implementation.

Execution accepts only the expected signed decision. Rejected, expired, revoked, superseded, wrong-context, wrong-payload, and wrong-action records cannot authorize an action. Migration 5 adds a unique nonce ledger and durable submission claims. Authorization consumes the nonce atomically; a replay cannot execute again. Idempotent decision submission returns the already committed result without consuming or processing the decision twice.

Learning approval, promotion, and activation are distinct protected actions. Each transition requires a separate one-time decision bound to `learning:approve:<id>`, `learning:promote:<id>`, or `learning:activate:<id>` and the same immutable learning digest; an earlier approval is not reused as a standing execution grant.

For Strata egress, the signed payload digest covers a canonical representation of every immutable request field except the signature reference itself, including the referenced content hash, route, capability, disclosure, retention, policy, protocol, timing, and idempotency identity.

Legacy unsigned `approvals` records and founder-name declarations remain readable for historical compatibility but cannot authorize native DCML, learning promotion/activation, policy promotion/rollback, cognitive rollback, or Strata egress. Existing version 1 signed records lack required bindings and therefore fail closed; operators must issue a new version 2 decision.

Recovery: stop the runtime, back up the private/public key and database offline, verify permissions, restore both together, then verify existing signatures. Loss of the private key prevents new approvals; replacement does not validate old records. Never copy a consumed nonce to a fresh database to make it reusable. No remote approval endpoint is provided.
