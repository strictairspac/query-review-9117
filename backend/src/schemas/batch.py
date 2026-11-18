from pydantic import BaseModel,Field
class BatchInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    sample_id:int=Field(gt=0)
    candidate_sql:str=Field(min_length=6,max_length=6000)
