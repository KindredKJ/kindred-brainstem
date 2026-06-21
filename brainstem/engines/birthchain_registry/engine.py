from brainstem.utils.paths import ROOT
from brainstem.utils.jsonl import append_jsonl
def create_lineage(name,parent='Kindred Labs'):
    rec={'lineage_id':'lineage_'+name.lower().replace(' ','_'),'name':name,'parent':parent,'origin':'Kindred Labs','founder':'Kindred Jermaine Cox','legal_owner_evidence_level':0,'result_level':0,'audit_status':'evidence_needed','blockchain_anchor_status':'not_anchored','next_required_evidence':'ownership evidence'}
    return append_jsonl(ROOT/'data'/'evidence_ledger.jsonl',rec)
