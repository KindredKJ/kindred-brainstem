from pydantic import BaseModel, Field
from typing import Any
class ResultRecord(BaseModel):
    product_id: str; level: int = 0; status: str = 'RESULT_PARTIAL'; next_required_result: str = 'local verification'; evidence_refs: list[str] = Field(default_factory=list); details: dict[str, Any] = Field(default_factory=dict)
