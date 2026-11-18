from sqlalchemy import select
from fastapi import HTTPException
from ..models.sample import Sample
from .query_engine import validate_sql
def serialize(x):return {'id':x.id,'name':x.name,'description':x.description,'original_sql':x.original_sql}
def list_samples(db):return [serialize(x) for x in db.scalars(select(Sample).order_by(Sample.id))]
def create_sample(db,data):
    validate_sql(data.original_sql)
    if db.scalar(select(Sample).where(Sample.name==data.name)):raise HTTPException(409,'样本名称已存在')
    obj=Sample(**data.model_dump());db.add(obj);db.commit();return serialize(obj)
