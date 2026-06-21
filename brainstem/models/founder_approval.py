from pydantic import BaseModel, Field
from brainstem.utils.time import utc_now
class ApprovalRequest(BaseModel):
    approval_id: str; action: str; subject: str; status: str='pending'; founder: str='Kindred Jermaine Cox'; reason: str=''; created_at: str=Field(default_factory=utc_now)
