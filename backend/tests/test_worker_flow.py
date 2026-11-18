"""worker 端到端流程测试：用 sys.modules 注入假 DB/Redis/查询引擎，验证调度规则。

场景：
 A. 完整复测：成对轮换、15 秒内收尾、结论与依据落库、证据文件写出；
 B. 复核插队：普通复核在测量中到达 → 当前样本对作废并让出 worker → 普通复核先执行 → 恢复后重试不重复计数；
 C. 半轮重启：只跑完一条腿即崩溃，重启后半轮作废、按同一轮换重试；
 D. 主循环优先级：普通复核与复测同时排队，普通复核先被消费。
"""
import os, sys, types, json, tempfile, unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


# ---------- 假 ORM：支持代码里用到的声明式模型与 select(...).where(...) ----------
class Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Entity:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _make_model_class(table, required=()):
    class Model(_Entity):
        _table = table
        _required = required
        def __init__(self, **kw):
            for key in required:
                kw.setdefault(key, None)
            super().__init__(**kw)
    Model.__name__ = table
    return Model


class _Col:
    def __init__(self, name, entity):
        self._name, self._entity = name, entity
    def _match(self, op, value, row):
        actual = getattr(row, self._name)
        if op == 'in':
            return actual in value
        if op == 'eq':
            return actual == value
        raise AssertionError('unsupported operator')
    def in_(self, values):
        return ('cond', self, 'in', values)
    def __eq__(self, value):
        return ('cond', self, 'eq', value)
    def __hash__(self):
        return hash((self._entity._table, self._name))


class FakeSelect:
    def __init__(self, what):
        self.what = what
        self.conds = []
    def where(self, *conds):
        self.conds.extend(conds)
        return self


class FakeDB:
    def __init__(self, store):
        self.store = store
        self.committed = 0
    def _table_of(self, entity):
        return getattr(entity, '_table', None) or entity
    def _all(self, table):
        return self.store.setdefault(table, [])
    def get(self, entity, pk):
        for row in self._all(self._table_of(entity)):
            if getattr(row, 'id', None) == pk:
                return row
        return None
    def add(self, obj):
        table = self._table_of(type(obj))
        rows = self._all(table)
        if getattr(obj, 'id', None) is None:
            obj.id = max([getattr(r, 'id', 0) for r in rows], default=0) + 1
        rows.append(obj)
    def commit(self):
        self.committed += 1
    def _is_model(self, what):
        return hasattr(what, '_table')
    def scalar(self, select_obj):
        rows = self._rows(select_obj)
        return rows[0] if rows else None
    def scalars(self, select_obj):
        return _Scalars(self._rows(select_obj), select_obj.what)
    def _rows(self, select_obj):
        what = select_obj.what
        if self._is_model(what):
            table = what._table
        else:
            table = what._entity._table
        rows = list(self._all(table))
        for _, col, op, value in select_obj.conds:
            rows = [r for r in rows if col._match(op, value, r)]
        if not self._is_model(what):
            rows = [getattr(r, what._name) for r in rows]
        return rows
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class _ModelBase:
    pass


class _Scalars:
    def __init__(self, rows, what):
        self.rows, self.what = rows, what
    def __iter__(self):
        return iter(self.rows)
    def all(self):
        return list(self.rows)
    def first(self):
        return self.rows[0] if self.rows else None


class FakeRedis:
    def __init__(self):
        self.lists = {}
    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(str(value))
    def lpop(self, key):
        return self.lists[key].pop(0) if self.lists.get(key) else None
    def llen(self, key):
        return len(self.lists.get(key, []))
    def ping(self):
        return True


class FakeTime:
    """perf_counter 每次调用前进 300ms，保证 4 对查询约 2.4 秒，落在 15 秒预算内。"""
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []
    def perf_counter(self):
        self.t += 0.3
        return self.t
    def time(self):
        return self.t
    def sleep(self, seconds):
        self.sleeps.append(seconds)


