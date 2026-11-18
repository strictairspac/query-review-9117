from sqlalchemy import select
from fastapi import HTTPException
from ..models.evidence import Evidence
def list_evidence(db):return [{'id':x.id,'batch_id':x.batch_id,'result':x.result} for x in db.scalars(select(Evidence).order_by(Evidence.id.desc()))]
def get_evidence(db,batch_id):
    x=db.scalar(select(Evidence).where(Evidence.batch_id==batch_id))
    if not x:raise HTTPException(404,'证据尚未生成，请等待 worker 完成')
    return {'id':x.id,'batch_id':x.batch_id,'result':x.result}
