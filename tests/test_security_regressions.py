import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from brainstem.adapters.models.base import Generation, ModelAdapter, ModelHealth
from brainstem.model.authority import FounderAuthority
from brainstem.model.core import BrainstemModel
from brainstem.model.schemas import StrategyCandidate
from brainstem.runtime.service import RuntimeService
from brainstem.runtime.store import IdempotencyConflict, StateStore

DIGEST = hashlib.sha256(b"immutable-payload").hexdigest()


class CountingAdapter(ModelAdapter):
    identity = "SIMULATED_COUNTING"

    def __init__(self) -> None:
        self.calls = 0
        self.lock = threading.Lock()

    def capabilities(self):
        return {"generate"}

    def health(self):
        return ModelHealth("HEALTHY", "test adapter")

    def generate(self, messages):
        with self.lock:
            self.calls += 1
        time.sleep(0.05)
        return Generation("one response", self.identity, {"total_tokens": 1})


def authority(tmp_path):
    store = StateStore(tmp_path / "state.db", tmp_path / "events.jsonl")
    return store, FounderAuthority(store, tmp_path / "authority")


def signed(auth, **overrides):
    values = {
        "action": "execute:exact-action",
        "scope": "production-control",
        "payload_digest": DIGEST,
        "environment": "production",
        "tenant": "tenant-a",
    }
    values.update(overrides)
    return auth.sign(**values)


def learning_model(tmp_path):
    store = StateStore(tmp_path / "learning.db", tmp_path / "learning.jsonl")
    model = BrainstemModel(store)
    model.dcml.authority = FounderAuthority(store, tmp_path / "authority")
    learning_id = model.learn(
        "strategy",
        {
            "strategy": StrategyCandidate(
                id="KSTR-SECURE",
                name="secure-strategy",
                description="cryptographically approved",
                expected_utility=0.9,
                risk=0.1,
                confidence=0.9,
                source="security-test",
            ).model_dump()
        },
        ["security-test"],
    )
    model.evaluate_learning(learning_id, 0.9, ["security-evidence"])
    return model, learning_id


def learning_decision(model, learning_id, decision="APPROVED", **overrides):
    row = model.learning(learning_id)[0]
    values = {
        "action": (
            f"learning:approve:{learning_id}"
            if decision == "APPROVED"
            else f"learning:reject:{learning_id}"
        ),
        "scope": "learning-governance",
        "payload_digest": model._learning_digest(row),
        "decision": decision,
        "environment": model.environment,
        "tenant": model.tenant,
    }
    values.update(overrides)
    return model.dcml.authority.sign(**values)


def test_rejected_decision_and_forged_founder_identity_never_approve_learning(
    tmp_path,
):
    model, learning_id = learning_model(tmp_path)
    rejected = learning_decision(model, learning_id, decision="REJECTED")
    with pytest.raises(PermissionError, match="invalid"):
        model.approve_learning(learning_id, rejected)
    with pytest.raises(PermissionError, match="invalid"):
        model.approve_learning(learning_id, "Kindred Jermaine Cox")
    assert model.learning(learning_id)[0]["status"] == "EVALUATED"


def test_modified_payload_and_malformed_record_fail_closed(tmp_path):
    store, auth = authority(tmp_path)
    approval = signed(auth)
    record = store.query(
        "SELECT payload FROM signed_approvals WHERE id=?", (approval,)
    )[0]
    modified = json.loads(record["payload"])
    modified["payload"]["payload_digest"] = "0" * 64
    store.execute(
        "UPDATE signed_approvals SET payload=? WHERE id=?",
        (json.dumps(modified), approval),
    )
    assert not auth.verify(
        approval,
        "execute:exact-action",
        DIGEST,
        expected_environment="production",
        expected_tenant="tenant-a",
        expected_scope="production-control",
    )
    store.execute(
        "UPDATE signed_approvals SET payload='not-json' WHERE id=?", (approval,)
    )
    assert not auth.verify(
        approval,
        "execute:exact-action",
        DIGEST,
        expected_environment="production",
        expected_tenant="tenant-a",
    )


