import hashlib, json
def canonical(data): return json.dumps(data, sort_keys=True, default=str, separators=(',', ':'))
def sha256_data(data) -> str: return hashlib.sha256(canonical(data).encode()).hexdigest()
def sha256_text(text: str) -> str: return hashlib.sha256(text.encode()).hexdigest()
