import uuid
from brainstem.utils.paths import ROOT
from brainstem.utils.jsonl import append_jsonl, read_jsonl
def add(title,tags,summary):
    rec={'memory_id':'mem_'+uuid.uuid4().hex[:8],'title':title,'tags':[t.strip() for t in tags.split(',') if t.strip()] if isinstance(tags,str) else tags,'summary':summary,'status':'stored'}
    return append_jsonl(ROOT/'data'/'associative_memory.jsonl', rec)
def recall(q):
    terms=set(q.lower().split()); out=[]
    for r in read_jsonl(ROOT/'data'/'associative_memory.jsonl'):
        text=' '.join([r.get('title',''),r.get('summary',''),' '.join(r.get('tags',[]))]).lower()
        score=sum(1 for t in terms if t in text)
        if score or any(t in text for t in ['proof','external'] if t in q.lower()): out.append((score,r))
    return [r for _,r in sorted(out,key=lambda x:x[0], reverse=True)]
def link(a,b,reason): return append_jsonl(ROOT/'data'/'associative_links.jsonl', {'memory_a':a,'memory_b':b,'reason':reason})
def all(): return read_jsonl(ROOT/'data'/'associative_memory.jsonl')
