from brainstem.utils.paths import GENERATED, ROOT
from brainstem.utils.jsonl import append_jsonl

def attend(product_id, mode='evidence_first'):
    nodes=[{'type':'audit_missing_evidence','name':'ownership evidence','score':100},{'type':'external_outcome','name':'level 5 evidence','score':90},{'type':'corporate_transition_blocker','name':'professional review','score':85}]
    rec={'product_id':product_id,'mode':mode,'top_node':nodes[0],'nodes':nodes,'next_required_result':nodes[0]['name']}
    append_jsonl(ROOT/'data'/'reality_attention_events.jsonl', rec)
    d=GENERATED/'reality_attention'/'attention_reports'; d.mkdir(parents=True,exist_ok=True)
    (d/f'{product_id}.md').write_text('# Attention Report\n\nTop blocker: ownership evidence.\n\nNext required actions: attach evidence.\n',encoding='utf-8')
    return rec