def build_worker_module(tmpdir):
    store = {'users': [], 'samples': [], 'batches': [], 'evidence': [],
             'audit': [], 'speed_tests': []}
    redis = FakeRedis()
    ftime = FakeTime()
    events = []

    def _model(name, cols):
        cls = _make_model_class(name, cols)
        for col in cols:
            setattr(cls, col, _Col(col, cls))
        return cls

    BatchModel = _model('batches', ['id', 'name', 'sample_id', 'candidate_sql', 'status', 'created_at'])
    SampleModel = _model('samples', ['id', 'name', 'description', 'original_sql'])
    EvidenceModel = _model('evidence', ['id', 'batch_id', 'result'])
    SpeedTestModel = _model('speed_tests', ['id', 'batch_id', 'status', 'rounds', 'result',
                                            'elapsed_ms', 'created_at', 'finished_at'])

    sqlalchemy = types.ModuleType('sqlalchemy')
    sqlalchemy.select = lambda *what: FakeSelect(what[0] if len(what) == 1 else what)
    orm = types.ModuleType('sqlalchemy.orm')
    class _Mapped:
        def __getitem__(self, item):
            return None
    orm.Mapped = _Mapped()
    orm.mapped_column = lambda *a, **k: None
    sqlalchemy.orm = orm
    for attr in ('String', 'Text', 'Integer', 'ForeignKey', 'JSON', 'DateTime', 'func'):
        setattr(sqlalchemy, attr, type(attr, (), {'__call__': lambda *a, **k: None,
                                                  'now': staticmethod(lambda: None)})())

    config_db = types.ModuleType('src.config.database')
    config_db.Base = type('Base', (), {})
    config_db.Session = lambda: FakeDB(store)
    config_db.engine = object()

    def model_module(name, cls):
        mod = types.ModuleType(name)
        mod.Base = config_db.Base
        for attr in ('Mapped', 'mapped_column'):
            setattr(mod, attr, getattr(orm, attr))
        mod_name = name.split('.')[-1]
        class_name = ''.join(p.capitalize() for p in mod_name.split('_'))
        setattr(mod, class_name, cls)
        return mod

    modules = {
        'sqlalchemy': sqlalchemy,
        'sqlalchemy.orm': orm,
        'src.config.database': config_db,
        'src.models.batch': model_module('src.models.batch', BatchModel),
        'src.models.sample': model_module('src.models.sample', SampleModel),
        'src.models.evidence': model_module('src.models.evidence', EvidenceModel),
        'src.models.speed_test': model_module('src.models.speed_test', SpeedTestModel),
    }

    batch_service = types.ModuleType('src.services.batch')
    batch_service.queue = redis
    modules['src.services.batch'] = batch_service

    query_engine = types.ModuleType('src.services.query_engine')
    def fake_compare(original, candidate):
        events.append(('compare', original, candidate))
        return {'equivalent': True, 'original': {'row_count': 3}, 'candidate': {'row_count': 3}}
    def make_timed(candidate_ms=60.0, original_ms=100.0):
        def timed_select(sql, timeout_ms):
            assert timeout_ms <= 2000, '普通复核等待不得超过 2 秒'
            ftime.perf_counter()
            ms = original_ms if sql.startswith('SELECT original') else candidate_ms
            events.append(('timed', sql, ms))
            return ms
        return timed_select
    query_engine.compare = fake_compare
    query_engine.timed_select = make_timed()
    modules['src.services.query_engine'] = query_engine

    saved = {k: sys.modules.get(k) for k in list(sys.modules)
             if k in modules or k == 'src' or k.startswith('src.')}
    for name, mod in modules.items():
        sys.modules[name] = mod
    # 清掉可能残留的 src 包与 worker，保证每个用例独立导入
    for stale in [k for k in list(sys.modules) if k == 'src' or k.startswith('src.')]:
        if stale not in modules:
            sys.modules.pop(stale, None)

    import src.worker as worker_mod
    class _FakePath:
        def __init__(self, p):
            self.p = os.path.join(tmpdir, str(p).lstrip('/'))
        def write_text(self, text):
            os.makedirs(os.path.dirname(self.p), exist_ok=True)
            Path(self.p).write_text(text, encoding='utf-8')
        def read_text(self):
            return Path(self.p).read_text(encoding='utf-8')
    worker_mod.Path = _FakePath
    worker_mod.heartbeat = _FakePath('/artifacts/worker.heartbeat')
    worker_mod.time = ftime

    def reset_modules():
        # 本次导入的 src.* 全部弹出，避免污染下一个用例
        for name in [k for k in list(sys.modules) if k == 'src' or k.startswith('src.')]:
            if name not in saved or saved[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved[name]
    return {
        'worker': worker_mod, 'store': store, 'redis': redis, 'time': ftime,
        'events': events, 'models': {
            'Batch': BatchModel, 'Sample': SampleModel, 'Evidence': EvidenceModel,
            'SpeedTest': SpeedTestModel},
        'tmpdir': tmpdir, 'reset': reset_modules,
        # worker 通过 from-import 绑定了名字，必须直接替换 worker 模块上的绑定
        'set_timed': lambda fn: setattr(worker_mod, 'timed_select', fn),
        'make_timed': make_timed,
    }


def seed_passed_batch(store, models):
    store['samples'].append(Row(id=1, name='低温结算汇总', description='d',
                                original_sql='SELECT original FROM invoices'))
    store['batches'].append(Row(id=5, name='shift-1', sample_id=1,
                                candidate_sql='SELECT candidate FROM invoices',
                                status='passed', created_at='2026-11-18 09:00:00'))
    store['speed_tests'].append(Row(id=1, batch_id=5, status='pending',
                                    rounds=[], result={}, elapsed_ms=0,
                                    created_at='2026-11-18 09:10:00', finished_at=None))


class WorkerFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='worker-test-')
        self.ctx = build_worker_module(self.tmp)
        self.addCleanup(self.ctx['reset'])
        seed_passed_batch(self.ctx['store'], self.ctx['models'])

    def _speed_row(self):
        return self.ctx['store']['speed_tests'][0]

    def test_a_full_run_rotates_pairs_and_concludes_faster(self):
        self.ctx['worker'].run_speed_test(1)
        row = self._speed_row()
        self.assertEqual(row.status, 'faster')
        rounds = row.rounds
        self.assertEqual(len([p for p in rounds if p['status'] == 'valid']), 4)
        self.assertEqual([p['order'] for p in rounds], ['OC', 'CO', 'OC', 'CO'])
        self.assertLessEqual(row.elapsed_ms, 15000)
        self.assertIn('判定提速', row.result['basis'])
        self.assertEqual(row.result['valid_pairs'], 4)
        # 证据文件写出，内容与落库一致
        written = json.loads(Path(self.tmp, 'artifacts', 'speed-test-1.json').read_text())
        self.assertEqual(written['status'], 'faster')
        self.assertEqual(written['rounds'], rounds)

    def test_b_normal_review_interrupts_and_pair_invalidated_then_resumed(self):
        worker = self.ctx['worker']
        redis = self.ctx['redis']
        # 前两条腿（第一对）正常；进入第二对第一条腿前让普通复核到达
        original_timed = self.ctx['make_timed']()
        calls = {'n': 0}
        def timed(sql, timeout_ms):
            calls['n'] += 1
            if calls['n'] == 3:
                # 第一对两腿完成后，第二对第一条腿的执行前检查会看到该普通复核
                redis.rpush('query-review:jobs', 9)
                self.ctx['store']['batches'].append(
                    Row(id=9, name='normal-1', sample_id=1,
                        candidate_sql='SELECT x FROM invoices', status='queued',
                        created_at='2026-11-18 09:20:00'))
            return original_timed(sql, timeout_ms)
        self.ctx['set_timed'](timed)

        worker.run_speed_test(1)  # 第二对第一条腿前检测到插队 → 作废并让出
        row = self._speed_row()
        self.assertEqual(row.status, 'measuring')
        invalid = [p for p in row.rounds if p['status'] == 'invalid']
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0]['overlap_batch_id'], 9)
        self.assertEqual(len([p for p in row.rounds if p['status'] == 'valid']), 1)

        # 主循环视角：普通复核先被消费
        self.assertEqual(worker.queue.lpop('query-review:jobs'), '9')
        worker.run_one(9)
        self.assertEqual(self.ctx['store']['batches'][1].status, 'passed')
        self.assertTrue(any(e[0] == 'compare' for e in self.ctx['events']))

        # 普通队列排空后恢复复测：重试不重复计数，最终仍拿到 4 个有效对
        worker.run_speed_test(1)
        row = self._speed_row()
        self.assertEqual(row.status, 'faster')
        self.assertEqual(len([p for p in row.rounds if p['status'] == 'valid']), 4)
        # 作废对的 seq 被跳过，有效对序号不重复
        valid_seqs = [p['seq'] for p in row.rounds if p['status'] == 'valid']
        self.assertEqual(len(valid_seqs), len(set(valid_seqs)))
        self.assertEqual(row.result['invalid_pairs'], 1)

    def test_c_half_round_restart_invalidates_and_retries_same_rotation(self):
        worker = self.ctx['worker']
        # 模拟崩溃前已落库一个半轮：只跑完候选腿
        half = {'seq': 1, 'order': 'CO', 'first_leg': 'candidate', 'status': 'half',
                'original_ms': None, 'candidate_ms': 55.0, 'invalid_reason': None,
                'overlap_batch_id': None}
        first = {'seq': 0, 'order': 'OC', 'first_leg': 'original', 'status': 'valid',
                 'original_ms': 100.0, 'candidate_ms': 60.0, 'invalid_reason': None,
                 'overlap_batch_id': None}
        self._speed_row().rounds = [first, half]
        worker.run_speed_test(1)  # 等同 worker 重启后重启恢复
        row = self._speed_row()
        self.assertEqual(row.rounds[1]['status'], 'invalid')
        self.assertIn('中断重启', row.rounds[1]['invalid_reason'])
        # 重试的第一对仍按“有效对=1”轮换为 CO，未把半轮计入
        retry = row.rounds[2]
        self.assertEqual(retry['order'], 'CO')
        self.assertEqual(row.status, 'faster')
        self.assertEqual(len([p for p in row.rounds if p['status'] == 'valid']), 4)

    def test_d_main_loop_serves_normal_review_before_speed_test(self):
        worker = self.ctx['worker']
        self.ctx['redis'].rpush('query-review:jobs', 9)
        self.ctx['store']['batches'].append(
            Row(id=9, name='normal-2', sample_id=1,
                candidate_sql='SELECT y FROM invoices', status='queued',
                created_at='2026-11-18 09:30:00'))
        self.ctx['redis'].rpush('speed-test:jobs', 1)

        class StopLoop(BaseException):
            pass
        real_run_speed = worker.run_speed_test
        def stop_after_speed(test_id):
            real_run_speed(test_id)
            raise StopLoop
        worker.run_speed_test = stop_after_speed
        try:
            worker.main()
        except StopLoop:
            pass
        # 普通复核的 compare 必须先于复测的 timed 事件
        first_compare = next(i for i, e in enumerate(self.ctx['events']) if e[0] == 'compare')
        first_timed = next(i for i, e in enumerate(self.ctx['events']) if e[0] == 'timed')
        self.assertLess(first_compare, first_timed)
        self.assertEqual(self.ctx['store']['batches'][1].status, 'passed')
        self.assertEqual(self._speed_row().status, 'faster')
        self.assertEqual(self.ctx['redis'].llen('query-review:jobs'), 0)


if __name__ == '__main__':
    unittest.main()
