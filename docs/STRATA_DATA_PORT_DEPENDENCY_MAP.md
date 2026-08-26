# Strata Data Port dependency map

The protected client requires `KINDRED_PORT_ZERO_URL`, `KINDRED_PORT_ZERO_CA`, `KINDRED_PORT_ZERO_CERT`, and `KINDRED_PORT_ZERO_KEY`. The URL must use HTTPS and the CA/client certificate/client key establish mutual TLS. Requests additionally require a valid local Ed25519 authorization binding the request ID and payload hash.

All dependencies fail closed. There is no production mock, emulator, automatic fallback, direct provider adapter, or direct external BRAINSTEM route. Full completion additionally depends on the inaccessible superstructure registry/UQR, authoritative identity services, Emit Core, domain ports, provider contracts, reconciliation implementations, and deployment infrastructure.
