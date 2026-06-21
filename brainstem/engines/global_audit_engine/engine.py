import csv, uuid
from brainstem.utils.paths import ROOT, GENERATED
from brainstem.utils.jsonl import append_jsonl, read_jsonl
DISCLAIMER='This system organizes founder-provided and publicly discoverable records for audit, planning, and professional review. It is not legal, tax, accounting, investment, or financial advice.'

def start(purpose):
    rec={'session_id':'audit_'+uuid.uuid4().hex[:8],'founder':'Kindred Jermaine Cox','purpose':purpose,'status':'evidence_needed','next_actions':['import assets','scan local repo','professional review']}
    return append_jsonl(ROOT/'data'/'audit_sessions.jsonl', rec)

def _import_csv(path, ledger, kind):
    count=0
    with open(path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            row={k:v for k,v in row.items() if k}; row.setdefault('evidence_level',1 if kind!='revenue' else 4); row.setdefault('audit_status','founder_reported' if kind!='revenue' else 'imported'); row['record_kind']=kind; row.setdefault('risk_flags','professional_review_needed')
            append_jsonl(ROOT/'data'/ledger,row); count+=1
    return {'imported':count,'ledger':ledger,'status':'RESULT_AUDIT_REQUIRED'}
def import_assets(path): return _import_csv(path,'asset_inventory.jsonl','asset')
def import_entities(path): return _import_csv(path,'entity_inventory.jsonl','entity')
def import_revenue(path): return _import_csv(path,'revenue_inventory.jsonl','revenue')
def scan_local():
    rec={'repo_id':'local_kindred_brainstem','platform':'local_git','owner':'Kindred Jermaine Cox','name':'kindred-brainstem','url':str(ROOT),'visibility':'local','local_path':str(ROOT),'evidence_level':2,'risk_flags':['public/private ownership review needed']}
    append_jsonl(ROOT/'data'/'repository_inventory.jsonl', rec); return rec
def templates():
    d=GENERATED/'audit'/'imports'/'templates'; d.mkdir(parents=True,exist_ok=True)
    heads={'assets_template.csv':'asset_id,name,category,owner_reported,related_entity,description,value_estimate_usd,tax_relevance,notes\n','entities_template.csv':'entity_id,legal_name,trade_names,jurisdiction,entity_type,status,EIN_last4,founder_role,notes\n','revenue_template.csv':'revenue_id,source_name,source_type,related_entity,related_product,processor,amount,currency,transaction_date,tax_year,evidence_ref,notes\n','bank_template.csv':'date,description,amount,currency,account_name,entity,category,evidence_ref,notes\n','invoices_template.csv':'invoice_id,date,due_date,entity,customer,description,amount,currency,status,notes\n','domains_template.csv':'domain,registrar,owner_reported,expiration_date,related_entity,notes\n','repos_template.csv':'platform,owner,name,url,visibility,related_product,notes\n','ip_template.csv':'name,ip_type,owner_reported,legal_owner,registration_number,jurisdiction,status,notes\n','liabilities_template.csv':'liability_id,name,related_entity,type,amount,currency,due_date,status,notes\n'}
    for n,h in heads.items(): (d/n).write_text(h,encoding='utf-8')
    return d
def report():
    templates(); d=GENERATED/'audit'/'reports'; d.mkdir(parents=True,exist_ok=True)
    sections=['Executive Summary','Founder Identity','Entity Inventory','Asset Inventory','Revenue Inventory','Liability Inventory','Domain Inventory','Repo Inventory','IP Inventory','Evidence Levels','Missing Evidence','Tax-Relevant Records','CPA Review Needs','Legal Review Needs','Risk Flags','Next Required Actions']
    text='# Global Audit Report\n\n'+DISCLAIMER+'\n\n'+'\n\n'.join(f'## {s}\nEvidence required; professional review required where applicable.' for s in sections)
    p=d/'global_audit_report.md'; p.write_text(text,encoding='utf-8'); return p
def cpa_pack():
    templates(); d=GENERATED/'audit'/'cpa_exports'; d.mkdir(parents=True,exist_ok=True)
    p=d/'cpa_review_packet.md'; p.write_text('# CPA Review Packet\n\n'+DISCLAIMER+'\n\n## Tax Years Covered\nReview required.\n\n## Revenue Summary\nImported records are not tax-ready.\n\n## Questions for CPA\nWhat additional evidence is required?\n\n## Next Required Actions\nAttach statements and professional review.\n',encoding='utf-8'); return p
def legal_pack():
    d=GENERATED/'audit'/'legal_review_packets'; d.mkdir(parents=True,exist_ok=True)
    p=d/'legal_review_packet.md'; p.write_text('# Legal Review Packet\n\n'+DISCLAIMER+'\n\n## Entity Map\nEvidence needed.\n\n## BRAINSTEM Transition Options\nNo legal consolidation claimed.\n\n## Questions for Attorney\nWhat filings or assignments are required?\n\n## Next Required Actions\nProfessional review.\n',encoding='utf-8'); return p
def inventory(): return {'assets':len(read_jsonl(ROOT/'data'/'asset_inventory.jsonl')),'entities':len(read_jsonl(ROOT/'data'/'entity_inventory.jsonl')),'revenue':len(read_jsonl(ROOT/'data'/'revenue_inventory.jsonl'))}
def missing_evidence(): return {'missing':['legal ownership evidence','private statements','professional review'],'status':'RESULT_AUDIT_REQUIRED'}
