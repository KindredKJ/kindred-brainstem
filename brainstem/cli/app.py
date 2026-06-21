from __future__ import annotations

import json
import platform
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="BRAINSTEM: From Signal to Infrastructure.")
console = Console()

plugcore_app = typer.Typer(help="PlugCore host adaptation commands.")
audit_app = typer.Typer(help="Global founder asset/company/revenue audit commands.")
transition_app = typer.Typer(help="BRAINSTEM corporate transition commands.")
outcome_app = typer.Typer(help="External outcome registry commands.")

app.add_typer(plugcore_app, name="plugcore")
app.add_typer(audit_app, name="audit")
app.add_typer(transition_app, name="transition")
app.add_typer(outcome_app, name="outcome")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def slug_from_product(product_path_or_name: str) -> str:
    raw = str(product_path_or_name).replace("\\", "/")
    name = Path(raw).stem if "." in Path(raw).name else Path(raw).name
    return name.strip().replace(" ", "_").lower() or "unknown"


def safe_git_status() -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.stdout.strip() or "clean"
    except Exception:
        return "git_status_unavailable"


@app.command()
def health() -> None:
    """Check the local BRAINSTEM installation."""
    console.print("[bold green]BRAINSTEM health: OK[/bold green]")
    console.print("CLI: integrated")
    console.print("Doctrine: result-only")
    console.print("External side effects: disabled by default")


@app.command()
def status() -> None:
    """Show local BRAINSTEM repo status."""
    root = Path.cwd()
    table = Table(title="BRAINSTEM status")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Repo", str(root))
    table.add_row("brainstem.yaml", str((root / "brainstem.yaml").exists()))
    table.add_row("doctrine.yaml", str((root / "doctrine.yaml").exists()))
    table.add_row("KRSE", str((root / "brainstem" / "engines" / "kindred_revenue_stack_engine").exists()))
    table.add_row("Git", safe_git_status())
    console.print(table)


@app.command()
def contract(product_path: Path) -> None:
    """Create a result contract for a product candidate."""
    product = read_yaml(product_path)
    slug = slug_from_product(str(product_path))
    contract_id = f"BRC-{slug}-{uuid.uuid4().hex[:8]}"
    record = {
        "contract_id": contract_id,
        "product_slug": slug,
        "product_path": str(product_path),
        "product": product,
        "result_level_target": 4,
        "status": "RESULT_CONTRACT_CREATED",
        "external_side_effects": False,
        "next_required_result": "Run execution and local verification.",
        "created_at": utc_now(),
    }
    out = Path("generated/result_contracts") / f"{slug}_contract.yaml"
    write_yaml(out, record)
    append_jsonl(Path("data/result_ledger.jsonl"), record)
    console.print(f"[bold green]Result contract created:[/bold green] {out}")


@app.command()
def execute(product_path: Path) -> None:
    """Execute a safe local artifact generation run for a product candidate."""
    product = read_yaml(product_path)
    slug = slug_from_product(str(product_path))
    run_id = f"BRE-{slug}-{uuid.uuid4().hex[:8]}"
    report = f"""# BRAINSTEM Execution Report

Product: {product.get("name", slug)}
Run ID: {run_id}
Status: RESULT_PARTIAL
Result level: 3 - local_execution_completed

## Generated Artifact
This is a safe local execution artifact. No external launch, payment, filing, or public action occurred.

## Next Required Result
Run `brainstem verify {product_path}` to verify local artifacts.
"""
    out = Path("generated/execution_runs") / f"{slug}_execution_report.md"
    write_text(out, report)
    record = {
        "run_id": run_id,
        "product_slug": slug,
        "product_path": str(product_path),
        "status": "RESULT_PARTIAL",
        "result_level": 3,
        "artifact": str(out),
        "external_side_effects": False,
        "created_at": utc_now(),
    }
    append_jsonl(Path("data/result_ledger.jsonl"), record)
    console.print(f"[bold green]Execution artifact created:[/bold green] {out}")


