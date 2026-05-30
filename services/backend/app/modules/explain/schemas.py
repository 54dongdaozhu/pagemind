from pydantic import BaseModel


class ExplainDeepRequest(BaseModel):
    keyword: str
    kp_type: str
    context: str
