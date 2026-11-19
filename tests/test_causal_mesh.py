"""Bilateral Ed25519 causal transcript, aggregate claim, and two-level membership tests."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from brainstem.fabric.causal_mesh import (
    GENESIS_HASH, BilateralEntanglementRecord, CausalMeshNode,
    EquivocationFraudWarrant, canonical_json, sha256_hex,
)
from brainstem.fabric.proof_folder import CausalProofFolder, FoldedCausalEnvelope
from scripts.benchmark_causal_mesh import make_record


def _sample(size=10, *, energy=.015):
    a = CausalMeshNode()
    b = CausalMeshNode()
    now = datetime.now(timezone.utc)
    receipt = sha256_hex(b"synthetic-poecl-record")
    head = GENESIS_HASH
    records = []
    for seq in range(1, size + 1):
        record = make_record(
            a, b, record_id=uuid4(), sequence=seq, head=head,
            receipt_hash=receipt, timestamp=now, joules=energy,
        )
        head = record.commitment_hash()
        records.append(record)
    return a, b, records


def test_bilateral_record_signatures_and_peer_chain():
    a, b, records = _sample(20)
    assert records[0].verify_bilateral_signatures()
    for record in records:
        assert b.verify_and_commit(record) == record
    assert b.chain_head == records[-1].commitment_hash()
    assert b.next_seq_no == 21
    assert b.verify_and_commit(records[-1]) == records[-1]


def test_fraud_warrant_requires_two_authentic_conflicting_records():
    a, b, records = _sample(3)
    for record in records:
        b.verify_and_commit(record)
    first = records[0]
    conflict = make_record(
        a, b, record_id=uuid4(), sequence=1, head=GENESIS_HASH,
        receipt_hash=first.poecl_receipt_hash, timestamp=first.timestamp_utc,
        micro_value=40000,
    )
    witness = b.verify_and_commit(conflict)
    assert isinstance(witness, EquivocationFraudWarrant)
    assert witness.verify()
    assert b.chain_head == records[-1].commitment_hash()
    altered = witness.model_copy(update={"seq_no": 2})
    assert not altered.verify()


def test_fold_and_nested_proof_with_trusted_signer():
    a, b, records = _sample(33)
    for record in records:
        b.verify_and_commit(record)
    folder = CausalProofFolder(a.private_key)
    left, raw_left = folder.fold_records(records[:16])
    middle, raw_middle = folder.fold_records(records[16:32])
    right, raw_right = folder.fold_records(records[32:])
    aggregate = folder.recursive_fold_envelopes([left, middle, right])
    assert aggregate.fold_depth == 2
    assert aggregate.record_count == len(records)
    assert aggregate.final_chain_head == b.chain_head
    assert aggregate.net_value_delta_micro_units == 33 * 250
    assert aggregate.total_energy_nanojoules == 33 * 15_000_000
    assert aggregate.verify_envelope(trusted_aggregator_pub_hex=folder.pub_hex)
    wrong_key = CausalMeshNode().public_key_hex
    assert not aggregate.verify_envelope(trusted_aggregator_pub_hex=wrong_key)
    target = 7
    proof = folder.generate_inclusion_proof(raw_left, target)
    super_proof = folder.generate_inclusion_proof(
        [left.envelope_hash(), middle.envelope_hash(), right.envelope_hash()], 0
    )
    assert proof.verify(
        leaf_hash=records[target].commitment_hash(), trusted_root=left.merkle_root
    )
    assert super_proof.verify(
        leaf_hash=left.envelope_hash(), trusted_root=aggregate.merkle_root
    )
    assert not proof.verify(leaf_hash=records[8].commitment_hash(), trusted_root=left.merkle_root)
    corrupt_flags = proof.model_copy(update={
        "sibling_is_right": tuple(not bit for bit in proof.sibling_is_right),
    })
    assert not corrupt_flags.verify(
        leaf_hash=records[target].commitment_hash(), trusted_root=left.merkle_root
    )
    assert not super_proof.verify(
        leaf_hash=left.envelope_hash(), trusted_root=left.merkle_root
    )


def test_fold_refuses_broken_head_sequence_or_invalid_signature():
    a, b, records = _sample(4)
    folder = CausalProofFolder(a.private_key)
    with pytest.raises(ValueError, match="broken bilateral sequence"):
        folder.fold_records([records[0], records[2]])
    corrupted = records[1].model_copy(
        update={"counterparty_sig_hex": "0" * 128}
    )
    with pytest.raises(PermissionError, match="invalid bilateral"):
        folder.fold_records([records[0], corrupted])
    env, hashes = folder.fold_records(records)
    tampered = env.model_copy(update={"net_value_delta_micro_units": 999999})
    assert not tampered.verify_envelope(trusted_aggregator_pub_hex=folder.pub_hex)
    with pytest.raises(ValueError, match="invalid child envelope count"):
        folder.recursive_fold_envelopes([])


def test_records_deny_nan_energy_and_non_nanojoule_precision():
    a, b, records = _sample(1)
    body = records[0].model_dump()
    body["joules_settled"] = 0.0000000001
    with pytest.raises(ValueError, match="nanjoules"):
        BilateralEntanglementRecord.model_validate(body)
    body["joules_settled"] = float("nan")
    with pytest.raises(ValueError):
        BilateralEntanglementRecord.model_validate(body)


def test_mismatched_signing_parties_rejected():
    a, b, records = _sample(2)
    outsider = CausalMeshNode()
    with pytest.raises(PermissionError, match="does not involve"):
        outsider.verify_and_commit(records[0])


def test_benchmark_small_sample_has_real_metrics():
    from scripts.benchmark_causal_mesh import run_benchmark
    metrics = run_benchmark(40, 10, repeats=10)
    assert metrics["total_settlements"] == 40
    assert metrics["batch_envelope_count"] == 4
    assert metrics["super_envelope_fold_depth"] == 2
    assert metrics["integrity_checks_passed"] is True
    assert metrics["trusted_aggregator_required"] is True
    assert metrics["zero_knowledge_proof"] is False
    assert metrics["nested_inclusion_microbench"]["samples"] == 10