@app.command()
def verify(product_path: Path) -> None:
    """Verify local BRAINSTEM artifacts for a product candidate."""
    slug = slug_from_product(str(product_path))
    execution_report = Path("generated/execution_runs") / f"{slug}_execution_report.md"
    verified = execution_report.exists()
    result_level = 4 if verified else 2
    status_value = "RESULT_VERIFIED" if verified else "RESULT_PARTIAL"
    report = {
        "product_slug": slug,
        "product_path": str(product_path),
        "status": status_value,
        "result_level": result_level,
        "verification": {
            "local_execution_report_exists": verified,
            "external_impact_verified": False,
            "revenue_verified": False,
            "tax_ready": False,
            "legal_consolidation_verified": False,
        },
        "next_required_result": "Record a real external outcome to move beyond local verification.",
        "created_at": utc_now(),
    }
    out = Path("generated/result_reports") / f"{slug}_verification.yaml"
    write_yaml(out, report)
    append_jsonl(Path("data/result_ledger.jsonl"), report)
    console.print(f"[bold green]Verification complete:[/bold green] level {result_level} → {out}")


@app.command()
def reality(product_path: Path) -> None:
    """Run the safe local reality loop: contract -> execute -> verify summary."""
    slug = slug_from_product(str(product_path))
    product = read_yaml(product_path)

    contract(product_path)
    execute(product_path)
    verify(product_path)

    summary = f"""# BRAINSTEM Reality Report

Product: {product.get("name", slug)}
Current status: RESULT_VERIFIED
Current result level: 4 - local_result_verified
External impact: RESULT_EXTERNAL_PENDING
Revenue proof: payment_not_verified
Legal/tax status: professional_review_required

## Next Required Result
Record non-mock external evidence or customer/payment evidence before claiming launch, revenue, or external impact.
"""
    out = Path("generated/result_reports") / f"{slug}_reality_report.md"
    write_text(out, summary)
    console.print(f"[bold cyan]Reality report:[/bold cyan] {out}")


@app.command()
def awareness() -> None:
    """Generate situational awareness snapshot."""
    root = Path.cwd()
    engines = list((root / "brainstem" / "engines").glob("*")) if (root / "brainstem" / "engines").exists() else []
    snapshot = {
        "snapshot_id": f"BSA-{uuid.uuid4().hex[:8]}",
        "created_at": utc_now(),
        "repo": str(root),
        "git_status": safe_git_status(),
        "engine_count": len([e for e in engines if e.is_dir()]),
        "krse_present": (root / "brainstem" / "engines" / "kindred_revenue_stack_engine").exists(),
        "result_only_doctrine_present": (root / "config" / "result_only_doctrine.yaml").exists(),
        "current_position": "local_integrated_candidate",
        "next_required_result": "Pass CLI verification commands and preserve generated evidence locally.",
    }
    out = Path("generated/situational_awareness/awareness_snapshot.yaml")
    write_yaml(out, snapshot)
    append_jsonl(Path("data/situational_awareness.jsonl"), snapshot)
    console.print(f"[bold green]Situational awareness snapshot created:[/bold green] {out}")


