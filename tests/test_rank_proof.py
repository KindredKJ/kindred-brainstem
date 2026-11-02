"""Rank-prover contract tests. All leaderboards here are fabricated test fixtures.

Passing tests validate signatures and ranking logic, NOT external performance.
"""
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from brainstem.benchmarks.rank_proof import assess_snapshot


D = "a" * 64


def _fixture(kindred_score=90, competitor_score=50):
    payload = {
        "schema_version": 1,
        "benchmark": "arc-agi-3",
        "benchmark_version": "2026",
        "issuer_name": "FAKE TEST ISSUER",
        "board_type": "PUBLIC_PROVISIONAL",
        "evaluated_at": "2026-11-02T10:00:00Z",
        "source_url": "https://arcprize.org/leaderboard",
        "metric": "score_percent",
        "score_direction": "higher",
        "dataset_sha256": D,
        "evaluator_sha256": D,
        "protocol_sha256": D,
        "conditions_sha256": D,
        "total_entries": 2,
        "rows": [
            {
                "system_id": "kindred-research-test",
                "system_name": "Kindred TEST ONLY + provider MODEL",
                "configuration": "BRAINSTEM_STATIC",
                "provider_model": "TEST_PROVIDER/MODEL",
                "conditions_sha256": D,
                "score": kindred_score,
            },
            {
                "system_id": "other-research-test",
                "system_name": "Other TEST ONLY",
                "configuration": "DIRECT",
                "provider_model": "TEST_PROVIDER/MODEL",
                "conditions_sha256": D,
                "score": competitor_score,
            },
        ],
    }
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo
    )
    def sign(obj):
        raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        return raw, key.sign(raw)
    return payload, sign, public


def test_signed_test_fixture_can_rank_first_without_claiming_global_agi():
    data, sign, pub = _fixture()
    blob, signature = sign(data)
    result = assess_snapshot(blob, signature, pub, "kindred-research-test")
    assert result["signature_valid"] is True
    assert result["rank_status"] == "LEADER_IN_SIGNED_SNAPSHOT"
    assert result["rank"] == 1
    assert result["global_number_one_claim_supported"] is False
    assert result["authority_independently_verified"] is False
    assert result["external_score_independently_reproduced"] is False


def test_signed_fixture_loses_when_competitor_has_higher_score():
    data, sign, pub = _fixture(40, 80)
    blob, signature = sign(data)
    result = assess_snapshot(blob, signature, pub, "kindred-research-test")
    assert result["rank_status"] == "NOT_FIRST_IN_SIGNED_SNAPSHOT"
    assert result["rank"] == 2


def test_signed_fixture_tie_is_not_unique_first():
    data, sign, pub = _fixture(80, 80)
    blob, signature = sign(data)
    result = assess_snapshot(blob, signature, pub, "kindred-research-test")
    assert result["rank_status"] == "TIED_FIRST_IN_SIGNED_SNAPSHOT"
    assert result["ties_at_score"] == 2


def test_tampered_signed_snapshot_is_untrusted():
    data, sign, pub = _fixture()
    blob, signature = sign(data)
    corrupted = blob.replace(b'"score":90', b'"score":99')
    assert corrupted != blob
    result = assess_snapshot(corrupted, signature, pub, "kindred-research-test")
    assert result["rank_status"] == "UNTRUSTED"
    assert result["signature_valid"] is False


def test_key_substitution_is_untrusted():
    data, sign, _pub = _fixture()
    blob, signature = sign(data)
    _other, _sign, wrong_pub = _fixture()
    result = assess_snapshot(blob, signature, wrong_pub, "kindred-research-test")
    assert result["rank_status"] == "UNTRUSTED"


@pytest.mark.parametrize("change", [
    {"source_url": "http://arcprize.org/leaderboard"},
    {"source_url": "https://arcprize.org.evil.example/leaderboard"},
    {"total_entries": 1},
    {"metric": "custom_metric"},
    {"dataset_sha256": "not-a-hash"},
    {"board_type": "MYSTERY"},
])
def test_invalid_signed_board_never_ranks(change):
    data, sign, pub = _fixture()
    data.update(change)
    blob, signature = sign(data)
    result = assess_snapshot(blob, signature, pub, "kindred-research-test")
    assert result["signature_valid"] is True
    assert result["rank_status"] == "INVALID_DATA"
    assert result["global_number_one_claim_supported"] is False


def test_mixed_conditions_are_rejected():
    data, sign, pub = _fixture()
    data["rows"][1]["conditions_sha256"] = "b" * 64
    blob, signature = sign(data)
    assert assess_snapshot(blob, signature, pub, "kindred-research-test")["rank_status"] == "INVALID_DATA"


def test_missing_target_is_not_assumed_to_have_lost():
    data, sign, pub = _fixture()
    blob, signature = sign(data)
    result = assess_snapshot(blob, signature, pub, "not-an-entry")
    assert result["rank_status"] == "TARGET_NOT_PRESENT"


def test_nonnumeric_or_nonfinite_scores_are_invalid():
    for score in [True, float("inf"), -1, 101, "100"]:
        data, sign, pub = _fixture()
        data["rows"][0]["score"] = score
        blob, signature = sign(data)
        result = assess_snapshot(blob, signature, pub, "kindred-research-test")
        assert result["rank_status"] == "INVALID_DATA"


def test_arc3_registered_but_no_official_score_without_evaluator(monkeypatch):
    from brainstem.benchmarks.registry import BenchmarkRegistry
    from brainstem.benchmarks.adapters import adapter_for

    monkeypatch.delenv("KINDRED_BENCHMARK_ARC_AGI_3_CMD", raising=False)
    spec = BenchmarkRegistry().get("arc-agi-3")
    assert "interactive" in spec.domain
    assert adapter_for(spec).doctor()["status"] == "NOT_CONFIGURED"
