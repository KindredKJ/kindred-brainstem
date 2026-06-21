from pathlib import Path
from brainstem.utils.paths import GENERATED, ROOT
from brainstem.utils.jsonl import append_jsonl

def execute(product_path):
    pid=Path(product_path).stem
    run_dir=GENERATED/'execution_runs'/pid; run_dir.mkdir(parents=True, exist_ok=True)
    artifact=run_dir/'local_result.txt'
    artifact.write_text(f"LOCAL VERIFIED ARTIFACT for {pid}\nMOCK: no external launch, no payment.\n", encoding='utf-8')
    rec={'product_id':pid,'status':'RESULT_PARTIAL','level':3,'artifact':str(artifact),'next_required_result':'verify artifact locally'}
    append_jsonl(ROOT/'data'/'result_ledger.jsonl', rec); return rec