@app.command()
def claims(
    candidate: str,
    claim: list[str] = typer.Option([], "--claim", help="Claim to check."),
) -> None:
    """Run claim guard against unsupported claims."""
    downgrade = {
        "production_ready": "staging_candidate",
        "launched": "launch_planned_or_unverified",
        "revenue_generating": "revenue_path_defined",
        "paid_result": "payment_not_verified",
        "externally_impactful": "external_impact_pending",
        "blockchain_backed": "blockchain_anchor_pending",
        "autonomous": "human_gated_automation",
        "world_class": "earth_class_candidate",
        "best_on_earth": "unproven_high_potential",
        "verified": "verification_pending",
        "scalable": "scaling_candidate",
        "fully_adaptive": "adaptive_architecture_candidate",
        "plug_and_play": "plugcore_candidate",
        "hardware_ready": "hardware_adapter_needed",
        "tax_ready": "tax_professional_review_packet_needed",
        "legally_consolidated": "legal_transition_plan_needed",
        "trademark_cleared": "trademark_review_needed",
        "asset_owned": "ownership_evidence_needed",
        "revenue_verified": "revenue_evidence_needed",
        "CPA_ready": "CPA_review_packet_candidate",
        "investor_ready": "investor_diligence_packet_needed",
    }
    checked = []
    table = Table(title=f"Claim Guard: {candidate}")
    table.add_column("Claim")
    table.add_column("Allowed Status")
    for item in claim:
        checked.append({"claim": item, "allowed_status": downgrade.get(item, "claim_review_required")})
        table.add_row(item, downgrade.get(item, "claim_review_required"))
    record = {
        "candidate": candidate,
        "checked": checked,
        "status": "CLAIM_GUARD_COMPLETE",
        "created_at": utc_now(),
    }
    append_jsonl(Path("data/claim_guard.jsonl"), record)
    console.print(table)


@outcome_app.command("add")
def outcome_add(
    product_path: Path,
    type: str = typer.Option(..., "--type"),
    value: str = typer.Option(..., "--value"),
    mock: bool = typer.Option(False, "--mock"),
) -> None:
    """Add an external outcome record. Mock outcomes are not real proof."""
    slug = slug_from_product(str(product_path))
    record = {
        "outcome_id": f"BEO-{uuid.uuid4().hex[:8]}",
        "product_slug": slug,
        "product_path": str(product_path),
        "type": type,
        "value": value,
        "is_mock": mock,
        "evidence_level": 1 if mock else 3,
        "status": "MOCK_OUTCOME_RECORDED" if mock else "OUTCOME_RECORDED",
        "created_at": utc_now(),
    }
    append_jsonl(Path("data/external_outcomes.jsonl"), record)
    out = Path("generated/external_outcomes") / f"{slug}_{record['outcome_id']}.yaml"
    write_yaml(out, record)
    console.print(f"[bold green]Outcome recorded:[/bold green] {out}")
    if mock:
        console.print("[yellow]MOCK outcome: do not claim real external impact.[/yellow]")


@outcome_app.command("list")
def outcome_list(candidate: str) -> None:
    """List known outcomes for a candidate."""
    path = Path("data/external_outcomes.jsonl")
    table = Table(title=f"Outcomes: {candidate}")
    table.add_column("Type")
    table.add_column("Value")
    table.add_column("Mock")
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec.get("product_slug") == candidate or candidate in rec.get("product_path", ""):
                table.add_row(str(rec.get("type")), str(rec.get("value")), str(rec.get("is_mock")))
    console.print(table)


