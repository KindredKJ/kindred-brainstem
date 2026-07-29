import json

from typer.testing import CliRunner

from brainstem.cli.app import app


runner = CliRunner()


def test_canonical_entry_opens_brainstem(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "KINDRED BRAINSTEM  v1.0.0" in result.output
    assert "kindred://brainstem >" in result.output


def test_codex_here_creates_audited_governed_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["codex", "--here", "--mission", "validate runtime"])
    assert result.exit_code == 0
    assert "BRAINSTEM successfully attached to CODEX" in result.output
    session = json.loads((tmp_path / ".kindred/session.json").read_text())
    assert session["promotion"] == "EVIDENCE-GATED"
    assert session["production_modification"] == "BLOCKED"
    assert session["mission"] == "validate runtime"
    assert (tmp_path / ".kindred/events.jsonl").exists()


def test_awaken_and_learning_status_are_truthful(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    awakened = runner.invoke(app, ["awaken"])
    assert awakened.exit_code == 0
    assert "Deep-Cognitive Learning" in awakened.output
    learning = runner.invoke(app, ["learn", "status"])
    assert learning.exit_code == 0
    assert "GOVERNED_REALTIME" in learning.output
    assert "Production changes              0" in learning.output