@pytest.mark.parametrize(
    ("environment", "tenant"),
    [("staging", "tenant-a"), ("production", "tenant-b")],
)
def test_wrong_environment_or_tenant_is_rejected(tmp_path, environment, tenant):
    _, auth = authority(tmp_path)
    approval = signed(auth)
    assert not auth.verify(
        approval,
        "execute:exact-action",
        DIGEST,
        expected_environment=environment,
        expected_tenant=tenant,
        expected_scope="production-control",
    )


def test_expired_revoked_and_superseded_decisions_fail_closed(tmp_path):
    _, auth = authority(tmp_path)
    expiry = (datetime.now(UTC) + timedelta(milliseconds=30)).isoformat()
    expired = signed(auth, expires_at=expiry)
    time.sleep(0.05)
    assert not auth.verify(
        expired,
        "execute:exact-action",
        DIGEST,
        expected_environment="production",
        expected_tenant="tenant-a",
    )
    revoked = signed(auth)
    auth.revoke(revoked)
    assert not auth.verify(
        revoked,
        "execute:exact-action",
        DIGEST,
        expected_environment="production",
        expected_tenant="tenant-a",
    )
    superseded = signed(auth)
    auth.supersede(superseded)
    assert not auth.verify(
        superseded,
        "execute:exact-action",
        DIGEST,
        expected_environment="production",
        expected_tenant="tenant-a",
    )


def test_nonce_is_consumed_once_and_replay_is_rejected(tmp_path):
    _, auth = authority(tmp_path)
    rejected = signed(auth, decision="REJECTED")
    assert not auth.authorize(
        rejected,
        "execute:exact-action",
        DIGEST,
        expected_environment="production",
        expected_tenant="tenant-a",
        expected_scope="production-control",
    )
    approval = signed(auth)
    expected = {
        "expected_environment": "production",
        "expected_tenant": "tenant-a",
        "expected_scope": "production-control",
    }
    assert auth.authorize(approval, "execute:exact-action", DIGEST, **expected)
    assert not auth.authorize(approval, "execute:exact-action", DIGEST, **expected)


def test_revoked_linked_approval_cannot_promote_learning(tmp_path):
    model, learning_id = learning_model(tmp_path)
    approval = learning_decision(model, learning_id)
    model.approve_learning(learning_id, approval)
    row = model.learning(learning_id)[0]
    promotion = model.dcml.authority.sign(
        f"learning:promote:{learning_id}",
        "learning-execution",
        model._learning_digest(row),
        environment=model.environment,
        tenant=model.tenant,
    )
    model.dcml.authority.revoke(promotion)
    with pytest.raises(PermissionError, match="Live cryptographic"):
        model.promote_learning(learning_id, promotion)
    assert model.learning(learning_id)[0]["status"] == "APPROVED"


def test_duplicate_and_concurrent_chat_delivery_process_once(tmp_path):
    adapter = CountingAdapter()
    store = StateStore(tmp_path / "chat.db", tmp_path / "chat.jsonl")
    runtime = RuntimeService(store, {"working": adapter})
    session = runtime.create_session("working")
    key = "same-chat-delivery-0001"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(runtime.chat, session["id"], "hello once", key)
            for _ in range(2)
        ]
    first, second = [future.result() for future in futures]
    assert first == second
    assert adapter.calls == 1
    assert len(store.history(session["id"])) == 2
    assert runtime.chat(session["id"], "hello once", key) == first
    assert adapter.calls == 1
    with pytest.raises(IdempotencyConflict):
        runtime.chat(session["id"], "changed content", key)


def test_duplicate_and_concurrent_learning_decision_is_idempotent(tmp_path):
    model, learning_id = learning_model(tmp_path)
    approval = learning_decision(model, learning_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(model.approve_learning, learning_id, approval) for _ in range(2)
        ]
    results = [future.result() for future in futures]
    assert {result["status"] for result in results} == {"APPROVED"}
    assert model.approve_learning(learning_id, approval)["status"] == "APPROVED"
    assert model.store.query("SELECT COUNT(*) AS count FROM approvals")[0]["count"] == 1
