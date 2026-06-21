from pathlib import Path
from brainstem.utils.paths import ROOT, GENERATED
from brainstem.utils.jsonl import append_jsonl

def run(product_path):
    pid=Path(product_path).stem; losses={'result_gap_loss':1.0,'external_impact_loss':1.0,'revenue_gap_loss':1.0,'audit_evidence_loss':1.0,'transition_readiness_loss':1.0}
    rec={'product_id':pid,'losses':losses,'status':'RESULT_REFINED','next_required_result':'reduce largest evidence gaps'}
    append_jsonl(ROOT/'data'/'backprop_events.jsonl', rec)
    d=GENERATED/'backprop'/'learning_reports'; d.mkdir(parents=True,exist_ok=True)
    (d/f'{pid}.md').write_text('# Learning Report\n\nNext required actions: attach external evidence and revenue proof.\n',encoding='utf-8')
    return rec

def model_plan(product_path): return {'status':'planning_only','no_training':True,'next_required_result':'collect reviewed training requirements'}
