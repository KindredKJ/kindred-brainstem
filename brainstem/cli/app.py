from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="BRAINSTEM: From Signal to Infrastructure.")
console = Console()


@app.command()
def health() -> None:
    """Check the local BRAINSTEM baseline installation."""
    console.print("[bold green]BRAINSTEM health: OK[/bold green]")
    console.print("Baseline CLI is installed.")
    console.print("Next: wait for Codex implementation or run the master build locally.")


@app.command()
def status() -> None:
    """Show baseline repo status."""
    root = Path.cwd()
    console.print("[bold cyan]BRAINSTEM status[/bold cyan]")
    console.print(f"Repo: {root}")
    console.print(f"brainstem.yaml exists: {(root / 'brainstem.yaml').exists()}")
    console.print(f"doctrine.yaml exists: {(root / 'doctrine.yaml').exists()}")
    console.print(f"KRSE exists: {(root / 'brainstem' / 'engines' / 'kindred_revenue_stack_engine').exists()}")


if __name__ == "__main__":
    app()
