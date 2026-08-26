# Founder approval security

Local founder authority uses an OpenSSL Ed25519 keypair. The private key is generated outside the repository under `~/.kindred/authority` with mode `0600`; only its public-key hash is an identity. Signed records bind action hash, scope, checkpoint hash, timestamp, expiration, and revocation. Modified payloads fail verification.

Recovery: stop the runtime, back up the private/public key and database offline, verify permissions, restore both together, then verify existing signatures. Loss of the private key prevents new approvals; replacement does not validate old records. No remote approval endpoint is provided.
