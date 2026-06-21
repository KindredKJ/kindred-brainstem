SECRET_WORDS=('secret','password','token','api_key','apikey','credential','private_key')
def redact_record(record: dict) -> dict:
    return {k: ('[REDACTED]' if any(w in k.lower() for w in SECRET_WORDS) else v) for k,v in record.items()}
def contains_secret_text(text: str) -> bool: return any(w in text.lower() for w in SECRET_WORDS)
