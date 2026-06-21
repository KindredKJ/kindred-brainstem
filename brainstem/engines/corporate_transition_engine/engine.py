from brainstem.utils.paths import GENERATED, ROOT
from brainstem.utils.jsonl import append_jsonl
DISCLAIMER='This system organizes founder-provided and publicly discoverable records for audit, planning, and professional review. It is not legal, tax, accounting, investment, or financial advice.'

def transition_record():
    rec={'transition_id':'brainstem_transition_v1','proposed_parent_brand':'BRAINSTEM','origin_lab':'Kindred Labs','status':'professional_review_needed','legal_completion_claimed':False,'risks':['trademark_review_needed','IP_assignment_evidence_needed'],'next_actions':['legal review packet','asset assignment checklist']}
    append_jsonl(ROOT/'data'/'corporate_transition.jsonl', rec); return rec

def report():
    transition_record(); d=GENERATED/'corporate_transition'/'reports'; d.mkdir(parents=True,exist_ok=True)
    sections=['Proposed Brand Architecture','Kindred Labs Lineage Preservation','BRAINSTEM Public Company Candidate','Asset Absorption Plan','Entity Transition Options','IP Assignment Plan','Risk Flags','Founder Approval Needs','Professional Review Needs','Next Required Actions']
    p=d/'BRAINSTEM_transition_report.md'
    p.write_text('# BRAINSTEM Transition Report\n\n'+DISCLAIMER+'\n\nNo legal absorption, legal consolidation, IP assignment, or trademark clearance is claimed.\n\n'+'\n\n'.join(f'## {s}\nProposed only; evidence and professional review required.' for s in sections),encoding='utf-8')
    return p

def absorption_plan(): return {'status':'proposed','professional_review_required':True,'next_actions':['collect evidence']}
def risks(): return {'risks':['trademark_review_needed','ownership_evidence_needed'],'legal_completion_claimed':False}
def brand_architecture(): return {'public_brand':'BRAINSTEM','origin_lab':'Kindred Labs','founder':'Kindred Jermaine Cox'}
