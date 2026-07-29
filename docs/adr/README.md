# Strata Data Port ADR register

The following decisions are accepted as the canonical target architecture but remain implemented only where identified by repository evidence:

1. Protocol → Tesseract → Unified Quad Runtime ↕ StrataFortress → Modular Core.
2. Port Zero is the sole protected-boundary authority; this repository implements only its BRAINSTEM client.
3. External ports remain on the StrataFortress Y-axis.
4. The UQR owns horizontal routing; Kindred Cloud connects to it but is not it.
5. External systems cannot call BRAINSTEM directly.
6. Durable state uses additive migrations, append-only transition events, and a transactional outbox.
7. Registry discovery never grants trust or route authorization.
8. Kindred providers, transport rails, regulated partners, and infrastructure vendors are distinct classifications.
9. G3T Connected is the communications provider of record; implementation is blocked pending its authority repository.
10. RetroBank is the canonical financial interface; no regulated status or transfer is claimed.
11. Kindred One is organization/tenant-first B2B enablement; authority remains unresolved.
12. WATT-BLOCK is evidence-only and has no energy control authority.
13. Truth, evidence, provider, rail, recipient, and reconciliation states remain separate.
14. Founder implementation authorization is recorded, but runtime requests still require cryptographic authorization.
15. Simulated adapters are test-only and cannot be a production boundary route.

ADR 0015 implements the BRAINSTEM-side protected client consequences. The remaining decisions belong in the unavailable superstructure and domain repositories and are therefore `BLOCKED`, not locally fabricated.
