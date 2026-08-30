from typer.testing import CliRunner

from brainstem.cli.app import app

runner = CliRunner()


def test_canonical_entry_reports_truthful_offline_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KINDRED_RUNTIME_URL", "http://127.0.0.1:1")
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "KINDRED BRAINSTEM 0.1.0-alpha" in result.output
    assert "Runtime: OFFLINE" in result.output
    assert "H^: UNAVAILABLE" in result.output


def test_codex_attach_fails_truthfully_when_runtime_is_offline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KINDRED_RUNTIME_URL", "http://127.0.0.1:1")
    result = runner.invoke(app, ["codex", "--here"])
    assert result.exit_code == 1
    assert "runtime unavailable" in result.output.lower()


def test_awaken_does_not_claim_unprobed_capabilities(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KINDRED_RUNTIME_URL", "http://127.0.0.1:1")
    result = runner.invoke(app, ["awaken"])
    assert result.exit_code == 0
    assert "State Store: UNAVAILABLE" in result.output
    for unsupported in ("ONLINE", "ACTIVE", "READY", "VERIFIED"):
        assert unsupported not in result.output
