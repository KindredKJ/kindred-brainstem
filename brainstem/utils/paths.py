from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data'
GENERATED = ROOT / 'generated'
CONFIG = ROOT / 'config'
def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True); return path
def rel(path: Path) -> str: return str(path.relative_to(ROOT)) if path.is_absolute() else str(path)
