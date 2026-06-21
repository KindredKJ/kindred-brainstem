from pathlib import Path
from typer.testing import CliRunner
from brainstem.cli.app import app
from brainstem.engines.kindred_revenue_stack_engine.engine import KindredRevenueStackEngine
from brainstem.engines.result_contract_engine.engine import create_contract
from brainstem.engines.execution_engine.engine import execute
from brainstem.engines.result_verifier.engine import verify
from brainstem.engines.external_outcome_registry.registry import add_outcome
from brainstem.engines.claim_guard.engine import review
from brainstem.engines.founder_approval_plane import engine as appr
from brainstem.engines.plugcore.engine import scan
from brainstem.engines.model_runtime.router import ask
from brainstem.engines.associative_memory_engine import engine as mem
from brainstem.engines.backprop_engine.engine import run
from brainstem.engines.reality_attention_engine.engine import attend
from brainstem.engines.global_audit_engine import engine as audit
from brainstem.engines.corporate_transition_engine import engine as trans
from brainstem.utils.paths import ROOT, GENERATED
from brainstem.utils.jsonl import append_jsonl

def test_health_and_krse_import():
    r=CliRunner().invoke(app,['health']); assert r.exit_code==0 and 'OK' in r.output
    assert KindredRevenueStackEngine().generate_plan({'name':'x'}).product_name=='x'

def test_reality_loop_and_external_level_gate():
    c,p=create_contract('products/moneyback_scan.yaml'); assert p.exists()
    e=execute('products/moneyback_scan.yaml'); assert Path(e['artifact']).exists()
    v=verify('products/moneyback_scan.yaml'); assert v['level'] == 4
    add_outcome('moneyback_scan','live_url_verified','https://example.com',mock=True)
    assert verify('products/moneyback_scan.yaml')['level'] == 4

def test_claim_guard_approval_plugcore_model_memory_backprop_attention():
    cg=review('moneyback_scan',['revenue_generating','tax_ready']); assert cg['results'][0]['safe_claim']=='revenue_path_defined' and cg['results'][1]['safe_claim']=='tax_professional_review_packet_needed'
    ar=appr.request('public_launch','moneyback_scan'); assert ar['status']=='pending' and appr.blocks('public_launch', ar['approval_id'])
    assert appr.server_config()['bind']=='127.0.0.1'
    assert scan()['host_type']=='local_machine'
    assert ask('situational_summary','x')['model']=='rule_model'
    m=mem.add('Result-Only Doctrine','result,verification,external proof','Only verified results count.'); assert mem.recall('external proof')
    assert 'result_gap_loss' in run('products/moneyback_scan.yaml')['losses']
    assert attend('moneyback_scan')['top_node']['type']=='audit_missing_evidence'

def test_audit_and_transition_and_hash_chain(tmp_path):
    sess=audit.start('global founder asset and revenue audit'); assert sess['status']=='evidence_needed'
    acsv=tmp_path/'assets.csv'; acsv.write_text('asset_id,name,category,owner_reported,related_entity,description,value_estimate_usd,tax_relevance,notes\na1,Brainstem,software_project,Kindred,,desc,0,yes,n\n')
    rcsv=tmp_path/'rev.csv'; rcsv.write_text('revenue_id,source_name,source_type,related_entity,related_product,processor,amount,currency,transaction_date,tax_year,evidence_ref,notes\nr1,Mock,manual,,,none,0,USD,2026-01-01,2026,MOCK,n\n')
    assert audit.import_assets(str(acsv))['imported']==1
    assert audit.import_revenue(str(rcsv))['imported']==1
    assert audit.report().exists() and audit.cpa_pack().exists()
    tr=trans.transition_record(); assert tr['legal_completion_claimed'] is False and trans.report().exists()
    path=ROOT/'data'/'evidence_ledger.jsonl'; r1=append_jsonl(path, {'x':1}); r2=append_jsonl(path, {'x':2}); assert r2['previous_hash']==r1['record_hash']
    outputs=''.join(p.read_text(errors='ignore') for p in GENERATED.rglob('*.md'))
    assert 'password=' not in outputs.lower() and 'api_key=' not in outputs.lower()
