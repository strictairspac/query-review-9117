from pydantic import BaseModel,Field
class SampleInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    description:str=Field(max_length=2000)
    original_sql:str=Field(min_length=6,max_length=6000)
