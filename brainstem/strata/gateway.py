"""Fail-closed production client from protected BRAINSTEM to Port Zero."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import ssl
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from brainstem.model.authority import FounderAuthority
from brainstem.runtime.store import StateStore, now
from brainstem.strata.contracts import (
    BoundaryState,
    BoundaryTransition,
    PortRequest,
    PortResponse,
    require_boundary_transition,
)


class PortZeroBlocked(RuntimeError):
    """The protected request cannot safely cross the boundary."""


class PortZeroGateway:
    """BRAINSTEM-side client only; it never assumes Port Zero authority."""

    def __init__(self, store: StateStore, authority: FounderAuthority) -> None:
        self.store = store
        self.authority = authority

    def status(self) -> dict[str, Any]:
        required = {
            "endpoint": os.getenv("KINDRED_PORT_ZERO_URL"),
            "ca_certificate": os.getenv("KINDRED_PORT_ZERO_CA"),
            "client_certificate": os.getenv("KINDRED_PORT_ZERO_CERT"),
            "client_key": os.getenv("KINDRED_PORT_ZERO_KEY"),
        }
        missing = [name for name, value in required.items() if not value]
        return {
            "status": "NOT_CONFIGURED" if missing else "AVAILABLE",
            "role": "protected_brainstem_client",
            "authority": "Port Zero authority remains external to this package",
            "missing": missing,
            "production_simulation_enabled": False,
        }

    def _transition(
        self,
        request: PortRequest,
        prior: BoundaryState,
        new: BoundaryState,
        reason: str,
        evidence: str | None = None,
    ) -> None:
        require_boundary_transition(prior, new)
        transition = BoundaryTransition(
            actor=request.actor_identity,
            authority=request.founder_authorization_reference,
            timestamp=datetime.now(UTC),
            prior_state=prior,
            new_state=new,
            reason=reason,
            evidence_reference=evidence,
            correlation_id=request.correlation_id,
            trace_id=request.trace_id,
            request_id=request.request_id,
        )
        payload = transition.model_dump_json()
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT state FROM strata_boundary_requests WHERE request_id=?",
                (request.request_id,),
            ).fetchone()
            if current is None:
                raise PortZeroBlocked("Boundary request is not durable")
            if current["state"] != prior:
                raise PortZeroBlocked(
                    f"Stale Strata transition expected {prior} but found {current['state']}"
                )
            db.execute(
                "INSERT INTO strata_boundary_events(request_id,tenant_id,prior_state,new_state,payload_hash,payload,created_at) VALUES(?,?,?,?,?,?,?)",
                (
                    request.request_id,
                    request.tenant_id,
                    prior,
                    new,
                    digest,
                    payload,
                    now(),
                ),
            )
            updated = db.execute(
                "UPDATE strata_boundary_requests SET state=?,updated_at=? WHERE request_id=? AND state=?",
                (new, now(), request.request_id, prior),
            )
            if updated.rowcount != 1:
                raise PortZeroBlocked("Concurrent Strata transition rejected")

    def submit(self, request: PortRequest) -> PortResponse:
        request.ensure_live()
        serialized = request.model_dump_json()
        request_digest = hashlib.sha256(serialized.encode()).hexdigest()
        try:
            with self.store.connect() as db:
                timestamp = now()
                db.execute(
                    "INSERT INTO strata_boundary_requests VALUES(?,?,?,?,?,?,?,?)",
                    (
                        request.request_id,
                        request.tenant_id,
                        request.idempotency_key,
                        request_digest,
                        BoundaryState.CREATED,
                        None,
                        timestamp,
                        timestamp,
                    ),
                )
                db.execute(
                    "INSERT INTO strata_boundary_outbox(request_id,payload_reference,payload_hash,created_at) VALUES(?,?,?,?)",
                    (
                        request.request_id,
                        request.payload_reference,
                        request.payload_hash,
                        timestamp,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            existing = self.store.query(
                "SELECT * FROM strata_boundary_requests WHERE request_id=? AND idempotency_key=?",
                (request.request_id, request.idempotency_key),
            )
            if not existing or not hmac.compare_digest(
                existing[0]["payload_hash"], request_digest
            ):
                raise PortZeroBlocked(
                    "idempotency identity reused with different content"
                ) from exc
            if existing[0]["response"]:
                return PortResponse.model_validate_json(existing[0]["response"])
            raise PortZeroBlocked(
                f"duplicate request retained in state {existing[0]['state']}"
            ) from exc
        if request.source_port_id != "brainstem-protected-client":
            self._transition(
                request,
                BoundaryState.CREATED,
                BoundaryState.BLOCKED,
                "external source attempted protected BRAINSTEM client identity",
            )
            raise PortZeroBlocked(
                "BRAINSTEM requests must originate from its protected client identity"
            )
        expected_action = f"strata:submit:{request.request_id}"
        authorization_digest = request.authorization_digest()
        if not self.authority.verify(
            request.founder_authorization_reference,
            expected_action,
            authorization_digest,
            expected_environment=request.environment,
            expected_tenant=request.tenant_id,
            expected_scope="strata-egress",
        ):
            self._transition(
                request,
                BoundaryState.CREATED,
                BoundaryState.BLOCKED,
                "cryptographic authorization failed",
            )
            raise PortZeroBlocked(
                "cryptographic founder or delegated authorization failed"
            )
        self._transition(
            request,
            BoundaryState.CREATED,
            BoundaryState.IDENTITY_VERIFIED,
            "cryptographic founder identity and request binding verified",
        )
        state = self.status()
        if state["status"] != "AVAILABLE":
            self._transition(
                request,
                BoundaryState.IDENTITY_VERIFIED,
                BoundaryState.BLOCKED,
                "Port Zero mTLS dependency not configured",
            )
            raise PortZeroBlocked(f"Port Zero unavailable: missing {state['missing']}")
        endpoint = str(os.environ["KINDRED_PORT_ZERO_URL"])
        if not endpoint.startswith("https://"):
            self._transition(
                request,
                BoundaryState.IDENTITY_VERIFIED,
                BoundaryState.BLOCKED,
                "Port Zero endpoint did not use HTTPS",
            )
            raise PortZeroBlocked("Port Zero production endpoint must use HTTPS")
        try:
            context = ssl.create_default_context(
                cafile=os.environ["KINDRED_PORT_ZERO_CA"]
            )
            context.load_cert_chain(
                os.environ["KINDRED_PORT_ZERO_CERT"],
                os.environ["KINDRED_PORT_ZERO_KEY"],
            )
        except (OSError, ssl.SSLError) as exc:
            self._transition(
                request,
                BoundaryState.IDENTITY_VERIFIED,
                BoundaryState.BLOCKED,
                f"Port Zero mTLS material failed validation: {type(exc).__name__}",
            )
            raise PortZeroBlocked("Port Zero mTLS material is invalid") from exc
        if not self.authority.authorize(
            request.founder_authorization_reference,
            expected_action,
            authorization_digest,
            expected_environment=request.environment,
            expected_tenant=request.tenant_id,
            expected_scope="strata-egress",
        ):
            self._transition(
                request,
                BoundaryState.IDENTITY_VERIFIED,
                BoundaryState.BLOCKED,
                "authorization nonce was invalid or already consumed",
            )
            raise PortZeroBlocked("cryptographic authorization replay blocked")
        self._transition(
            request,
            BoundaryState.IDENTITY_VERIFIED,
            BoundaryState.POLICY_APPROVED,
            "signed request is bound to the declared policy version and purpose",
        )
        self._transition(
            request,
            BoundaryState.POLICY_APPROVED,
            BoundaryState.ROUTE_AUTHORIZED,
            "configured Port Zero route passed local fail-closed gates",
        )
        body = request.model_dump_json().encode()
        self._transition(
            request,
            BoundaryState.ROUTE_AUTHORIZED,
            BoundaryState.SUBMITTED_TO_PORT_ZERO,
            "mTLS submission initiated",
        )
        http_request = urllib.request.Request(  # noqa: S310 -- endpoint is HTTPS-only
            endpoint.rstrip("/") + "/v1/requests",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": request.idempotency_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 -- validated HTTPS plus mTLS
                http_request, context=context, timeout=20
            ) as response:
                result = json.loads(response.read())
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            self._transition(
                request,
                BoundaryState.SUBMITTED_TO_PORT_ZERO,
                BoundaryState.FAILED,
                f"Port Zero transport failed: {type(exc).__name__}",
            )
            raise PortZeroBlocked(
                "Port Zero transport failed without fallback"
            ) from exc
        try:
            parsed = PortResponse.model_validate(result)
        except ValidationError as exc:
            self._transition(
                request,
                BoundaryState.SUBMITTED_TO_PORT_ZERO,
                BoundaryState.FAILED,
                "response contract validation failed",
            )
            raise PortZeroBlocked("Port Zero response contract was invalid") from exc
        if not hmac.compare_digest(parsed.request_id, request.request_id):
            self._transition(
                request,
                BoundaryState.SUBMITTED_TO_PORT_ZERO,
                BoundaryState.FAILED,
                "response request identity mismatch",
            )
            raise PortZeroBlocked("Port Zero response request identity mismatch")
        self._transition(
            request,
            BoundaryState.SUBMITTED_TO_PORT_ZERO,
            BoundaryState.PORT_REPORTED,
            "signed response requires reconciliation",
        )
        self.store.execute(
            "UPDATE strata_boundary_requests SET response=?,updated_at=? WHERE request_id=?",
            (parsed.model_dump_json(), now(), request.request_id),
        )
        return parsed
