from pathlib import Path
from brainstem.utils.paths import GENERATED, ROOT
from brainstem.utils.yaml_io import read_yaml, write_yaml
from brainstem.utils.jsonl import append_jsonl
def product_id(path): return Path(path).stem
def create_contract(product_path):
    data=read_yaml(ROOT/product_path) if not Path(product_path).is_absolute() else read_yaml(Path(product_path))
    pid=data.get('id') or data.get('name') or product_id(product_path)
    contract={'product_id':pid,'result_level_target':4,'status':'RESULT_EXTERNAL_PENDING','next_required_result':'create local artifact and verify it','source':str(product_path)}
    out=GENERATED/'result_contracts'/f'{pid}_contract.yaml'; write_yaml(out,contract)
    append_jsonl(ROOT/'data'/'result_ledger.jsonl', contract)
    return contract,out
