"""Typed BRAINSTEM-side contracts for the Strata Data Port Zero boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TruthClass(StrEnum):
    REQUESTED = "REQUESTED"
    INTERNALLY_OBSERVED = "INTERNALLY_OBSERVED"
    PORT_REPORTED = "PORT_REPORTED"
    KINDRED_PROVIDER_REPORTED = "KINDRED_PROVIDER_REPORTED"
    RAIL_REPORTED = "RAIL_REPORTED"
    RECIPIENT_CONFIRMED = "RECIPIENT_CONFIRMED"
    RECONCILED = "RECONCILED"
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"
    DISPUTED = "DISPUTED"
    UNKNOWN = "UNKNOWN"


class EvidenceState(StrEnum):
    NOT_RECORDED = "NOT_RECORDED"
    RECORDED = "RECORDED"
    HASH_VERIFIED = "HASH_VERIFIED"
    SIGNATURE_VERIFIED = "SIGNATURE_VERIFIED"
    RECEIPT_VERIFIED = "RECEIPT_VERIFIED"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
    INVALID = "INVALID"


class ReconciliationState(StrEnum):
    PENDING = "PENDING"
    PROVIDER_REPORTED = "PROVIDER_REPORTED"
    RAIL_REPORTED = "RAIL_REPORTED"
    RECIPIENT_CONFIRMED = "RECIPIENT_CONFIRMED"
    RECONCILED = "RECONCILED"
    DISPUTED = "DISPUTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    REVERSED = "REVERSED"


class BoundaryState(StrEnum):
    CREATED = "CREATED"
    IDENTITY_VERIFIED = "IDENTITY_VERIFIED"
    POLICY_APPROVED = "POLICY_APPROVED"
    ROUTE_AUTHORIZED = "ROUTE_AUTHORIZED"
    SUBMITTED_TO_PORT_ZERO = "SUBMITTED_TO_PORT_ZERO"
    PORT_REPORTED = "PORT_REPORTED"
    RECONCILIATION_PENDING = "RECONCILIATION_PENDING"
    RECONCILED = "RECONCILED"
    EVIDENCE_VERIFIED = "EVIDENCE_VERIFIED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


BOUNDARY_TRANSITIONS: dict[BoundaryState, frozenset[BoundaryState]] = {
    BoundaryState.CREATED: frozenset(
        {
            BoundaryState.IDENTITY_VERIFIED,
            BoundaryState.BLOCKED,
            BoundaryState.CANCELLED,
            BoundaryState.EXPIRED,
        }
    ),
    BoundaryState.IDENTITY_VERIFIED: frozenset(
        {
            BoundaryState.POLICY_APPROVED,
            BoundaryState.BLOCKED,
            BoundaryState.CANCELLED,
            BoundaryState.EXPIRED,
        }
    ),
    BoundaryState.POLICY_APPROVED: frozenset(
        {
            BoundaryState.ROUTE_AUTHORIZED,
            BoundaryState.BLOCKED,
            BoundaryState.CANCELLED,
            BoundaryState.EXPIRED,
        }
    ),
    BoundaryState.ROUTE_AUTHORIZED: frozenset(
        {
            BoundaryState.SUBMITTED_TO_PORT_ZERO,
            BoundaryState.BLOCKED,
            BoundaryState.CANCELLED,
            BoundaryState.EXPIRED,
        }
    ),
    BoundaryState.SUBMITTED_TO_PORT_ZERO: frozenset(
        {BoundaryState.PORT_REPORTED, BoundaryState.FAILED, BoundaryState.EXPIRED}
    ),
    BoundaryState.PORT_REPORTED: frozenset(
        {BoundaryState.RECONCILIATION_PENDING, BoundaryState.FAILED}
    ),
    BoundaryState.RECONCILIATION_PENDING: frozenset(
        {BoundaryState.RECONCILED, BoundaryState.FAILED, BoundaryState.CANCELLED}
    ),
    BoundaryState.RECONCILED: frozenset(
        {BoundaryState.EVIDENCE_VERIFIED, BoundaryState.FAILED}
    ),
    BoundaryState.EVIDENCE_VERIFIED: frozenset(
        {BoundaryState.COMPLETED, BoundaryState.FAILED}
    ),
    BoundaryState.COMPLETED: frozenset(),
    BoundaryState.FAILED: frozenset(),
    BoundaryState.BLOCKED: frozenset(),
    BoundaryState.CANCELLED: frozenset(),
    BoundaryState.EXPIRED: frozenset(),
}


def require_boundary_transition(prior: BoundaryState, new: BoundaryState) -> None:
    if new not in BOUNDARY_TRANSITIONS[prior]:
        raise ValueError(f"Illegal Strata boundary transition {prior} -> {new}")


class PortRequest(BaseModel):
    schema_version: str = "1.0"
    request_id: str
    correlation_id: str
    causation_id: str | None = None
    trace_id: str
    organization_id: str
    tenant_id: str
    environment: str
    source_port_id: str = "brainstem-protected-client"
    target_port_id: str
    requester_identity: str
    actor_identity: str
    delegated_authority: list[str] = Field(default_factory=list)
    founder_authorization_reference: str
    capability: str
    action: str
    purpose: str
    data_classification: str
    disclosure_scope: list[str]
    retention_policy: str
    payload_reference: str
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_version: str
    protocol_version: str
    requested_at: datetime
    expires_at: datetime
    idempotency_key: str = Field(min_length=16, max_length=200)
    evidence_requirements: list[str]

    @field_validator("requested_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value

    def ensure_live(self) -> None:
        if self.expires_at <= datetime.now(UTC):
            raise ValueError("request expired")

    def authorization_digest(self) -> str:
        """Digest every immutable request field except the signature reference."""
        payload = self.model_dump(
            mode="json", exclude={"founder_authorization_reference"}
        )
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


class PortResponse(BaseModel):
    schema_version: str = "1.0"
    response_id: str
    request_id: str
    source_port_id: str
    target_port_id: str
    port_status: str
    domain_status: str
    provider_status: str
    rail_status: str
    reconciliation_status: ReconciliationState
    evidence_status: EvidenceState
    truth_class: TruthClass
    result_reference: str | None = None
    receipt_reference: str | None = None
    evidence_references: list[str] = Field(default_factory=list)
    response_codes: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None


class BoundaryTransition(BaseModel):
    actor: str
    authority: str
    timestamp: datetime
    prior_state: BoundaryState
    new_state: BoundaryState
    reason: str
    evidence_reference: str | None = None
    correlation_id: str
    trace_id: str
    request_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
