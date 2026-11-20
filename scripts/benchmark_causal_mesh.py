#!/usr/bin/env python3
"""Reproducible bilateral causal transcript and signed-Merkle folding benchmark.

Usage:
  python scripts/benchmark_causal_mesh.py --records 100000 --batch-size 1000 --output causal_mesh.json

Uses local, synthetic records and test-generated Ed25519 keys. Does not
transfer real money, measure real energy, prove zero-knowledge claims,
or establish externally authenticated settlement finality.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstem.fabric.causal_mesh import (
    BilateralEntanglementRecord, CausalMeshNode, EquivocationFraudWarrant,
    GENESIS_HASH, canonical_json, sha256_hex,
)
from brainstem.fabric.proof_folder import CausalProofFolder, FoldedCausalEnvelope


def percentiles(samples_ns: list[int]) -> dict[str, float]:
    ordered = sorted(samples_ns)
    def p(q: float) -> float:
        return round(ordered[max(0, int((len(ordered) - 1) * q))] / 1000, 3)
    return {
        "samples": len(samples_ns),
        "p50_us": p(.5), "p95_us": p(.95), "p99_us": p(.99),
        "mean_us": round(statistics.fmean(samples_ns) / 1000, 3),
    }


def make_record(initiator, peer, *, record_id, sequence, head, receipt_hash,
                timestamp, micro_value=250, joules=.015):
    header = {
        "record_id": str(record_id), "seq_no": sequence,
        "initiator_pub_hex": initiator.public_key_hex,
        "counterparty_pub_hex": peer.public_key_hex,
        "initiator_prev_hash": head, "counterparty_prev_hash": head,
        "poecl_receipt_hash": receipt_hash,
        "value_delta_micro_units": micro_value,
        "joules_settled": joules,
        "timestamp_utc": timestamp.astimezone(timezone.utc).isoformat(),
    }
    signed_bytes = canonical_json(header)
    return BilateralEntanglementRecord(
        **{**header, "timestamp_utc": timestamp},
        initiator_sig_hex=initiator.sign_commitment(signed_bytes),
        counterparty_sig_hex=peer.sign_commitment(signed_bytes),
    )


def run_benchmark(total_txs: int = 100000, batch_size: int = 1000,
                  *, repeats: int = 1000) -> dict:
    if total_txs < 1 or batch_size < 1 or total_txs % batch_size:
        raise ValueError("positive total_txs must be divisible by positive batch_size")
    if not 10 <= repeats <= 10000:
        raise ValueError("repeats out of range [10,10000]")
    initiator = CausalMeshNode()
    counterparty = CausalMeshNode()
    folder = CausalProofFolder(initiator.private_key)
    fixed_time = datetime.now(timezone.utc)
    synthetic_trace = sha256_hex(b"synthetic_not_a_live_PoECL_worker_receipt")
    records: list[BilateralEntanglementRecord] = []

    signing_start = time.perf_counter_ns()
    head = GENESIS_HASH
    for seq in range(1, total_txs + 1):
        row = make_record(
            initiator, counterparty, record_id=uuid4(), sequence=seq, head=head,
            receipt_hash=synthetic_trace, timestamp=fixed_time,
        )
        head = row.commitment_hash()
        records.append(row)
    signing_ns = time.perf_counter_ns() - signing_start

    verified_start = time.perf_counter_ns()
    for record in records:
        if isinstance(counterparty.verify_and_commit(record), EquivocationFraudWarrant):
            raise AssertionError("non-conflicting benchmark settlement rejected")
    verified_ns = time.perf_counter_ns() - verified_start
    if counterparty.chain_head != head:
        raise AssertionError("peer final chain head did not match signed transcript")

    original = records[0]
    malicious = make_record(
        initiator, counterparty, record_id=uuid4(), sequence=1,
        head=GENESIS_HASH, receipt_hash=synthetic_trace,
        timestamp=fixed_time, micro_value=999999,
    )
    before = time.perf_counter_ns()
    conflict = counterparty.verify_and_commit(malicious)
    fraud_detection_ns = time.perf_counter_ns() - before
    if not isinstance(conflict, EquivocationFraudWarrant) or not conflict.verify():
        raise AssertionError("conflicting signed transcript lacks verifiable evidence")

    folded_start = time.perf_counter_ns()
    batches: list[FoldedCausalEnvelope] = []
    first_batch_hashes: list[str] = []
    for start in range(0, total_txs, batch_size):
        env, hashes = folder.fold_records(
            records[start:start + batch_size],
            verify_individual_sigs=False,  # all records just verified by counterparty
        )
        batches.append(env)
        if not first_batch_hashes:
            first_batch_hashes = hashes
    superenv = folder.recursive_fold_envelopes(batches)
    folded_ns = time.perf_counter_ns() - folded_start
    if not superenv.verify_envelope(trusted_aggregator_pub_hex=folder.pub_hex):
        raise AssertionError("super-envelope signature invalid")
    if superenv.record_count != total_txs or superenv.final_chain_head != head:
        raise AssertionError("fold violates committed transcript bounds")
    if superenv.net_value_delta_micro_units != total_txs * 250:
        raise AssertionError("folded micro-unit accounting is inconsistent")
    if superenv.total_energy_nanojoules != total_txs * 15_000_000:
        raise AssertionError("folded nanjoule accounting is inconsistent")

    leaf_index = min(512, batch_size - 1)
    leaf_witness = folder.generate_inclusion_proof(first_batch_hashes, leaf_index)
    super_witness = folder.generate_inclusion_proof(
        [env.envelope_hash() for env in batches], 0
    )
    def inclusion() -> bool:
        return (
            batches[0].verify_envelope(trusted_aggregator_pub_hex=folder.pub_hex)
            and leaf_witness.verify(
                leaf_hash=records[leaf_index].commitment_hash(),
                trusted_root=batches[0].merkle_root,
            )
            and super_witness.verify(
                leaf_hash=batches[0].envelope_hash(), trusted_root=superenv.merkle_root
            )
            and superenv.verify_envelope(trusted_aggregator_pub_hex=folder.pub_hex)
        )
    if not inclusion():
        raise AssertionError("two-level settlement inclusion verification failed")

    invalid_root = "f" * 64 if leaf_witness.expected_root != "f" * 64 else "e" * 64
    if leaf_witness.verify(
        leaf_hash=records[leaf_index].commitment_hash(), trusted_root=invalid_root
    ):
        raise AssertionError("membership witness accepted incorrect trusted root")

    verify_env_samples: list[int] = []
    verify_membership_samples: list[int] = []
    for _ in range(repeats):
        begin = time.perf_counter_ns()
        if not superenv.verify_envelope(trusted_aggregator_pub_hex=folder.pub_hex):
            raise AssertionError("super-envelope verification failure")
        verify_env_samples.append(time.perf_counter_ns() - begin)
        begin = time.perf_counter_ns()
        if not inclusion():
            raise AssertionError("nested inclusion verification failure")
        verify_membership_samples.append(time.perf_counter_ns() - begin)

    return {
        "benchmark_id": "kindred.causal_mesh.signed_merkle_fold.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "sample_kind": "synthetic_co_signed_transcript_no_real_value_or_energy_measurements",
        "cryptography": "Ed25519_bilateral_signatures_and_aggregator_attested_merkle",
        "zero_knowledge_proof": False,
        "trusted_aggregator_required": True,
        "total_settlements": total_txs,
        "batch_size": batch_size,
        "batch_envelope_count": len(batches),
        "bilateral_signing_tps": round(total_txs / (signing_ns / 1e9), 2),
        "ed25519_verify_and_commit_tps": round(total_txs / (verified_ns / 1e9), 2),
        "fraud_warrant_detection_single_sample_us": round(fraud_detection_ns / 1000, 3),
        "folding_ms": round(folded_ns / 1e6, 3),
        "envelope_verify_microbench": percentiles(verify_env_samples),
        "nested_inclusion_microbench": percentiles(verify_membership_samples),
        "super_envelope_size_bytes": len(superenv.model_dump_json().encode("utf-8")),
        "super_envelope_fold_depth": superenv.fold_depth,
        "merkle_inclusion_witness_levels": len(leaf_witness.sibling_hashes) + len(super_witness.sibling_hashes),
        "net_signed_value_micro_units": superenv.net_value_delta_micro_units,
        "net_claimed_energy_nanojoules": superenv.total_energy_nanojoules,
        "final_chain_head": superenv.final_chain_head,
        "integrity_checks_passed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=100000)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--repeat-verification", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_benchmark(
        args.records, args.batch_size, repeats=args.repeat_verification
    )
    encoded = json.dumps(result, sort_keys=True, indent=2)
    print(encoded, flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
