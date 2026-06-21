from pathlib import Path
import yaml
def read_yaml(path: Path):
    if not path.exists(): return {}
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {}
def write_yaml(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
