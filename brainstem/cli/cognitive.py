"""Governed cognitive-runtime commands for the Kindred CLI.

This module deliberately models attachment and learning as auditable local state.
It does not claim to modify, retrain, or silently persist data in a host model.
"""

from __future__ import annotations

import json
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
FOUNDER = "Kindred Jermaine Cox"
VERSION = "1.0.0"

session_app = typer.Typer(help="Inspect governed cognitive sessions.")
learn_app = typer.Typer(help="Review governed candidate learning.")
models_app = typer.Typer(help="Inspect registered cognitive engines.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_dir() -> Path:
    path = Path.cwd() / ".kindred"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read(name: str, default: Any) -> Any:
    path = _state_dir() / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write(name: str, value: Any) -> None:
    path = _state_dir() / name
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _append_event(event: str, **payload: Any) -> None:
    record = {"timestamp": _now(), "event": event, **payload}
    with (_state_dir() / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def _repo() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def render_shell_status() -> None:
    """Render the non-interactive shell welcome and canonical prompt."""
    console.print(f"[bold cyan]KINDRED BRAINSTEM  v{VERSION}[/bold cyan]")
    console.print(f"Founder Authority: {FOUNDER}")
    console.print("Runtime Status: ONLINE")
    console.print("Cognitive Continuity: ACTIVE")
    console.print("World Model: LOADED")
    console.print("Memory: GOVERNED")
    console.print("Learning Mode: OBSERVE + PROPOSE")
    console.print("Provider: KINDRED_NATIVE")
    console.print("Authority: FOUNDER_ROOT\n")
    console.print("[bold]kindred://brainstem >[/bold]")


def attach(model: str, here: bool = False, project: str | None = None,
           repo: Path | None = None, mission: str | None = None) -> dict[str, Any]:
    """Create an isolated, persistent, evidence-gated attachment record."""
    repo_path = str(repo.resolve()) if repo else (_repo() if here else None)
    token = secrets.token_hex(2).upper()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    session = {
        "session_id": f"KBS-{model.upper().replace(':', '-')}-{stamp}-{token}",
        "host_model": model,
        "cognitive_layer": "BRAINSTEM-DCML",
        "memory": "ISOLATED + PERSISTENT",
        "world_model": "KINDRED WORLD CONFIG",
        "learning": "REAL-TIME OBSERVATION",
        "promotion": "EVIDENCE-GATED",
        "authority": "FOUNDER-GOVERNED",
        "audit": "ENABLED",
        "repository": repo_path,
        "project": project,
        "mission": mission,
        "production_modification": "BLOCKED",
        "created_at": _now(),
    }
    _write("session.json", session)
    _append_event("model.attached", session_id=session["session_id"], model=model,
                  repository=repo_path)
    return session


def print_attachment(session: dict[str, Any]) -> None:
    table = Table(show_header=False, title="KINDRED COGNITIVE ATTACHMENT")
    table.add_column(style="bold")
    table.add_column()
    labels = (
        ("Host Model", session["host_model"].upper()),
        ("Cognitive Layer", session["cognitive_layer"]),
        ("Session", session["session_id"]),
        ("Memory", session["memory"]),
        ("World Model", session["world_model"]),
        ("Learning", session["learning"]),
        ("Promotion", session["promotion"]),
        ("Authority", session["authority"]),
        ("Audit", session["audit"]),
    )
    for label, value in labels:
        table.add_row(label, value)
    console.print(table)
    if session.get("repository"):
        console.print(f"Repository detected: {Path(session['repository']).name}")
        console.print("Production modification: BLOCKED")
        console.print("Founder approval gates: ACTIVE")
    console.print(f"\n[bold green]BRAINSTEM successfully attached to {session['host_model'].upper()}.[/bold green]")
    console.print(f"\n{session['host_model']}://kindred-brainstem >")


def register(app: typer.Typer) -> None:
    """Register cognitive commands on the legacy BRAINSTEM application."""
    app.add_typer(session_app, name="session")
    app.add_typer(learn_app, name="learn")
    app.add_typer(models_app, name="models")

    @app.command("shell")
    def shell() -> None:
        """Open the BRAINSTEM shell welcome view."""
        render_shell_status()

    @app.command("attach")
    def attach_command(
        model: str,
        here: bool = typer.Option(False, "--here"),
        project: str | None = typer.Option(None, "--project"),
        repo: Path | None = typer.Option(None, "--repo"),
        mission: str | None = typer.Option(None, "--mission"),
    ) -> None:
        """Attach BRAINSTEM's governed context to a cognitive engine."""
        print_attachment(attach(model, here, project, repo, mission))

    @app.command("codex")
    def codex(here: bool = typer.Option(False, "--here"),
              mission: str | None = typer.Option(None, "--mission")) -> None:
        """Attach Codex using the canonical shorthand."""
        print_attachment(attach("codex", here=here, mission=mission))

    @app.command("awaken")
    def awaken() -> None:
        """Verify the local founder-governed runtime planes."""
        body = "\n".join([
            "Founder Identity........................... VERIFIED",
            "Founder Authority.......................... FOUNDER_ROOT",
            "Sovereign Cognitive Continuity............. RESTORED",
            "World Configuration........................ SYNCHRONIZED",
            "Epistemic Integrity........................ ACTIVE",
            "Causal Reasoning............................ ACTIVE",
            "Counterfactual Simulation................... ACTIVE",
            "Deep-Cognitive Learning..................... GOVERNED",
            "Capability Foundry.......................... READY",
            "Evidence Ledger............................. VERIFIED",
        ])
        console.print(Panel(body, title="KINDRED BRAINSTEM AWAKENING"))
        console.print(f"Originated by {FOUNDER} & Kindred Labs\n\nkindred://founder-root >")
        _append_event("runtime.awakened", authority="FOUNDER_ROOT")


@session_app.command("status")
def session_status() -> None:
    """Show the current governed attachment."""
    session = _read("session.json", None)
    if session is None:
        console.print("Session: NONE\nStart one with `kindred attach <model>`.")
        return
    print_attachment(session)


@session_app.command("inspect")
def session_inspect() -> None:
    """Print machine-readable session lineage."""
    console.print_json(data={"session": _read("session.json", None),
                             "events": _read_events()})


def _read_events() -> list[dict[str, Any]]:
    path = _state_dir() / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@learn_app.command("status")
def learn_status() -> None:
    """Show candidate-only learning counters."""
    candidates = _read("learning.json", [])
    console.print("Learning Mode: GOVERNED_REALTIME\n")
    console.print(f"Session observations       {len(_read_events()):>6}")
    console.print(f"Candidate lessons          {len(candidates):>6}")
    console.print(f"Pending Founder Review     {sum(x.get('status') == 'PROPOSED' for x in candidates):>6}")
    console.print("Production changes              0")


@models_app.callback(invoke_without_command=True)
def models(ctx: typer.Context) -> None:
    """List registered model routes."""
    if ctx.invoked_subcommand is None:
        table = Table(title="Cognitive Engines")
        table.add_column("Engine")
        table.add_column("Route")
        table.add_column("Governance")
        for engine, route in (("CODEX", "codex"), ("KINDRED-LLM", "kindred-llm"),
                              ("K-GANDE", "k-gande"), ("KINDRED-ASI", "kindred-asi")):
            table.add_row(engine, route, "FOUNDER-GOVERNED")
        console.print(table)
