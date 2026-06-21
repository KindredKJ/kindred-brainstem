from pathlib import Path
from brainstem.utils.paths import ROOT
from brainstem.utils.jsonl import append_jsonl, read_jsonl
def add_outcome(product_path_or_id, outcome_type, value, mock=True):
    pid=Path(product_path_or_id).stem
    rec={'product_id':pid,'outcome_type':outcome_type,'value':value,'mock':mock,'status':'MOCK_RECORDED' if mock else 'EVIDENCE_RECORDED'}
    return append_jsonl(ROOT/'data'/'external_outcomes.jsonl', rec)
def list_outcomes(product_id): return [r for r in read_jsonl(ROOT/'data'/'external_outcomes.jsonl') if r.get('product_id')==product_id]
