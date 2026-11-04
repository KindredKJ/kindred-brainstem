"""Offline, authenticated comparison of ARC-AGI-3 leaderboard snapshots.

A valid Ed25519 signature proves that the holder of the SUPPLIED key signed
exactly these bytes. It does not establish that the key belongs to ARC Prize,
that the snapshot is exhaustive, or that Kindred is the world's #1 AI lab.
The issuer and source require independent, out-of-band verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_PUBLIC_KEY_BYTES = 16384
MAX_SIGNATURE_BYTES = 16384
HASH_LENGTH = 64
ALLOWED_BOARDS = {"PUBLIC_PROVISIONAL", "FINAL_OFFICIAL"}
ALLOWED_HOSTS = {"arcprize.org", "www.arcprize.org", "kaggle.com", "www.kaggle.com"}


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _read(path: Path, max_bytes: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"file too large: {path.name}")
    return data


def _digest(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == HASH_LENGTH
        and all(ch in "0123456789abcdefABCDEF" for ch in value)
    )


def _string(value) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 300


def _parse_timestamp(value: str) -> None:
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise ValueError("evaluated_at must be an ISO-8601 timestamp") from None
    if date.tzinfo is None:
        raise ValueError("evaluated_at must contain a timezone")


def _validate(snapshot: object) -> dict:
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be a JSON object")
    if type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    if snapshot.get("benchmark") != "arc-agi-3":
        raise ValueError("this auditor only accepts arc-agi-3")
    if snapshot.get("board_type") not in ALLOWED_BOARDS:
        raise ValueError("board_type must be PUBLIC_PROVISIONAL or FINAL_OFFICIAL")
    if snapshot.get("metric") != "score_percent":
        raise ValueError("metric must be score_percent")
    if snapshot.get("score_direction") != "higher":
        raise ValueError("score_direction must be higher")
    for key in ("benchmark_version", "issuer_name", "evaluated_at"):
        if not _string(snapshot.get(key)):
            raise ValueError(f"missing or invalid {key}")
    _parse_timestamp(snapshot["evaluated_at"])
    for key in ("dataset_sha256", "evaluator_sha256", "protocol_sha256", "conditions_sha256"):
        if not _digest(snapshot.get(key)):
            raise ValueError(f"invalid {key}")
    source = snapshot.get("source_url")
    if not isinstance(source, str):
        raise ValueError("source_url must be https")
    parsed = urlsplit(source)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("source_url must identify the known ARC/Kaggle domain via HTTPS")
    rows = snapshot.get("rows")
    if not isinstance(rows, list) or len(rows) < 2 or len(rows) > 100000:
        raise ValueError("at least two and at most 100000 leaderboard rows required")
    if type(snapshot.get("total_entries")) is not int or snapshot["total_entries"] != len(rows):
        raise ValueError("total_entries must match exported row count (completeness is still unverified)")
    ids = set()
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"row {idx} must be object")
        for key in ("system_id", "system_name", "configuration", "provider_model"):
            if not _string(row.get(key)):
                raise ValueError(f"row {idx} has missing/invalid {key}")
        if row["system_id"] in ids:
            raise ValueError("duplicate system_id")
        ids.add(row["system_id"])
        score = row.get("score")
        if (type(score) not in (int, float) or not math.isfinite(score)
                or not (0 <= score <= 100)):
            raise ValueError(f"invalid score on row {idx}")
        if row.get("conditions_sha256") != snapshot["conditions_sha256"]:
            raise ValueError("all entries must use identical evaluation conditions")
    return snapshot


def assess_snapshot(snapshot_bytes: bytes, signature: bytes, public_key_pem: bytes,
                    system_id: str) -> dict:
    """Return machine-readable, conservative attribution and provisional rank.

    The report NEVER makes an independent-authority or global AGI claim.
    """
    if not _string(system_id):
        raise ValueError("system_id required")
    report = {
        "benchmark": "arc-agi-3",
        "target_system_id": system_id,
        "snapshot_sha256": _sha256(snapshot_bytes),
        "signer_public_key_sha256": _sha256(public_key_pem),
        "signature_valid": False,
        "authority_independently_verified": False,
        "external_score_independently_reproduced": False,
        "global_number_one_claim_supported": False,
        "rank_status": "UNTRUSTED",
        "reasons": [],
    }
    try:
        key = load_pem_public_key(public_key_pem)
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("public key must be Ed25519")
        key.verify(signature, snapshot_bytes)
    except (InvalidSignature, ValueError, TypeError) as exc:
        report["reasons"].append(f"signature verification failed ({type(exc).__name__})")
        return report
    report["signature_valid"] = True
    try:
        snapshot = _validate(json.loads(snapshot_bytes))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        report["rank_status"] = "INVALID_DATA"
        report["reasons"].append(str(exc))
        return report
    rows = snapshot["rows"]
    target = next((r for r in rows if r["system_id"] == system_id), None)
    if target is None:
        report["rank_status"] = "TARGET_NOT_PRESENT"
        report["reasons"].append("target does not occur in the signed snapshot")
        return report
    score = target["score"]
    rank = 1 + sum(row["score"] > score for row in rows)
    ties = sum(row["score"] == score for row in rows)
    report.update({
        "rank_status": "LEADER_IN_SIGNED_SNAPSHOT" if rank == 1 and ties == 1
            else "TIED_FIRST_IN_SIGNED_SNAPSHOT" if rank == 1
            else "NOT_FIRST_IN_SIGNED_SNAPSHOT",
        "rank": rank,
        "ties_at_score": ties,
        "score_percent": score,
        "total_exported_entries": len(rows),
        "board_type": snapshot["board_type"],
        "source_url_declared": snapshot["source_url"],
        "system_name": target["system_name"],
        "model_attribution": target["provider_model"],
        "evaluated_at": snapshot["evaluated_at"],
        "conditions_sha256": snapshot["conditions_sha256"],
    })
    report["reasons"].extend([
        "A valid signature authenticates the supplied public key, not the real-world issuer.",
        "The snapshot's source URL, publication, completeness, scores and evaluation conditions have not been independently verified.",
        "Even an official ARC-AGI-3 first place is not proof of globally best AGI or best AI lab.",
    ])
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit a signed ARC-AGI-3 snapshot (not a global #1 certification)")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--signature", required=True, type=Path, help="Detached raw Ed25519 signature")
    parser.add_argument("--public-key", required=True, type=Path, help="PEM key authenticated independently")
    parser.add_argument("--system-id", required=True)
    parser.add_argument("--output", type=Path, help="Write JSON report, without claiming independent verification")
    args = parser.parse_args(argv)
    try:
        report = assess_snapshot(
            _read(args.snapshot, MAX_SNAPSHOT_BYTES),
            _read(args.signature, MAX_SIGNATURE_BYTES),
            _read(args.public_key, MAX_PUBLIC_KEY_BYTES),
            args.system_id,
        )
        encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 0 if report["rank_status"] in {
            "LEADER_IN_SIGNED_SNAPSHOT", "TIED_FIRST_IN_SIGNED_SNAPSHOT",
            "NOT_FIRST_IN_SIGNED_SNAPSHOT",
        } else 2
    except (ValueError, OSError) as exc:
        print(json.dumps({"rank_status": "INVALID_INPUT", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
