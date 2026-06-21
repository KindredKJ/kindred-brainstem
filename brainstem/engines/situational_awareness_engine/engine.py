from brainstem.utils.paths import GENERATED, ROOT
from brainstem.utils.jsonl import append_jsonl

def snapshot():
    rec={'status':'RESULT_AUDIT_REQUIRED','internal_state':'local-first repo','external_state':'no external action taken','next_required_result':'run audit and attach evidence'}
    append_jsonl(ROOT/'data'/'situational_awareness.jsonl', rec)
    d=GENERATED/'situational_awareness'; d.mkdir(parents=True,exist_ok=True)
    (d/'snapshot.md').write_text('# Situational Awareness\n\nNo external launch, tax filing, legal filing, or payment occurred.\n\nNext required actions: gather evidence.\n',encoding='utf-8')
    return rec
