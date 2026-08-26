from datetime import UTC, datetime, timedelta

import pytest

from brainstem.model.authority import FounderAuthority
from brainstem.runtime.store import StateStore
from brainstem.strata.contracts import (
    BOUNDARY_TRANSITIONS,
    BoundaryState,
    PortRequest,
    require_boundary_transition,
)
from brainstem.strata.gateway import PortZeroBlocked, PortZeroGateway


def request(
    authority,
    request_id="KREQ-1",
    tenant="tenant-a",
    source="brainstem-protected-client",
):
    payload_hash = "a" * 64
    item = PortRequest(
        request_id=request_id,
        correlation_id="corr-1",
        trace_id="trace-1",
        organization_id="org-a",
        tenant_id=tenant,
        environment="development",
        source_port_id=source,
        target_port_id="communications-external",
        requester_identity="service:brainstem",
        actor_identity="workload:brainstem",
        founder_authorization_reference="PENDING-SIGNATURE",
        capability="communications.intent",
        action="submit",
        purpose="authorized-test-boundary-validation",
        data_classification="INTERNAL",
        disclosure_scope=["intent-reference"],
        retention_policy="AUDIT_30D",
        payload_reference="vault://payload/1",
        payload_hash=payload_hash,
        policy_version="1",
        protocol_version="1",
        requested_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        idempotency_key=f"idempotency-{request_id}-0001",
        evidence_requirements=["provider-receipt", "reconciliation"],
    )
    approval = authority.sign(
        f"strata:submit:{request_id}",
        "strata-egress",
        item.authorization_digest(),
        environment="development",
        tenant=tenant,
    )
    return item.model_copy(update={"founder_authorization_reference": approval})


def setup(tmp_path):
    store = StateStore(tmp_path / "state.db", tmp_path / "events.jsonl")
    authority = FounderAuthority(store, tmp_path / "authority")
    authority.initialize()
    return store, authority, PortZeroGateway(store, authority)


def test_production_boundary_fails_closed_without_mtls_and_persists_audit(
    tmp_path, monkeypatch
):
    for name in (
        "KINDRED_PORT_ZERO_URL",
        "KINDRED_PORT_ZERO_CA",
        "KINDRED_PORT_ZERO_CERT",
        "KINDRED_PORT_ZERO_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    store, authority, gateway = setup(tmp_path)
    item = request(authority)
    with pytest.raises(PortZeroBlocked, match="missing"):
        gateway.submit(item)
    persisted = store.query("SELECT * FROM strata_boundary_requests")[0]
    assert persisted["state"] == BoundaryState.BLOCKED
    events = store.query("SELECT * FROM strata_boundary_events ORDER BY sequence")
    assert [(event["prior_state"], event["new_state"]) for event in events] == [
        (BoundaryState.CREATED, BoundaryState.IDENTITY_VERIFIED),
        (BoundaryState.IDENTITY_VERIFIED, BoundaryState.BLOCKED),
    ]
    event = events[-1]
    assert event["new_state"] == BoundaryState.BLOCKED
    assert (
        "vault://" not in event["payload"]
    )  # transition audit excludes payload reference
    assert gateway.status()["production_simulation_enabled"] is False


def test_tampered_or_self_declared_authority_is_denied(tmp_path):
    store, authority, gateway = setup(tmp_path)
    item = request(authority)
    item.founder_authorization_reference = "KSIGN-NOT-REAL"
    with pytest.raises(PortZeroBlocked, match="authorization"):
        gateway.submit(item)
    assert (
        store.query("SELECT state FROM strata_boundary_requests")[0]["state"]
        == "BLOCKED"
    )


def test_request_modified_after_signature_is_denied(tmp_path):
    store, authority, gateway = setup(tmp_path)
    item = request(authority)
    item.disclosure_scope = ["caller-expanded-scope"]
    with pytest.raises(PortZeroBlocked, match="authorization"):
        gateway.submit(item)
    assert (
        store.query("SELECT state FROM strata_boundary_requests")[0]["state"]
        == "BLOCKED"
    )


def test_idempotency_reuse_with_changed_request_is_blocked(tmp_path):
    _, authority, gateway = setup(tmp_path)
    first = request(authority)
    with pytest.raises(PortZeroBlocked):
        gateway.submit(first)
    changed = request(authority, request_id="KREQ-2")
    changed.idempotency_key = first.idempotency_key
    with pytest.raises(PortZeroBlocked, match="different content"):
        gateway.submit(changed)


def test_expired_request_never_enters_durable_outbox(tmp_path):
    store, authority, gateway = setup(tmp_path)
    item = request(authority)
    item.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(ValueError, match="expired"):
        gateway.submit(item)
    assert store.query("SELECT * FROM strata_boundary_requests") == []


def test_migration_is_additive_and_survives_restart(tmp_path):
    path = tmp_path / "state.db"
    store = StateStore(path)
    session = store.create_session("legacy")
    reopened = StateStore(path)
    assert reopened.session(session["id"])["id"] == session["id"]
    assert reopened.query("SELECT version FROM schema_migrations")[-1] == {"version": 5}


def test_external_source_cannot_impersonate_protected_brainstem(tmp_path):
    store, authority, gateway = setup(tmp_path)
    item = request(authority, source="external-port")
    with pytest.raises(PortZeroBlocked, match="protected client identity"):
        gateway.submit(item)
    assert (
        store.query("SELECT state FROM strata_boundary_requests")[0]["state"]
        == "BLOCKED"
    )


def test_all_declared_strata_transitions_are_reachable_and_all_others_rejected():
    states = set(BoundaryState)
    assert set(BOUNDARY_TRANSITIONS) == states
    for prior in states:
        for new in states:
            if new in BOUNDARY_TRANSITIONS[prior]:
                require_boundary_transition(prior, new)
            else:
                with pytest.raises(ValueError, match="Illegal Strata"):
                    require_boundary_transition(prior, new)