@plugcore_app.command("scan")
def plugcore_scan() -> None:
    """Scan host capability profile safely."""
    profile = {
        "host_profile_id": f"BPC-{uuid.uuid4().hex[:8]}",
        "created_at": utc_now(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "git_available": shutil.which("git") is not None,
        "docker_available": shutil.which("docker") is not None,
        "access_level": "observe",
        "execute_hard_requires_founder_approval": True,
        "overall_safe_potential_score": 55,
        "next_required_result": "Add deeper hardware/resource adapters after baseline verification.",
    }
    out = Path("generated/plugcore/host_profile.yaml")
    write_yaml(out, profile)
    console.print(f"[bold green]PlugCore host profile created:[/bold green] {out}")


@plugcore_app.command("report")
def plugcore_report() -> None:
    """Show PlugCore report path/status."""
    path = Path("generated/plugcore/host_profile.yaml")
    if not path.exists():
        console.print("[yellow]No PlugCore profile yet. Run: brainstem plugcore scan[/yellow]")
        raise typer.Exit(code=1)
    console.print(path.read_text(encoding="utf-8"))


@audit_app.command("start")
def audit_start(
    purpose: str = typer.Option("global founder asset and revenue audit", "--purpose"),
) -> None:
    """Start a local audit session."""
    record = {
        "session_id": f"BAUD-{uuid.uuid4().hex[:8]}",
        "founder": "Kindred Jermaine Cox",
        "purpose": purpose,
        "status": "audit_started",
        "evidence_level": 1,
        "professional_review_required": True,
        "created_at": utc_now(),
        "next_actions": [
            "Import assets CSV.",
            "Import entities CSV.",
            "Import revenue CSV.",
            "Attach evidence before treating items as verified.",
        ],
    }
    append_jsonl(Path("data/audit_sessions.jsonl"), record)
    out = Path("generated/audit/sessions") / f"{record['session_id']}.yaml"
    write_yaml(out, record)
    console.print(f"[bold green]Audit session started:[/bold green] {out}")


@audit_app.command("scan-local")
def audit_scan_local() -> None:
    """Create a local repo/product inventory snapshot."""
    root = Path.cwd()
    record = {
        "scan_id": f"BSCAN-{uuid.uuid4().hex[:8]}",
        "created_at": utc_now(),
        "repo": str(root),
        "products": [str(p) for p in Path("products").glob("*.yaml")],
        "configs": [str(p) for p in Path("config").glob("*.yaml")],
        "engine_count": len([p for p in Path("brainstem/engines").glob("*") if p.is_dir()]),
        "evidence_level": 2,
        "status": "local_record_found",
    }
    append_jsonl(Path("data/asset_inventory.jsonl"), record)
    out = Path("generated/audit/reports/local_scan.yaml")
    write_yaml(out, record)
    console.print(f"[bold green]Local audit scan created:[/bold green] {out}")


@audit_app.command("inventory")
def audit_inventory() -> None:
    """Show audit inventory file status."""
    files = [
        "data/audit_sessions.jsonl",
        "data/asset_inventory.jsonl",
        "data/entity_inventory.jsonl",
        "data/revenue_inventory.jsonl",
    ]
    table = Table(title="Audit inventory")
    table.add_column("File")
    table.add_column("Exists")
    for file in files:
        table.add_row(file, str(Path(file).exists()))
    console.print(table)


@audit_app.command("report")
def audit_report() -> None:
    """Generate global audit report."""
    report = """# BRAINSTEM Global Audit Report

Founder: Kindred Jermaine Cox

## Status
Local audit-support report generated.

## Evidence Rule
No asset, company, revenue, or ownership claim is verified without evidence.

## Professional Review
Required for legal, tax, accounting, investment, or filing conclusions.

## Next Required Actions
- Import entity records.
- Import asset records.
- Import revenue/payment records.
- Attach evidence.
- Export CPA/legal review packet.
"""
    out = Path("generated/audit/reports/global_audit_report.md")
    write_text(out, report)
    console.print(f"[bold green]Audit report generated:[/bold green] {out}")


@audit_app.command("cpa-pack")
def audit_cpa_pack() -> None:
    """Generate CPA review packet."""
    report = """# BRAINSTEM CPA Review Packet

This packet organizes founder-provided and local records for professional review.

It is not tax advice and is not a tax filing.

## Next Required Actions
- Import bank/payment CSVs.
- Attach 1099s/W-9s if available.
- Reconcile revenue by tax year.
- Review with a qualified tax professional.
"""
    out = Path("generated/audit/cpa_exports/cpa_review_packet.md")
    write_text(out, report)
    console.print(f"[bold green]CPA packet generated:[/bold green] {out}")


@audit_app.command("legal-pack")
def audit_legal_pack() -> None:
    """Generate legal review packet."""
    report = """# BRAINSTEM Legal Review Packet

This packet organizes entity, IP, domain, and transition questions for attorney review.

It is not legal advice and does not perform filings.
"""
    out = Path("generated/audit/legal_review_packets/legal_review_packet.md")
    write_text(out, report)
    console.print(f"[bold green]Legal packet generated:[/bold green] {out}")


@audit_app.command("tax-support-pack")
def audit_tax_support_pack() -> None:
    """Generate tax support packet."""
    out = Path("generated/audit/tax_support_packets/tax_support_packet.md")
    write_text(out, "# BRAINSTEM Tax Support Packet\n\nProfessional review required.\n")
    console.print(f"[bold green]Tax support packet generated:[/bold green] {out}")


@audit_app.command("missing-evidence")
def audit_missing_evidence() -> None:
    """Generate missing evidence report."""
    out = Path("generated/audit/reports/missing_evidence.md")
    write_text(out, "# Missing Evidence\n\n- Entity filings\n- EIN confirmation\n- Bank/payment records\n- IP ownership evidence\n")
    console.print(f"[bold yellow]Missing evidence report generated:[/bold yellow] {out}")


@audit_app.command("export-csv")
def audit_export_csv() -> None:
    """Generate simple CPA CSV export placeholder."""
    out = Path("generated/audit/cpa_exports/revenue_export.csv")
    write_text(out, "date,source,amount,currency,evidence_ref\n")
    console.print(f"[bold green]CSV export generated:[/bold green] {out}")


@transition_app.command("report")
def transition_report() -> None:
    """Generate BRAINSTEM corporate transition report."""
    report = """# BRAINSTEM Transition Report

## Proposed Public Brand
BRAINSTEM

## Origin Lab
Kindred Labs

## Founder
Kindred Jermaine Cox

## Status
Proposed transition map only. No legal consolidation has occurred.

## Strategic Model
BRAINSTEM becomes the public startup/company umbrella.
Kindred Labs remains the origin lab and lineage source.
Kindred-created systems become candidate lineage assets pending ownership evidence.

## Professional Review Required
- Entity structure
- IP assignment
- Trademark review
- Tax/accounting review
- Domain/asset ownership verification

## Next Required Actions
- Inventory all entities.
- Inventory all repositories/products/domains.
- Attach evidence.
- Review with attorney/CPA before filings.
"""
    out = Path("generated/corporate_transition/reports/BRAINSTEM_transition_report.md")
    write_text(out, report)
    console.print(f"[bold green]Transition report generated:[/bold green] {out}")


@transition_app.command("map")
def transition_map() -> None:
    """Generate transition map."""
    data = {
        "proposed_parent_brand": "BRAINSTEM",
        "origin_lab": "Kindred Labs",
        "founder": "Kindred Jermaine Cox",
        "status": "proposed",
        "legal_consolidation_verified": False,
        "professional_review_required": True,
    }
    out = Path("generated/corporate_transition/maps/transition_map.yaml")
    write_yaml(out, data)
    console.print(f"[bold green]Transition map generated:[/bold green] {out}")


@transition_app.command("absorption-plan")
def transition_absorption_plan() -> None:
    """Generate absorption plan."""
    out = Path("generated/corporate_transition/absorption_plans/absorption_plan.md")
    write_text(out, "# BRAINSTEM Absorption Plan\n\nEvidence and professional review required before legal action.\n")
    console.print(f"[bold green]Absorption plan generated:[/bold green] {out}")


@transition_app.command("risks")
def transition_risks() -> None:
    """Generate transition risk flags."""
    out = Path("generated/corporate_transition/risk_flags/risk_flags.md")
    write_text(out, "# Transition Risk Flags\n\n- Trademark risk\n- Entity ownership uncertainty\n- IP assignment evidence needed\n")
    console.print(f"[bold yellow]Risk flags generated:[/bold yellow] {out}")


@transition_app.command("brand-architecture")
def transition_brand_architecture() -> None:
    """Generate brand architecture report."""
    out = Path("generated/corporate_transition/reports/brand_architecture.md")
    write_text(out, "# Brand Architecture\n\nBRAINSTEM = public umbrella\nKindred Labs = origin lab\n")
    console.print(f"[bold green]Brand architecture generated:[/bold green] {out}")


if __name__ == "__main__":
    app()
