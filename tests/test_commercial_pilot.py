"""Contract tests use mocked provider responses; they are NOT pilot evidence."""
import hashlib
import json

import pytest

from brainstem.benchmarks.commercial_pilot import verify_bundle


SHA = "a" * 40
RUN_ID = "kindred-pilot-0001"
PAYMENT_ID = "pi_123456789"
HOST = "pilot.kindredlabs.ai"


def make_manifest(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"event":"agent_action","task":"deploy"}\n', encoding="utf-8")
    bundle = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "repo": "KindredKJ/kindred-cloud",
        "commit": SHA,
        "deployment_host": HOST,
        "stripe_payment_intent": PAYMENT_ID,
        "agent_trace_file": "trace.jsonl",
        "agent_trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
    }
    p = tmp_path / "pilot.json"
    p.write_text(json.dumps(bundle), encoding="utf-8")
    return p


def fake_provider(url, token):
    if url.startswith("https://api.github.com/"):
        return {"sha": SHA}
    if url.startswith("https://" + HOST):
        return {"commit": SHA, "run_id": RUN_ID}
    if url.startswith("https://api.stripe.com/"):
        assert token == "sk_live_testfixture"
        return {
            "id": PAYMENT_ID,
            "livemode": True,
            "status": "succeeded",
            "currency": "usd",
            "amount_received": 49900,
            "metadata": {"kindred_run_id": RUN_ID},
        }
    raise AssertionError("unexpected provider URL")


def test_all_four_checks_reconcile_but_do_not_prove_agi(tmp_path):
    manifest = make_manifest(tmp_path)
    report = verify_bundle(
        manifest, fetcher=fake_provider,
        environ={"STRIPE_SECRET_KEY": "sk_live_testfixture",
                 "KINDRED_PILOT_ALLOWED_HOSTS": HOST},
    )
    assert report["status"] == "LIVE_PAYMENT_AND_RELEASE_METADATA_RECONCILED"
    assert report["confirmed_gross_usd_cents"] == 49900
    assert all(report["checks"].values())
    assert report["independent_agent_autonomy_verified"] is False
    assert report["agi_verified"] is False
    assert report["funds_settled_verified"] is False


def test_missing_live_credentials_fail_closed(tmp_path):
    report = verify_bundle(make_manifest(tmp_path), fetcher=fake_provider,
                           environ={"KINDRED_PILOT_ALLOWED_HOSTS": HOST})
    assert report["status"] == "INCOMPLETE"
    assert not report["checks"]["stripe_live_paid_intent_api"]


def test_mismatched_stripe_run_id_is_rejected(tmp_path):
    def changed(url, token):
        item = fake_provider(url, token)
        if "stripe.com" in url:
            item["metadata"]["kindred_run_id"] = "unrelated-run"
        return item

    report = verify_bundle(make_manifest(tmp_path), fetcher=changed,
                           environ={"STRIPE_SECRET_KEY": "sk_live_testfixture",
                                    "KINDRED_PILOT_ALLOWED_HOSTS": HOST})
    assert report["status"] == "INCOMPLETE"
    assert not report["checks"]["stripe_live_paid_intent_api"]


def test_deployment_host_allowlist_must_be_explicit(tmp_path):
    report = verify_bundle(make_manifest(tmp_path), fetcher=fake_provider,
                           environ={"STRIPE_SECRET_KEY": "sk_live_testfixture"})
    assert report["status"] == "INCOMPLETE"
    assert report["checks"]["deployment_release_metadata"] is False


def test_invalid_trace_or_path_escape_never_passes(tmp_path):
    manifest = make_manifest(tmp_path)
    data = json.loads(manifest.read_text())
    data["agent_trace_file"] = "../outside.jsonl"
    manifest.write_text(json.dumps(data))
    report = verify_bundle(manifest, fetcher=fake_provider,
                           environ={"STRIPE_SECRET_KEY": "sk_live_testfixture",
                                    "KINDRED_PILOT_ALLOWED_HOSTS": HOST})
    assert report["checks"]["agent_trace_sha256"] is False
    assert report["status"] == "INCOMPLETE"


def test_invalid_schema_refused(tmp_path):
    manifest = make_manifest(tmp_path)
    data = json.loads(manifest.read_text())
    data["commit"] = "main"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="complete SHA"):
        verify_bundle(manifest, fetcher=fake_provider, environ={})
