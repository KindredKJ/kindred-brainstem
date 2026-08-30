# Brainstem ↔ DECA execution-kernel architecture

## Canonical orientation

There is exactly one BRAINSTEM: the current `BrainstemModel` with native governed DCML.

BRAINSTEM is the top-level persistent developmental intelligence. It owns cognitive identity and state, memory, beliefs, world modeling, causal and counterfactual reasoning, strategy formation and selection, specialist routing, prediction, evaluation, credit assignment, skill formation, calibration, governed learning, checkpoints, promotion, and cognitive rollback.

DECA is not a second brain and is not embedded as a competing cognitive runtime. DECA is a separately versioned execution kernel/runtime that BRAINSTEM invokes when an intended outcome requires governed effects, reservations, transactions, recovery, or canonical execution receipts.

## Responsibility boundary

### BRAINSTEM owns

- purpose and objective interpretation
- contextual grounding and memory
- cognitive world state
- reasoning, predictions, and counterfactuals
- strategy formation and selection
- specialist/model/tool selection
- capability-gap identification
- candidate skill formation
- evaluation, reward, and causal credit assignment
- calibration, consolidation, and governed learning
- cognitive checkpoints, promotion, and rollback

### DECA owns

- execution-intent admission
- capability and authority validation
- resource reservation
- transactional effect execution
- idempotency and replay protection
- compensation and recovery
- canonical execution state transitions
- effect receipts and execution lineage
- canonical outcome records supplied back to BRAINSTEM

### Independent verification

When an independent verifier such as Panoptic is configured, it provides re-observation, contradiction, and independent verification evidence. Neither BRAINSTEM cognition nor DECA effect execution may silently self-declare an externally consequential outcome verified.

## Control flow

```text
objective / purpose
      |
      v
BRAINSTEM + DCML
      |
      | reason / predict / select strategy
      | identify required capability
      v
DECA execution request
      |
      | admit / authorize / reserve / execute / recover
      v
real effect + execution receipt
      |
      v
independent observation / verification when required
      |
      v
canonical outcome evidence
      |
      v
BRAINSTEM + DCML
      |
      | evaluate / assign credit / calibrate / learn
      v
improved future cognition
```

## Repository and versioning rule

BRAINSTEM and DECA remain separate canonical repositories and separately versioned products. BRAINSTEM consumes a pinned compatible DECA release or protocol version; DECA never requires a duplicate BRAINSTEM implementation.

Do not create `brainstem-v2`, `brainstem-legacy`, `deca-v2`, `deca-v3`, or other per-version repositories. Evolution happens through commits, release branches when needed, immutable tags, release artifacts, and explicit compatibility contracts in the canonical repositories.

## Non-duplication invariants

1. No legacy BRAINSTEM engine may be reintroduced as a second cognitive authority beside `BrainstemModel`/DCML.
2. DECA must not implement BRAINSTEM memory, cognition, strategy learning, skill learning, or DCML.
3. BRAINSTEM must not bypass DECA for external effects that are assigned to DECA's execution jurisdiction.
4. DECA must not self-grant authority based on a BRAINSTEM recommendation.
5. BRAINSTEM may propose; DECA must independently enforce its execution contract.
6. Verified DECA outcomes may become governed BRAINSTEM learning evidence; execution success never automatically widens BRAINSTEM or DECA authority.

## Product-level definition

**BRAINSTEM is the evolving intelligence. DECA is the governed execution kernel it uses to turn selected strategies into controlled, recoverable, evidenced consequences.**
