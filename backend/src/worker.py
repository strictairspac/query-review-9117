import time,json,traceback
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from .config.database import Session
from .models.batch import Batch
from .models.sample import Sample
from .models.evidence import Evidence
from .models.speed_test import SpeedTest
from .services.batch import queue
from .services.query_engine import compare,timed_select
from .services import speed_test_core as core
heartbeat=Path('/artifacts/worker.heartbeat')
# 异常情况下的作废上限：超过后即使未满 15 秒也收尾给“证据不足”，避免 worker 空转
MAX_INVALID_PAIRS=8
class _YieldToNormal(Exception):
    """测量中发现普通复核到达：保存半轮作废状态后让出 worker，主循环先处理普通复核。"""
def run_one(batch_id):
    with Session() as db:
        batch=db.get(Batch,batch_id)
        if not batch or db.scalar(select(Evidence).where(Evidence.batch_id==batch_id)):return
        sample=db.get(Sample,batch.sample_id);batch.status='running';db.commit()
        try:
            result=compare(sample.original_sql,batch.candidate_sql)
            batch.status='passed' if result['equivalent'] else 'different'
        except Exception as exc:
            result={'error':str(exc)[:500]};batch.status='failed'
        db.add(Evidence(batch_id=batch_id,result=result));db.commit()
        Path(f'/artifacts/review-{batch_id}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
def normal_pending_ids(db):
    return list(db.scalars(select(Batch.id).where(Batch.status.in_(['queued','running']))))
def run_speed_test(test_id):
    with Session() as db:
        obj=db.get(SpeedTest,test_id)
        if not obj or obj.status not in ('pending','measuring'):return
        batch=db.get(Batch,obj.batch_id)
        if not batch:return
        sample=db.get(Sample,batch.sample_id)
        if not sample:return
        rounds=obj.rounds or []
        # 恢复后先处理被中断截断的半轮：作废后重试，不重复计数
        core.recover_half_rounds(rounds)
        obj.status='measuring';obj.rounds=rounds;db.commit()
        wall_start=time.perf_counter()
        def save():
            # JSON 列原地修改不会被 SQLAlchemy 标记为脏，每次提交写入新的 list 副本
            obj.rounds=[dict(p) for p in rounds];db.commit()
        def measure_leg(pair,kind,sql):
            # 每条腿执行前检查普通复核是否到达：当前半轮作废并让出 worker
            if queue.llen('query-review:jobs')>0 or normal_pending_ids(db):
                waiting=normal_pending_ids(db)
                core.invalidate_pair(pair,'与普通复核重叠，样本对作废',
                                     overlap_batch_id=waiting[0] if waiting else None)
                save();raise _YieldToNormal()
            try:
                ms=timed_select(sql,core.LEG_TIMEOUT_MS)
            except Exception as exc:
                # 超时/执行错误：本对作废，下一对按相同轮换重试，不重复计数
                core.invalidate_pair(pair,'测量超时或执行错误：'+str(exc)[:120]);save();return False
            pair[kind+'_ms']=ms
            save();return True
        try:
            while True:
                wall_ms=(time.perf_counter()-wall_start)*1000
                valid_count=len(core.valid_rounds(rounds))
                invalid_count=len([p for p in rounds if p['status']==core.PAIR_INVALID])
                if invalid_count>=MAX_INVALID_PAIRS:break
                if core.next_step(obj.elapsed_ms or 0,wall_ms,rounds)!='measure':break
                pair=core.new_round(len(rounds),valid_count);rounds.append(pair);save()
                order=pair['order']
                legs=[('original',sample.original_sql),('candidate',batch.candidate_sql)]
                if order==core.ORDER_CANDIDATE_FIRST:legs.reverse()
                leg_start=time.perf_counter();ok=True
                for kind,sql in legs:
                    if not measure_leg(pair,kind,sql):ok=False;break
                if not ok:continue
                pair['status']=core.PAIR_VALID
                obj.elapsed_ms=(obj.elapsed_ms or 0)+round((time.perf_counter()-leg_start)*1000,3)
                save()
                # 一对刚完成但普通复核已在等待：该对与普通复核同处繁忙期，同样作废
                waiting=normal_pending_ids(db)
                if queue.llen('query-review:jobs')>0 or waiting:
                    core.invalidate_pair(pair,'与普通复核重叠，样本对作废',
                                         overlap_batch_id=waiting[0] if waiting else None)
                    save();raise _YieldToNormal()
        except _YieldToNormal:
            # 状态已落库；主循环排空普通复核后，会通过 in_flight 恢复本复测
            return
        conclusion,basis=core.conclude(rounds)
        obj.status=conclusion
        obj.result={'conclusion':conclusion,'basis':basis,
                    'time_budget_ms':core.TIME_BUDGET_MS,
                    'elapsed_ms':obj.elapsed_ms or 0,
                    'valid_pairs':len(core.valid_rounds(rounds)),
                    'invalid_pairs':len([p for p in rounds if p['status']==core.PAIR_INVALID])}
        obj.finished_at=datetime.now();save()
        Path(f'/artifacts/speed-test-{test_id}.json').write_text(
            json.dumps({'speed_test_id':test_id,'batch_id':obj.batch_id,
                        'status':conclusion,'rounds':rounds,'result':obj.result},
                       ensure_ascii=False,indent=2))
def in_flight_speed_tests(db):
    return list(db.scalars(select(SpeedTest.id).where(SpeedTest.status.in_(['pending','measuring']))))
def main():
    while True:
        try:
            heartbeat.write_text(str(time.time()))
            with Session() as db:
                # 1) 普通复核绝对优先
                item=queue.lpop('query-review:jobs')
                if item:
                    run_one(int(item))
                    continue
                pending=normal_pending_ids(db)
                if pending:
                    for ident in pending:run_one(ident)
                    continue
                # 2) 普通队列空闲才处理提速复测
                job=queue.lpop('speed-test:jobs')
                if job:
                    run_speed_test(int(job))
                    continue
                active=in_flight_speed_tests(db)
                if active:
                    for ident in active:run_speed_test(ident)
                    continue
            time.sleep(0.5)
        except Exception:traceback.print_exc();time.sleep(2)
if __name__=='__main__':main()
