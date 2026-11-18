"""Strict read-only bounded SQL execution against a single seeded business table."""
import json,hashlib,time
from collections import Counter
import sqlglot
from sqlglot import exp
from sqlalchemy import text
from ..config.database import engine
ALLOWED_FUNCTIONS={'SUM','COUNT','AVG','MIN','MAX','ROUND','COALESCE','CAST'}
ALLOWED_COLUMNS={'customer','route','amount','temperature','invoice_id','status'}
def validate_sql(sql):
    try: trees=sqlglot.parse(sql,read='postgres')
    except Exception as exc: raise ValueError('SQL 无法解析：'+str(exc)[:180])
    if len(trees)!=1 or not isinstance(trees[0],exp.Select): raise ValueError('只允许单条 SELECT')
    tree=trees[0]
    if tree.args.get('into') or tree.args.get('locks') or tree.find(exp.With): raise ValueError('不允许 INTO、锁或 CTE')
    tables=list(tree.find_all(exp.Table))
    if not tables or any(t.name!='invoices' or t.db or t.catalog for t in tables): raise ValueError('只允许访问 invoices 表')
    for col in tree.find_all(exp.Column):
        if col.name not in ALLOWED_COLUMNS and col.name!='*': raise ValueError('未知业务字段：'+col.name)
    for f in tree.find_all(exp.Func):
        if f.sql_name() not in ALLOWED_FUNCTIONS: raise ValueError('不允许函数：'+f.sql_name())
    if len(list(tree.walk()))>250: raise ValueError('SQL 结构过大')
    return tree.sql(dialect='postgres')
def execute_query(sql):
    sql=validate_sql(sql)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text("SET LOCAL statement_timeout='2500ms'"))
            conn.execute(text('SET LOCAL ROLE query_reader'))
            plan=conn.execute(text('EXPLAIN (ANALYZE, FORMAT JSON, BUFFERS) '+sql)).scalar()
            started=time.perf_counter()
            cursor=conn.execute(text(sql)); columns=list(cursor.keys()); rows=cursor.fetchmany(1001)
            if len(rows)>1000: raise ValueError('结果超过 1000 行，请聚合或 LIMIT')
            rows=[[str(v) if v is not None else None for v in row] for row in rows]
            return {'columns':columns,'rows':rows,'row_count':len(rows),'elapsed_ms':round((time.perf_counter()-started)*1000,3),'plan':plan}
def compare(original,candidate):
    left=execute_query(original);right=execute_query(candidate)
    canon=lambda data:Counter(json.dumps(row,ensure_ascii=False) for row in data['rows'])
    a,b=canon(left),canon(right)
    equivalent=len(left['columns'])==len(right['columns']) and a==b
    digest=lambda x:hashlib.sha256(json.dumps(sorted(canon(x).items()),ensure_ascii=False).encode()).hexdigest()
    return {'equivalent':equivalent,'comparison':'忽略行顺序、保留重复行；按输出列位置比较，数字按数据库文本表示','original':left,'candidate':right,'original_checksum':digest(left),'candidate_checksum':digest(right),'missing_rows':list((a-b).elements())[:10],'extra_rows':list((b-a).elements())[:10],'note':'执行时间受缓存与机器负载影响；不据一次耗时断言优化收益'}
