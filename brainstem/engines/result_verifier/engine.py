from pathlib import Path
from brainstem.utils.paths import GENERATED, ROOT
from brainstem.utils.jsonl import append_jsonl, read_jsonl
def verify(product_path):
    pid=Path(product_path).stem; artifact=GENERATED/'execution_runs'/pid/'local_result.txt'
    external=[r for r in read_jsonl(ROOT/'data'/'external_outcomes.jsonl') if r.get('product_id')==pid and not r.get('mock')]
    level=5 if external else (4 if artifact.exists() else 1)
    status='RESULT_EXTERNAL_PENDING' if level==4 else ('RESULT_VERIFIED' if level>=5 else 'RESULT_PARTIAL')
    rec={'product_id':pid,'level':level,'status':status,'evidence_refs':[str(artifact)] if artifact.exists() else [],'next_required_result':'external evidence required for level 5' if level<5 else 'human/use/payment evidence for higher level'}
    append_jsonl(ROOT/'data'/'result_ledger.jsonl', rec); return rec
