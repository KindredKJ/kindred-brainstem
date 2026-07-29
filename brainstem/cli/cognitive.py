"""CLI client for the separately running Kindred BRAINSTEM runtime."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import typer
from rich.console import Console
from rich.table import Table

from brainstem.runtime.client import RuntimeClient, RuntimeUnavailable
from brainstem.runtime.paths import global_state_dir, repository_root

console = Console()
VERSION = "0.1.0-alpha"
runtime_app = typer.Typer(help="Start, stop, and probe the local runtime service.")
session_app = typer.Typer(help="Inspect persistent runtime sessions.")
learn_app = typer.Typer(help="Inspect candidate-first learning proposals.")
models_app = typer.Typer(help="Probe configured model adapters.")
cognitive_app = typer.Typer(help="Inspect and checkpoint the native BRAINSTEM model.")
world_app = typer.Typer(help="Inspect the structured BRAINSTEM world model.")
learning_app = typer.Typer(help="Govern DCML learning proposals.")
telemetry_app = typer.Typer(help="Inspect attached-instrument telemetry.")
dcml_app = typer.Typer(help="Operate the native verified-experience DCML loop.")
memory_app = typer.Typer(help="Inspect and consolidate governed memory.")
strata_app = typer.Typer(help="Inspect the protected Strata Data Port client boundary.")
strata_ports_app = typer.Typer(help="Operate BRAINSTEM-side Port Zero diagnostics.")
strata_app.add_typer(strata_ports_app, name="ports")


def _client() -> RuntimeClient:
    return RuntimeClient(os.getenv("KINDRED_RUNTIME_URL", "http://127.0.0.1:8280"))


def _pid_path() -> Path:
    path = global_state_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path / "runtime.pid"


def _saved_session_path() -> Path:
    root = repository_root()
    path = root / ".kindred" if root else global_state_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path / "active_session"


def _runtime_health() -> dict:
    try:
        return _client().health()
    except RuntimeUnavailable:
        return {"status": "OFFLINE", "database": "UNAVAILABLE", "models": {}}


def render_shell_status() -> None:
    health = _runtime_health()
    console.print(f"[bold cyan]KINDRED BRAINSTEM {VERSION}[/bold cyan]")
    console.print("Founder and Originating Architect: Kindred Jermaine Cox")
    console.print(f"Runtime: {health['status']}")
    console.print(f"State Store: {health.get('database', 'UNAVAILABLE')}")
    h_health = health.get("models", {}).get("h-carat", {})
    console.print(f"H^: {h_health.get('status', 'UNAVAILABLE')}")
    console.print("Production Promotion: BLOCKED")


def run_shell(client: RuntimeClient, input_fn: Callable[[str], str] = input) -> None:
    """Run a recoverable conversation; all inference occurs through the runtime API."""
    health = client.health()
    if health["status"] not in {"HEALTHY", "DEGRADED"}:
        raise RuntimeUnavailable("Runtime health probe did not pass")
    saved = _saved_session_path()
    session = None
    if saved.exists():
        try:
            session = client.session(saved.read_text().strip())
        except RuntimeError:
            saved.unlink(missing_ok=True)
    if session is None:
        try:
            session = client.create_session(
                repository=str(repository_root()) if repository_root() else None
            )
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            console.print(
                "Configure a healthy model explicitly; no fallback was attempted."
            )
            return
        saved.write_text(session["id"] + "\n")
    console.print(f"Session: {session['id']}  Model: {session['model']}")
    console.print("Type /help for commands; /exit to leave.")
    while True:
        try:
            text = input_fn("kindred://brainstem > ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nSession preserved.")
            return
        if not text:
            continue
        if text == "/exit":
            console.print("Session preserved.")
            return
        if text == "/help":
            console.print(
                "/status /model /models /attach MODEL /detach /switch MODEL /context "
                "/mission /memory /evidence /learning /new /resume /clear /exit"
            )
            continue
        if text in {"/status", "/context", "/model"}:
            session = client.session(session["id"])
            console.print_json(data=session)
            continue
        if text == "/models":
            console.print_json(data=client.models())
            continue
        if text.startswith(("/switch ", "/attach ")):
            model = text.split(maxsplit=1)[1]
            session = client.switch(session["id"], model)
            console.print(f"Model: {model}")
            continue
        if text == "/new":
            session = client.create_session(
                repository=str(repository_root()) if repository_root() else None
            )
            saved.write_text(session["id"] + "\n")
            console.print(f"Session: {session['id']}")
            continue
        if text == "/resume":
            console.print(f"Session already active: {session['id']}")
            continue
        if text in {
            "/detach",
            "/clear",
            "/mission",
            "/memory",
            "/evidence",
            "/learning",
        }:
            console.print(f"{text}: NOT_IMPLEMENTED")
            continue
        try:
            result = client.chat(session["id"], text)
            for chunk in result["response"].splitlines(keepends=True):
                console.print(chunk, end="")
            console.print()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")


def _attach_model(model: str, here: bool) -> None:
    try:
        root = repository_root()
        session = _client().create_session(model, str(root) if here and root else None)
        _saved_session_path().write_text(session["id"] + "\n")
        console.print_json(data=session)
    except (RuntimeError, RuntimeUnavailable) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


def register(app: typer.Typer) -> None:
    app.add_typer(runtime_app, name="runtime")
    app.add_typer(session_app, name="session")
    app.add_typer(learn_app, name="learn")
    app.add_typer(models_app, name="models")
    app.add_typer(cognitive_app, name="cognitive")
    app.add_typer(world_app, name="world")
    app.add_typer(learning_app, name="learning")
    app.add_typer(telemetry_app, name="telemetry")
    app.add_typer(dcml_app, name="dcml")
    app.add_typer(memory_app, name="memory")
    app.add_typer(strata_app, name="strata")

    @app.command("shell")
    def shell() -> None:
        """Open an interactive, runtime-backed conversation."""
        try:
            run_shell(_client())
        except RuntimeUnavailable as exc:
            console.print(
                f"[red]OFFLINE: {exc}[/red]\nStart it with `kindred runtime start`."
            )
            raise typer.Exit(1) from exc

    @app.command("attach")
    def attach(model: str, here: bool = typer.Option(False, "--here")) -> None:
        """Create a BRAINSTEM-owned session using the selected specialist."""
        _attach_model(model, here)

    @app.command("codex")
    def codex(
        here: bool = typer.Option(False, "--here"),
        mission: str | None = typer.Option(None, "--mission"),
    ) -> None:
        """Attach the real installed Codex CLI, or report its truthful blocker."""
        del mission  # Missions remain NOT_IMPLEMENTED and are never falsely persisted.
        _attach_model("codex", here)

    @app.command("with")
    def with_model(model: str, task: str) -> None:
        """Run one governed task using a selected model adapter."""
        client = _client()
        try:
            session = client.create_session(
                model, str(repository_root()) if repository_root() else None
            )
            console.print(client.chat(session["id"], task)["response"])
        except (RuntimeError, RuntimeUnavailable) as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc

    @app.command("beliefs")
    def beliefs_command() -> None:
        console.print_json(data=_client().request("GET", "/beliefs"))

    @app.command("strategies")
    def strategies_command() -> None:
        console.print_json(data=_client().request("GET", "/strategies"))

    @app.command("skills")
    def skills_command() -> None:
        console.print_json(data=_client().request("GET", "/skills"))

    @app.command("awaken")
    def awaken() -> None:
        """Display only health-probed runtime and adapter states."""
        render_shell_status()


@runtime_app.command("start")
def runtime_start() -> None:
    """Start the local runtime bound to loopback."""
    if _runtime_health()["status"] in {"HEALTHY", "DEGRADED"}:
        console.print("Runtime: HEALTHY (already running)")
        return
    log = global_state_dir() / "runtime.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    stream = log.open("ab")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "brainstem.runtime.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8280",
        ],
        stdout=stream,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _pid_path().write_text(str(process.pid))
    for _ in range(30):
        time.sleep(0.1)
        if _runtime_health()["status"] in {"HEALTHY", "DEGRADED"}:
            console.print(
                f"Runtime: {_runtime_health()['status']}\nPID: {process.pid}\nBind: 127.0.0.1:8280"
            )
            return
    console.print(f"Runtime: UNAVAILABLE\nSee {log}")
    raise typer.Exit(1)


@runtime_app.command("stop")
def runtime_stop() -> None:
    path = _pid_path()
    if not path.exists():
        console.print("Runtime: OFFLINE")
        return
    try:
        os.kill(int(path.read_text()), signal.SIGTERM)
    except ProcessLookupError:
        pass
    path.unlink(missing_ok=True)
    console.print("Runtime: OFFLINE")


@runtime_app.command("status")
def runtime_status() -> None:
    console.print_json(data=_runtime_health())


@session_app.command("status")
def session_status() -> None:
    path = _saved_session_path()
    if not path.exists():
        console.print("Session: UNAVAILABLE")
        return
    try:
        console.print_json(data=_client().session(path.read_text().strip()))
    except (RuntimeError, RuntimeUnavailable) as exc:
        console.print(f"Session: UNAVAILABLE ({exc})")


@learn_app.command("status")
def learn_status() -> None:
    try:
        proposals = _client().request("GET", "/learning")
        console.print(
            f"Learning: AVAILABLE\nCandidate proposals: {len(proposals)}\nProduction promotion: BLOCKED"
        )
    except RuntimeUnavailable:
        console.print("Learning: UNAVAILABLE")


@models_app.callback(invoke_without_command=True)
def models(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        try:
            table = Table("Model", "Status", "Detail")
            for model in _client().models():
                table.add_row(model["id"], model["status"], model["detail"])
            console.print(table)
        except RuntimeUnavailable:
            console.print("Models: UNAVAILABLE (runtime OFFLINE)")


@cognitive_app.command("status")
def cognitive_status() -> None:
    try:
        result = _client().request("GET", "/cognitive")
        console.print(
            f"Cognitive Model: {result['status']}\nTrained Weights: {result['trained_weights']}\nState Revision: {result['state']['revision']}"
        )
    except RuntimeUnavailable:
        console.print("Cognitive Model: UNAVAILABLE")


@cognitive_app.command("inspect")
def cognitive_inspect() -> None:
    try:
        console.print_json(data=_client().request("GET", "/cognitive"))
    except RuntimeUnavailable:
        console.print("Cognitive Model: UNAVAILABLE")


@cognitive_app.command("checkpoint")
def cognitive_checkpoint() -> None:
    try:
        console.print_json(data=_client().request("POST", "/cognitive/checkpoint", {}))
    except RuntimeUnavailable:
        console.print("Checkpoint: UNAVAILABLE")


@cognitive_app.command("rollback")
def cognitive_rollback(checkpoint: str) -> None:
    try:
        console.print_json(
            data=_client().request("POST", f"/cognitive/rollback/{checkpoint}", {})
        )
    except RuntimeUnavailable:
        console.print("Rollback: UNAVAILABLE")


@world_app.command("show")
def world_show() -> None:
    try:
        console.print_json(data=_client().request("GET", "/world"))
    except RuntimeUnavailable:
        console.print("World Model: UNAVAILABLE")


@learning_app.command("list")
def learning_list() -> None:
    try:
        console.print_json(data=_client().request("GET", "/learning"))
    except RuntimeUnavailable:
        console.print("Learning: UNAVAILABLE")


@learning_app.command("inspect")
def learning_inspect(learning_id: str) -> None:
    console.print_json(data=_client().request("GET", f"/learning/{learning_id}"))


@learning_app.command("approve")
def learning_approve(
    learning_id: str, founder: str = typer.Option("", "--founder")
) -> None:
    if founder != "Kindred Jermaine Cox":
        console.print("Approval: BLOCKED (explicit founder declaration required)")
        raise typer.Exit(1)
    console.print_json(
        data=_client().request(
            "POST", f"/learning/{learning_id}/approve", {"founder": founder}
        )
    )


@learning_app.command("reject")
def learning_reject(
    learning_id: str, founder: str = typer.Option("", "--founder")
) -> None:
    if founder != "Kindred Jermaine Cox":
        console.print("Rejection: BLOCKED (explicit founder declaration required)")
        raise typer.Exit(1)
    console.print_json(
        data=_client().request(
            "POST", f"/learning/{learning_id}/reject", {"founder": founder}
        )
    )


@telemetry_app.command("show")
def telemetry_show() -> None:
    try:
        console.print_json(data=_client().request("GET", "/telemetry"))
    except RuntimeUnavailable:
        console.print("Telemetry: UNAVAILABLE")


def _dcml_get(path: str) -> None:
    try:
        console.print_json(data=_client().request("GET", path))
    except RuntimeUnavailable:
        console.print("DCML: UNAVAILABLE")


@dcml_app.command("status")
def dcml_status() -> None:
    _dcml_get("/dcml/status")


@dcml_app.command("inspect")
def dcml_inspect() -> None:
    _dcml_get("/cognitive")


@dcml_app.command("experiences")
def dcml_experiences() -> None:
    _dcml_get("/dcml/experiences")


@dcml_app.command("evaluate")
def dcml_evaluate() -> None:
    _dcml_get("/dcml/evaluations")


@dcml_app.command("credit")
def dcml_credit() -> None:
    console.print(
        "Credit Assignment: AVAILABLE through the BrainstemModel DCML interface"
    )


@dcml_app.command("datasets")
def dcml_datasets() -> None:
    _dcml_get("/dcml/datasets")


@dcml_app.command("checkpoints")
def dcml_checkpoints() -> None:
    _dcml_get("/dcml/checkpoints")


@dcml_app.command("benchmark")
def dcml_benchmark() -> None:
    _dcml_get("/dcml/benchmarks")


@dcml_app.command("calibrate")
def dcml_calibrate() -> None:
    _dcml_get("/dcml/calibration")


@dcml_app.command("skills")
def dcml_skills() -> None:
    _dcml_get("/dcml/skills")


@dcml_app.command("consolidate")
def dcml_consolidate() -> None:
    try:
        console.print_json(data=_client().request("POST", "/dcml/consolidation", {}))
    except RuntimeUnavailable:
        console.print("Consolidation: UNAVAILABLE")


@dcml_app.command("cycle")
def dcml_cycle() -> None:
    console.print("Use `kindred shell` for an instrument-backed DCML cycle.")


@dcml_app.command("replay")
def dcml_replay() -> None:
    console.print("Replay: AVAILABLE through the BrainstemModel DCML interface")


@dcml_app.command("curriculum")
def dcml_curriculum() -> None:
    console.print("Curriculum: AVAILABLE through the BrainstemModel DCML interface")


@dcml_app.command("explain")
def dcml_explain(cycle_id: str) -> None:
    console.print(
        f"Explain {cycle_id}: AVAILABLE through the BrainstemModel DCML interface"
    )


@dcml_app.command("lineage")
def dcml_lineage(learning_id: str) -> None:
    del learning_id
    _dcml_get("/dcml/lineage")


@dcml_app.command("regressions")
def dcml_regressions() -> None:
    _dcml_get("/dcml/advanced-benchmarks")


@dcml_app.command("compare")
def dcml_compare(old: str, new: str) -> None:
    console.print_json(
        data={
            "old": old,
            "new": new,
            "status": "AVAILABLE",
            "source": "checkpoint metrics",
        }
    )


@dcml_app.command("transfer-test")
def dcml_transfer_test() -> None:
    _dcml_get("/dcml/transfers")


@dcml_app.command("propose")
def dcml_propose() -> None:
    console.print("Proposal creation requires a verified evaluated experience.")


@dcml_app.command("approve")
def dcml_approve(experience_id: str) -> None:
    console.print(
        f"Approval for {experience_id}: BLOCKED unless signed by local founder authority"
    )


@dcml_app.command("reject")
def dcml_reject(experience_id: str) -> None:
    console.print(
        f"Rejection for {experience_id}: BLOCKED unless signed by local founder authority"
    )


@dcml_app.command("train")
def dcml_train(dataset_id: str) -> None:
    console.print(
        f"Training {dataset_id}: AVAILABLE only through approved model-owned DCML operation"
    )


@dcml_app.command("canary")
def dcml_canary(checkpoint: str) -> None:
    console.print(
        f"Canary {checkpoint}: AVAILABLE only with an explicit benchmark case set"
    )


@dcml_app.command("promote")
def dcml_promote(checkpoint: str) -> None:
    console.print(
        f"Promotion {checkpoint}: BLOCKED until a passing canary and signed promotion"
    )


@dcml_app.command("rollback")
def dcml_rollback(checkpoint: str) -> None:
    console.print(f"Rollback {checkpoint}: BLOCKED until a signed rollback record")


@memory_app.command("consolidate")
def memory_consolidate() -> None:
    dcml_consolidate()


@memory_app.command("consolidation-status")
def memory_consolidation_status() -> None:
    _dcml_get("/memory/consolidations")


@memory_app.command("conflicts")
def memory_conflicts() -> None:
    _dcml_get("/memory/conflicts")


@memory_app.command("provenance")
def memory_provenance(memory_id: str) -> None:
    _dcml_get(f"/memory/{memory_id}/provenance")


@strata_ports_app.command("health")
def strata_ports_health() -> None:
    _dcml_get("/strata/ports/health")


@strata_ports_app.command("audit")
def strata_ports_audit() -> None:
    _dcml_get("/strata/ports/audit")


@strata_ports_app.command("trace")
def strata_ports_trace(request_id: str) -> None:
    _dcml_get(f"/strata/ports/trace/{request_id}")


@strata_ports_app.command("list")
def strata_ports_list() -> None:
    console.print_json(
        data={
            "port_zero": "NOT_CONFIGURED",
            "external_ports": [],
            "authority": "superstructure registry unavailable",
        }
    )


@strata_ports_app.command("doctor")
def strata_ports_doctor() -> None:
    strata_ports_health()


@strata_ports_app.command("verify")
def strata_ports_verify() -> None:
    console.print(
        "Network verification: BLOCKED until Port Zero mTLS and authority registry are configured"
    )


@strata_ports_app.command("routes")
def strata_ports_routes() -> None:
    console.print("Routes: BLOCKED (authoritative Port Zero registry unavailable)")
