from brainstem.utils.paths import ROOT
from brainstem.utils.jsonl import append_jsonl, read_jsonl
from brainstem.utils.validation import require_founder_review
import uuid
DEFAULT_BIND='127.0.0.1'
def request(action, subject, reason=''):
    rec={'approval_id':'appr_'+uuid.uuid4().hex[:10],'action':action,'subject':subject,'status':'pending','founder':'Kindred Jermaine Cox','reason':reason,'required':require_founder_review(action)}
    return append_jsonl(ROOT/'data'/'founder_approvals.jsonl', rec)
def set_status(aid,status):
    rec={'approval_id':aid,'status':status,'audit_event':'status_change'}; append_jsonl(ROOT/'data'/'founder_approval_audit.jsonl', rec); return rec
def list_requests(): return read_jsonl(ROOT/'data'/'founder_approvals.jsonl')
def blocks(action, approval_id=None):
    if not require_founder_review(action): return False
    matches=[r for r in list_requests() if r.get('approval_id')==approval_id]
    return not matches or matches[-1].get('status')!='approved'
def server_config(bind=DEFAULT_BIND): return {'bind':bind,'internal_only':True,'warning': 'external bind blocked' if bind!='127.0.0.1' else ''}
