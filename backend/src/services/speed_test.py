from sqlalchemy import select
from fastapi import HTTPException
from ..config.settings import REDIS_URL
from ..models.batch import Batch
from ..models.speed_test import SpeedTest
from redis import Redis
queue=Redis.from_url(REDIS_URL)
SPEED_JOBS_KEY='speed-test:jobs'
ACTIVE_STATUSES=('pending','measuring')
TERMINAL_STATUSES=('faster','no_gain','inconclusive')
def serialize(x):
    return {'id':x.id,'batch_id':x.batch_id,'status':x.status,'rounds':x.rounds or [],
            'result':x.result or {},'elapsed_ms':x.elapsed_ms or 0,
            'created_at':str(x.created_at),'finished_at':str(x.finished_at) if x.finished_at else None}
def list_speed_tests(db,batch_id=None):
    stmt=select(SpeedTest).order_by(SpeedTest.id.desc())
    if batch_id is not None:stmt=stmt.where(SpeedTest.batch_id==batch_id)
    return [serialize(x) for x in db.scalars(stmt)]
def create_speed_test(db,data):
    batch=db.get(Batch,data.batch_id)
    if not batch:raise HTTPException(404,'复核批次不存在')
    # 只有复核通过（结果一致）的批次才能发起提速复测
    if batch.status!='passed':
        raise HTTPException(409,'仅复核通过（结果一致）的批次可发起提速复测，当前状态：'+batch.status)
    # 同一批次只允许一个待测/测量中的复测，保留查询限制
    active=db.scalar(select(SpeedTest).where(
        SpeedTest.batch_id==data.batch_id,SpeedTest.status.in_(ACTIVE_STATUSES)))
    if active:raise HTTPException(409,'该批次已有进行中的提速复测，请等待结论或查看记录')
    obj=SpeedTest(batch_id=data.batch_id,status='pending',rounds=[],result={},elapsed_ms=0)
    db.add(obj);db.commit();db.refresh(obj)
    queue.rpush(SPEED_JOBS_KEY,obj.id)
    return serialize(obj)
