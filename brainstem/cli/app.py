from pathlib import Path
import typer
from brainstem.engines.result_contract_engine.engine import create_contract
from brainstem.engines.execution_engine.engine import execute as ex
from brainstem.engines.result_verifier.engine import verify as ver
from brainstem.engines.external_outcome_registry.registry import add_outcome, list_outcomes
from brainstem.engines.claim_guard.engine import review
from brainstem.engines.situational_awareness_engine.engine import snapshot
from brainstem.engines.earth_class_validation_engine.engine import validate
from brainstem.engines.plugcore.engine import scan as plug_scan
from brainstem.engines.model_runtime.router import ask
from brainstem.engines.associative_memory_engine import engine as mem
from brainstem.engines.backprop_engine.engine import run as bp_run, model_plan
from brainstem.engines.reality_attention_engine.engine import attend
from brainstem.engines.global_audit_engine import engine as audit_engine
from brainstem.engines.corporate_transition_engine import engine as trans
from brainstem.engines.founder_approval_plane import engine as appr
app=typer.Typer(no_args_is_help=True); outcome_app=typer.Typer(); plugcore_app=typer.Typer(); model_app=typer.Typer(); memory_app=typer.Typer(); audit_app=typer.Typer(); transition_app=typer.Typer(); approve_app=typer.Typer()
app.add_typer(outcome_app,name='outcome'); app.add_typer(plugcore_app,name='plugcore'); app.add_typer(model_app,name='model'); app.add_typer(memory_app,name='memory'); app.add_typer(audit_app,name='audit'); app.add_typer(transition_app,name='transition'); app.add_typer(approve_app,name='approve')
@app.command()
def health(): typer.echo('BRAINSTEM health: OK; local-first; no external actions')
@app.command()
def status(): typer.echo('RESULT_AUDIT_REQUIRED: evidence-ledgered v1 installed')
@app.command()
def contract(product_path: str): typer.echo(create_contract(product_path)[0])
@app.command()
def execute(product_path: str): typer.echo(ex(product_path))
@app.command()
def verify(product_path: str): typer.echo(ver(product_path))
@app.command()
def reality(product_path: str):
    create_contract(product_path); ex(product_path); typer.echo(ver(product_path))
@app.command()
def results(): typer.echo('See data/result_ledger.jsonl')
@outcome_app.command('add')
def outcome_add(product_path: str, type: str=typer.Option(...,'--type'), value: str='', mock: bool=True): typer.echo(add_outcome(product_path,type,value,mock))
@outcome_app.command('list')
def outcome_list(product_id: str): typer.echo(list_outcomes(product_id))
@app.command()
def awareness(): typer.echo(snapshot())
@app.command()
def earth(product_path: str): typer.echo(validate(product_path))
@app.command()
def claims(product_id: str, claim: list[str]=typer.Option([], '--claim')): typer.echo(review(product_id, claim))
@plugcore_app.command('scan')
def pc_scan(): typer.echo(plug_scan())
@plugcore_app.command('report')
def pc_report(): typer.echo('generated/plugcore/utilization_report.md')
@app.command('approval-server')
def approval_server(bind: str='127.0.0.1'): typer.echo(appr.server_config(bind))
@approve_app.command('list')
def approve_list(): typer.echo(appr.list_requests())
@approve_app.command('show')
def approve_show(approval_id: str): typer.echo([r for r in appr.list_requests() if r.get('approval_id')==approval_id])
@approve_app.command('approve')
def approve(approval_id: str): typer.echo(appr.set_status(approval_id,'approved'))
@approve_app.command('deny')
def deny(approval_id: str): typer.echo(appr.set_status(approval_id,'denied'))
@approve_app.command('hold')
def hold(approval_id: str): typer.echo(appr.set_status(approval_id,'held'))
@approve_app.command('revoke')
def revoke(approval_id: str): typer.echo(appr.set_status(approval_id,'revoked'))
@model_app.command('ask')
def model_ask(task: str=typer.Option(...,'--task'), input: str=typer.Option(...,'--input')): typer.echo(ask(task,input))
@memory_app.command('add')
def memory_add(title: str=typer.Option(...,'--title'), tags: str=typer.Option('', '--tags'), summary: str=typer.Option(...,'--summary')): typer.echo(mem.add(title,tags,summary))
@memory_app.command('recall')
def memory_recall(query: str): typer.echo(mem.recall(query))
@memory_app.command('list')
def memory_list(): typer.echo(mem.all())
@memory_app.command('show')
def memory_show(memory_id: str): typer.echo([r for r in mem.all() if r.get('memory_id')==memory_id])
@memory_app.command('link')
def memory_link(a: str,b: str, reason: str=typer.Option('', '--reason')): typer.echo(mem.link(a,b,reason))
@app.command()
def backprop(product_path: str): typer.echo(bp_run(product_path))
@app.command('model-backprop-plan')
def model_backprop_plan(product_path: str): typer.echo(model_plan(product_path))
@app.command('learning')
def learning(): typer.echo('Use learning list/show in v1 via data/learning_memory.jsonl')
@app.command()
def attention(product_id: str): typer.echo(attend(product_id))
@app.command('context-pack')
def context_pack(product_id: str, mode: str='evidence_first'): typer.echo(attend(product_id,mode))
@audit_app.command('start')
def audit_start(purpose: str=typer.Option(...,'--purpose')): typer.echo(audit_engine.start(purpose))
@audit_app.command('import-assets')
def import_assets(path: str): typer.echo(audit_engine.import_assets(path))
@audit_app.command('import-entities')
def import_entities(path: str): typer.echo(audit_engine.import_entities(path))
@audit_app.command('import-revenue')
def import_revenue(path: str): typer.echo(audit_engine.import_revenue(path))
@audit_app.command('import-bank')
def import_bank(path: str): typer.echo(audit_engine.import_revenue(path))
@audit_app.command('import-invoices')
def import_inv(path: str): typer.echo(audit_engine.import_revenue(path))
@audit_app.command('scan-local')
def scan_local(): typer.echo(audit_engine.scan_local())
@audit_app.command('inventory')
def inventory(): typer.echo(audit_engine.inventory())
@audit_app.command('report')
def audit_report(): typer.echo(audit_engine.report())
@audit_app.command('missing-evidence')
def missing(): typer.echo(audit_engine.missing_evidence())
@audit_app.command('cpa-pack')
def cpa_pack(): typer.echo(audit_engine.cpa_pack())
@audit_app.command('legal-pack')
def legal_pack(): typer.echo(audit_engine.legal_pack())
@audit_app.command('tax-support-pack')
def tax_pack(): typer.echo(audit_engine.cpa_pack())
@audit_app.command('export-csv')
def export_csv(): typer.echo(audit_engine.templates())
@transition_app.command('map')
def tmap(): typer.echo(trans.transition_record())
@transition_app.command('report')
def treport(): typer.echo(trans.report())
@transition_app.command('absorption-plan')
def tabs(): typer.echo(trans.absorption_plan())
@transition_app.command('risks')
def trisks(): typer.echo(trans.risks())
@transition_app.command('brand-architecture')
def tbrand(): typer.echo(trans.brand_architecture())
if __name__=='__main__': app()
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
