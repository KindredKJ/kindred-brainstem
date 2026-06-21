import json
from pathlib import Path
from .hashing import sha256_data
from .time import utc_now
def read_jsonl(path: Path):
    if not path.exists(): return []
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
def append_jsonl(path: Path, record: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    prev = read_jsonl(path)
    rec = dict(record); rec.setdefault('created_at', utc_now()); rec['previous_hash'] = prev[-1].get('record_hash','') if prev else ''
    rec['record_hash'] = sha256_data({k:v for k,v in rec.items() if k!='record_hash'})
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, sort_keys=True, default=str)+'\n')
    return rec
