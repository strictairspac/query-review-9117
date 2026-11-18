from pydantic import BaseModel
class EvidenceOutput(BaseModel):
    id:int
    batch_id:int
    result:dict
