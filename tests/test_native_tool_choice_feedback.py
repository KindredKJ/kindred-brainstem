"""Native DCML selects live tools and adapts to observed execution outcomes.

Unit-test receipts are synthetic and never represented as live GitHub results.
"""
from __future__ import annotations

import json
import pytest

from brainstem.runtime.app import build_app, SessionRequest
from brainstem.runtime.service import RuntimeService
from brainstem.runtime.store import StateStore


CANDIDATES = [
    {"name": "github.repository.get", "risk": "read",
     "description": "Read metadata for a repository explicitly granted by the founder"},
    {"name": "github.pull_requests.list", "risk": "read",
     "description": "List pull requests for a founder granted GitHub repository"},
    {"name": "github.issues.list", "risk": "read",
     "description": "List repository issues excluding pull requests for the granted GitHub repository"},
    {"name": "github.actions.runs.list", "risk": "read",
     "description": "List recent GitHub Actions workflow runs for a founder granted repository"},
]
TEST_HASH = "a" * 64


@pytest.fixture()
def service(tmp_path):
    return RuntimeService(StateStore(tmp_path / "dcml-real-native.sqlite3"), adapters={})


def test_actual_existing_dcml_counterfactual_selects_tool_dynamically(service):
    session = service.create_native_session("continuum:research")
    cases = [
        ("Inspect repository metadata and the default branch", "github.repository.get"),
        ("Review pull requests and merged code changes", "github.pull_requests.list"),
        ("Investigate product issues and defects", "github.issues.list"),
        ("Inspect GitHub Actions workflow runs", "github.actions.runs.list"),
    ]
    decisions = []
    for objective, expected in cases:
        result = service.select_native_tool(
            session["id"], objective, list(reversed(CANDIDATES)),
            {"mission_id": "mission-unit-testing", "wing": "research"},
        )
        decisions.append(result)
        assert result["selected_tool"] == expected
        assert result["decision_id"].startswith("KDECIDE-")
        assert result["model_identity"] == "KINDRED-BRAINSTEM"
        assert result["decision_policy"] == "dcml_counterfactual_utility_with_observed_feedback"
        assert result["external_model_used"] is False
        assert result["language_generation_performed"] is False
        assert result["external_action_executed"] is False
        assert result["outcome_verified"] is False
    assert len({result["selected_tool"] for result in decisions}) == 4
    assert len(service.store.query("SELECT id FROM counterfactual_decisions")) == 4
    assert len(service.store.query("SELECT id FROM evidence WHERE kind='dcml_native_tool_choice'")) == 4
    assert service.store.query("SELECT id FROM telemetry") == []


def test_read_only_candidates_are_strictly_enforced(service):
    session = service.create_native_session()
    alternatives = list(CANDIDATES[:2])
    alternatives[1] = {**alternatives[1], "risk": "irreversible"}
    with pytest.raises(ValueError, match="read capabilities"):
        service.select_native_tool(session["id"], "Review code", alternatives)
    with pytest.raises(ValueError, match="unique"):
        service.select_native_tool(session["id"], "Review code", [CANDIDATES[0], CANDIDATES[0]])
    assert service.store.query("SELECT id FROM counterfactual_decisions") == []


def test_observed_failure_changes_next_native_tool_choice(service):
    session = service.create_native_session("continuum:platform")
    options = [CANDIDATES[1], CANDIDATES[2]]
    objective = "Monitor Github information"
    first = service.select_native_tool(session["id"], objective, options)
    assert first["selected_tool"] == "github.issues.list"
    outcome = service.observe_native_tool_outcome(
        session["id"], first["decision_id"], first["selected_tool"],
        False, TEST_HASH, "b" * 64, "c" * 64,
    )
    assert outcome["observed_success"] is False
    assert outcome["adaptive_policy_updated"] is True
    assert outcome["model_weights_trained"] is False
    same = service.observe_native_tool_outcome(
        session["id"], first["decision_id"], first["selected_tool"],
        False, TEST_HASH, "b" * 64, "c" * 64,
    )
    assert same["already_recorded"] is True
    with pytest.raises(ValueError, match="conflicting"):
        service.observe_native_tool_outcome(
            session["id"], first["decision_id"], first["selected_tool"],
            True, TEST_HASH, "b" * 64, "c" * 64,
        )
    second = service.select_native_tool(session["id"], objective, options)
    assert second["selected_tool"] == "github.pull_requests.list"
    assert service.store.query("SELECT id FROM counterfactual_observations")


def test_tool_observation_must_belong_to_same_native_session(service):
    a = service.create_native_session("continuum:research")
    b = service.create_native_session("continuum:products")
    decision = service.select_native_tool(a["id"], "Review pull requests", CANDIDATES)
    with pytest.raises(ValueError, match="not owned"):
        service.observe_native_tool_outcome(
            b["id"], decision["decision_id"], decision["selected_tool"],
            True, TEST_HASH, "b" * 64, "c" * 64,
        )
    with pytest.raises(ValueError, match="differs"):
        service.observe_native_tool_outcome(
            a["id"], decision["decision_id"], "github.issues.list",
            True, TEST_HASH, "b" * 64, "c" * 64,
        )


def test_native_decision_and_feedback_survive_restart(service):
    session = service.create_native_session("continuum:fleet")
    decision = service.select_native_tool(
        session["id"], "List pull requests", CANDIDATES,
    )
    reopened = RuntimeService(StateStore(service.store.path), adapters={})
    outcome = reopened.observe_native_tool_outcome(
        session["id"], decision["decision_id"], decision["selected_tool"],
        True, TEST_HASH, "b" * 64, "c" * 64,
    )
    assert outcome["outcome_status"] == "observed_provider_execution"
    assert outcome["independent_customer_outcome_verified"] is False
    choices = reopened.store.query(
        "SELECT status,payload FROM counterfactual_decisions WHERE id=?",
        (decision["decision_id"],),
    )
    assert choices[0]["status"] == "VERIFIED"
    assert json.loads(choices[0]["payload"])["actual_outcome"] == 1.0


def test_tool_decisions_do_not_work_with_external_adapter_sessions(service):
    other = service.store.create_session("configured")
    with pytest.raises(ValueError, match="native"):
        service.select_native_tool(other["id"], "Review PRs", CANDIDATES)
    with pytest.raises(ValueError, match="native"):
        service.observe_native_tool_outcome(
            other["id"], "KDECIDE-not-real", "github.repository.get",
            True, TEST_HASH, "b"*64, "c"*64,
        )
