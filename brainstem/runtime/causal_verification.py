"""Independent BRAINSTEM validation of EMIT PoECL process-trace attestations.

Checks receipt bindings, domain-separated Merkle tree and causal digest.
The caller must additionally verify the receipt's HMAC with the shared key.
This is process-level provenance, not hardware, syscall, or consensus proof.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

CAUSAL_SCHEMA = "kindred.poecl.process_trace.v1"
DOMAIN = b"KINDRED-POECL-v1\x00"
_ALLOWED_EVENTS = {"queue.dequeued", "operator.completed", "operator.failed", "audit.persisted"}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _merkle_root(events: list[dict[str, Any]]) -> str:
    if not isinstance(events, list) or not 1 <= len(events) <= 16:
        raise ValueError("invalid causal trace length")
    if len(_canonical(events)) > 4096:
        raise ValueError("causal trace too large")
    leaves = [hashlib.sha256(b"\x00" + _canonical(item)).digest() for item in events]
    while len(leaves) > 1:
        if len(leaves) % 2:
            leaves.append(leaves[-1])
        leaves = [
            hashlib.sha256(b"\x01" + leaves[i] + leaves[i+1]).digest()
            for i in range(0, len(leaves), 2)
        ]
    return leaves[0].hex()


def verify_process_attestation(receipt: dict[str, Any]) -> bool:
    """Verify a signed receipt's causal payload only; HMAC is checked separately."""
    if not isinstance(receipt, dict):
        return False
    proof = receipt.get("causal_proof")
    if not isinstance(proof, dict):
        return False
    try:
        if proof.get("schema_version") != CAUSAL_SCHEMA:
            return False
        bindings = (
            ("task_id", "task_id"), ("worker_id", "worker_id"),
            ("capability_uri", "action"), ("input_sha256", "payload_sha256"),
            ("outcome", "status"),
        )
        if any(proof.get(left) != receipt.get(right) for left, right in bindings):
            return False
        if proof.get("output_sha256") != hashlib.sha256(_canonical(receipt["output"])).hexdigest():
            return False
        if (proof.get("attestation_level") != "emit_local_process_instrumentation"
            or proof.get("energy_source") != "unmeasured"
            or proof.get("energy_joules_est") is not None):
            return False
        if type(proof.get("sequence")) is not int or proof["sequence"] < 1:
            return False
        if type(proof.get("elapsed_ns")) is not int or proof["elapsed_ns"] < 0:
            return False
        previous = proof.get("prev_chain_hash")
        if not isinstance(previous, str) or len(previous) != 64:
            return False
        events = proof.get("trace_events")
        if not isinstance(events, list) or any(
            not isinstance(e, dict) or e.get("event") not in _ALLOWED_EVENTS
            for e in events
        ):
            return False
        expected_events = [
            "queue.dequeued",
            "operator.completed" if receipt.get("status") == "completed" else "operator.failed",
        ]
        if receipt.get("status") == "completed":
            expected_events.append("audit.persisted")
        if [e["event"] for e in events] != expected_events:
            return False
        if events[0].get("worker_id") != receipt.get("worker_id"):
            return False
        if events[1].get("capability_uri") != receipt.get("action"):
            return False
        if receipt.get("status") == "completed" and events[2].get("task_id") != receipt.get("task_id"):
            return False
        if proof.get("trace_merkle_root") != _merkle_root(events):
            return False
        chain_hash = proof.get("chain_hash")
        if not isinstance(chain_hash, str) or len(chain_hash) != 64:
            return False
        material = {k: v for k, v in proof.items() if k != "chain_hash"}
        expected = hashlib.sha256(DOMAIN + _canonical(material)).hexdigest()
        return hmac.compare_digest(chain_hash, expected)
    except (KeyError, ValueError, TypeError, OverflowError):
        return False
