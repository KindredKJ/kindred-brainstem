from pathlib import Path
from brainstem.utils.paths import DATA
from brainstem.utils.jsonl import append_jsonl, read_jsonl
PATH = DATA / 'audit_sessions.jsonl'
def append(record): return append_jsonl(PATH, record)
def all(): return read_jsonl(PATH)
