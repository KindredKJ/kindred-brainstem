import json

from brainstem.adapters.models.base import Generation, ModelAdapter, ModelHealth
from brainstem.adapters.models.codex import CodexAdapter
from brainstem.runtime.app import ChatRequest, SessionRequest, build_app
from brainstem.runtime.service import RuntimeService
from brainstem.runtime.store import StateStore


def endpoint(app, path):
    return next(
        route.endpoint for route in app.routes if getattr(route, "path", None) == path
    )


class SimulatedAdapter(ModelAdapter):
    identity = "SIMULATED"

    def capabilities(self):
        return {"generate", "stream"}

    def health(self):
        return ModelHealth("HEALTHY", "test provider probe passed")

    def generate(self, messages):
        return Generation(
            f"SIMULATED response to: {messages[-1]['content']}",
            "SIMULATED",
            {"total_tokens": 4},
        )


class UnavailableSimulatedAdapter(SimulatedAdapter):
    identity = "failed"

    def health(self):
        return ModelHealth("UNAVAILABLE", "probe failed")

    def generate(self, messages):
        raise AssertionError("unhealthy adapter must not run")


def service(tmp_path):
    store = StateStore(tmp_path / "brainstem.db", tmp_path / "events.jsonl")
    return RuntimeService(
        store,
        {
            "h-carat": UnavailableSimulatedAdapter(),
            "working": SimulatedAdapter(),
            "failed": UnavailableSimulatedAdapter(),
        },
    )


def test_runtime_api_chat_evidence_and_candidate_learning(tmp_path):
    runtime = service(tmp_path)
    app = build_app(service=runtime)
    assert endpoint(app, "/health")()["database"] == "HEALTHY"
    session = endpoint(app, "/sessions")(SessionRequest(model="working"))
    body = endpoint(app, "/chat")(
        ChatRequest(session_id=session["id"], message="hello")
    )
    assert body["response"] == "SIMULATED response to: hello"
    assert body["learning_status"] == "PROPOSED"
    assert len(endpoint(app, "/evidence")()) == 1
    assert endpoint(app, "/learning")()[0]["status"] == "PROPOSED"


def test_session_and_context_survive_store_reopen_and_model_switch(tmp_path):
    runtime = service(tmp_path)
    session = runtime.create_session("working")
    runtime.chat(session["id"], "remember this")
    runtime.switch(session["id"], "failed")
    reopened = StateStore(tmp_path / "brainstem.db", tmp_path / "events.jsonl")
    assert reopened.session(session["id"])["model"] == "failed"
    assert reopened.history(session["id"])[0]["content"] == "remember this"


def test_failed_model_has_no_silent_fallback_and_is_audited(tmp_path):
    runtime = service(tmp_path)
    session = runtime.store.create_session("failed")
    try:
        runtime.chat(session["id"], "do not fallback")
    except RuntimeError as exc:
        assert "no fallback attempted" in str(exc)
    else:
        raise AssertionError("failed adapter should fail")
    events = (tmp_path / "events.jsonl").read_text().splitlines()
    assert any(json.loads(line)["kind"] == "model.failed" for line in events)
    assert runtime.store.history(session["id"])[0]["role"] == "user"


def test_h_carat_and_codex_truthfully_unavailable(tmp_path):
    runtime = service(tmp_path)
    assert runtime.models()[0]["status"] == "UNAVAILABLE"
    health = CodexAdapter(executable="definitely-not-installed-codex").health()
    assert health.status == "NOT_CONFIGURED"


def test_authority_and_unimplemented_surfaces_are_truthful(tmp_path):
    app = build_app(service=service(tmp_path))
    identity = endpoint(app, "/identity")()
    assert identity["founder"] == "Kindred Jermaine Cox"
    assert identity["license"] == "LicenseRef-Kindred-Proprietary"
    assert endpoint(app, "/world")()["schema_version"] == 1
    assert endpoint(app, "/missions")()["status"] == "NOT_IMPLEMENTED"


def test_backup_and_restore_preserve_canonical_session(tmp_path):
    runtime = service(tmp_path)
    session = runtime.create_session("working")
    runtime.chat(session["id"], "persist through backup")
    backup = runtime.store.backup(tmp_path / "backup.db")
    restored = StateStore.restore(
        backup, tmp_path / "restored.db", tmp_path / "restored.jsonl"
    )
    assert restored.session(session["id"])["id"] == session["id"]
    assert restored.history(session["id"])[0]["content"] == "persist through backup"
    assert (
        restored.query("SELECT COUNT(*) AS count FROM learning_proposals")[0]["count"]
        == 1
    )


def test_dcml_runtime_endpoints_delegate_to_native_model(tmp_path):
    app = build_app(service=service(tmp_path))
    status = endpoint(app, "/dcml/status")()
    assert status["foundation_model_weights"] == "NOT_TRAINED"
    assert status["migration_version"] == 2
    assert endpoint(app, "/dcml/experiences")() == []
    assert endpoint(app, "/dcml/datasets")() == []
