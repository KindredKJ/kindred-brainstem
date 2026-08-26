# ADR 0015: BRAINSTEM Port Zero client boundary

**Decision:** BRAINSTEM remains protected and exposes no external stratum endpoint. It may emit only a signed, purpose-bound, classified request to the authoritative Port Zero over configured mutual TLS. This repository does not implement or impersonate Port Zero authority.

**Consequences:** Missing endpoint, certificates, valid signature, matching identity, live expiry, or idempotency integrity blocks traversal. Submission produces only `REQUESTED`/boundary-observed truth, never provider success. External callbacks and reconciliation remain the authority of the UQR and domain systems.
