"""Read-only reconciliation of a real Kindred agent's paid commercial pilot.

This verifies repository state, deployment release metadata, a live Stripe
payment intent, and the integrity of a locally retained agent trace. It does
not certify AGI, customer use, agent autonomy, or settlement to a bank.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 262144
MAX_TRACE_BYTES = 50 * 1024 * 1024
SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}\Z")
DIGEST_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
HOST_PATTERN = re.compile(r"[a-z0-9][a-z0-9.-]*[a-z0-9]\Z")
PAYMENT_PATTERN = re.compile(r"pi_[A-Za-z0-9]+\Z")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch_json(url: str, bearer: str | None = None):
    headers = {"Accept": "application/json", "User-Agent": "Kindred-Pilot-Audit/1"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    opener = build_opener(_NoRedirect)
    with opener.open(Request(url, headers=headers), timeout=12) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("remote JSON response exceeds size limit")
        return json.loads(raw)


def _require_manifest(bundle: dict) -> None:
    if not isinstance(bundle, dict) or type(bundle.get("schema_version")) is not int or bundle["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    for key in ("run_id", "repo", "commit", "deployment_host", "stripe_payment_intent", "agent_trace_file", "agent_trace_sha256"):
        if not isinstance(bundle.get(key), str) or not bundle[key].strip():
            raise ValueError(f"missing or invalid field: {key}")
    if len(bundle["run_id"]) > 128 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{5,127}", bundle["run_id"]):
        raise ValueError("invalid run_id")
    if not REPO_PATTERN.fullmatch(bundle["repo"]) or ".." in bundle["repo"]:
        raise ValueError("invalid GitHub owner/repository")
    if not SHA_PATTERN.fullmatch(bundle["commit"]):
        raise ValueError("commit must be a complete SHA-1 Git commit ID")
    if not DIGEST_PATTERN.fullmatch(bundle["agent_trace_sha256"]):
        raise ValueError("invalid agent trace digest")
    if not PAYMENT_PATTERN.fullmatch(bundle["stripe_payment_intent"]):
        raise ValueError("invalid Stripe payment intent ID")
    host = bundle["deployment_host"].lower()
    if not HOST_PATTERN.fullmatch(host) or ".." in host or host in {"localhost", "localdomain"}:
        raise ValueError("invalid deployment DNS hostname")


def _trace_check(manifest_path: Path, bundle: dict) -> bool:
    root = manifest_path.resolve().parent
    path = Path(bundle["agent_trace_file"])
    if path.is_absolute():
        return False
    try:
        target = (root / path).resolve(strict=True)
        target.relative_to(root)
        if not target.is_file() or target.stat().st_size > MAX_TRACE_BYTES:
            return False
        with target.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        return digest.lower() == bundle["agent_trace_sha256"].lower()
    except (OSError, ValueError):
        return False


def verify_bundle(manifest_path: Path, fetcher=_fetch_json, environ=None) -> dict:
    """Audit user-provided references against live provider APIs.

    fetcher is injectable for unit tests. Production calls default to HTTPS
    requests with redirects rejected. No provider changes are performed.
    """
    env = os.environ if environ is None else environ
    bundle = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require_manifest(bundle)
    result = {
        "run_id": bundle["run_id"],
        "status": "INCOMPLETE",
        "checks": {},
        "blockers": [],
        "independent_agent_autonomy_verified": False,
        "agi_verified": False,
        "funds_settled_verified": False,
        "note": "API reconciliation alone does not prove independently autonomous operation, AGI, or bank settlement.",
    }

    def record(name: str, passed: bool, reason: str) -> None:
        result["checks"][name] = bool(passed)
        if not passed:
            result["blockers"].append(f"{name}: {reason}")

    record("agent_trace_sha256", _trace_check(manifest_path, bundle),
           "trace missing, outside bundle, oversized, or digest mismatch (local integrity only)")

    owner, name = bundle["repo"].split("/")
    github_url = f"https://api.github.com/repos/{quote(owner)}/{quote(name)}/commits/{bundle['commit']}"
    try:
        commit = fetcher(github_url, env.get("GITHUB_TOKEN"))
        record("github_commit_api", isinstance(commit, dict) and str(commit.get("sha", "")).lower() == bundle["commit"].lower(),
               "commit was not confirmed by GitHub's API")
    except (HTTPError, URLError, TimeoutError, ValueError, OSError, KeyError) as exc:
        record("github_commit_api", False, f"GitHub API check failed ({type(exc).__name__})")

    host = bundle["deployment_host"].lower()
    allowed = {item.strip().lower() for item in env.get("KINDRED_PILOT_ALLOWED_HOSTS", "").split(",") if item.strip()}
    if host not in allowed:
        record("deployment_release_metadata", False, "host not explicitly allowlisted in KINDRED_PILOT_ALLOWED_HOSTS")
    else:
        try:
            # This endpoint is operator-controlled metadata, NOT cryptographic
            # proof that the release actually executes the declared commit.
            release = fetcher(f"https://{host}/.well-known/kindred-release.json", None)
            record("deployment_release_metadata",
                   isinstance(release, dict)
                   and str(release.get("commit", "")).lower() == bundle["commit"].lower()
                   and release.get("run_id") == bundle["run_id"],
                   "deployment did not return matching commit and run_id metadata")
        except (HTTPError, URLError, TimeoutError, ValueError, OSError, KeyError) as exc:
            record("deployment_release_metadata", False, f"release endpoint check failed ({type(exc).__name__})")

    stripe_key = env.get("STRIPE_SECRET_KEY", "")
    if not stripe_key.startswith(("sk_live_", "rk_live_")):
        record("stripe_live_paid_intent_api", False, "live restricted or secret Stripe API key not configured")
    else:
        intent_url = f"https://api.stripe.com/v1/payment_intents/{quote(bundle['stripe_payment_intent'])}"
        try:
            payment = fetcher(intent_url, stripe_key)
            valid = (isinstance(payment, dict)
                     and payment.get("id") == bundle["stripe_payment_intent"]
                     and payment.get("livemode") is True
                     and payment.get("status") == "succeeded"
                     and payment.get("currency") == "usd"
                     and type(payment.get("amount_received")) is int
                     and payment["amount_received"] > 0
                     and isinstance(payment.get("metadata"), dict)
                     and payment["metadata"].get("kindred_run_id") == bundle["run_id"])
            record("stripe_live_paid_intent_api", valid,
                   "live succeeded USD payment intent bound to this run was not confirmed")
            if valid:
                result["confirmed_gross_usd_cents"] = payment["amount_received"]
        except (HTTPError, URLError, TimeoutError, ValueError, OSError, KeyError) as exc:
            record("stripe_live_paid_intent_api", False, f"Stripe API check failed ({type(exc).__name__})")

    if all(result["checks"].values()) and len(result["checks"]) == 4:
        result["status"] = "LIVE_PAYMENT_AND_RELEASE_METADATA_RECONCILED"
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only commercial pilot evidence reconciliation")
    parser.add_argument("manifest", type=Path, help="Local JSON manifest; never commit private receipts")
    args = parser.parse_args(argv)
    try:
        result = verify_bundle(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "INVALID_MANIFEST", "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "LIVE_PAYMENT_AND_RELEASE_METADATA_RECONCILED" else 2


if __name__ == "__main__":
    sys.exit(main())
