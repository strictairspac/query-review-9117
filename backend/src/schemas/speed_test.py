from pydantic import BaseModel,Field
class SpeedTestInput(BaseModel):
    batch_id:int=Field(gt=0)
