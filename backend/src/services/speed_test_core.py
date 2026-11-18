"""提速复测的纯判定逻辑：成对轮换、15 秒预算、作废与结论。

本模块不导入任何第三方库，可在没有数据库/Redis 的环境下直接用 unittest 验证。
worker 负责实际执行 SQL 并把这里产生的决策落库。
"""
from statistics import median

# 一次复测必须在 15 秒测量时间内给出结论（仅统计实际测量耗时，不含被普通复核插队的等待）
TIME_BUDGET_MS = 15000
# 进程异常等极端情况下的墙钟兜底，避免复测无限占用 worker
HARD_DEADLINE_MS = 60000
# 单条查询超时；普通复核并发到达时，测量中的 worker 最多等这一条查询结束，必须 <= 2 秒
LEG_TIMEOUT_MS = 1200
NORMAL_REVIEW_MAX_WAIT_MS = 2000
# 最多采集 4 个有效样本对，少于 2 个有效对则证据不足
MAX_VALID_PAIRS = 4
MIN_VALID_PAIRS = 2
# 中位耗时改善达到 10% 才判定提速，反向恶化 10% 判未提速，其间视为证据不足
SPEED_MARGIN = 0.10

ORDER_ORIGINAL_FIRST = 'OC'   # 先原始后候选
ORDER_CANDIDATE_FIRST = 'CO'  # 先候选后原始

PAIR_VALID = 'valid'
PAIR_INVALID = 'invalid'
PAIR_HALF = 'half'

CONCLUSION_FASTER = 'faster'
CONCLUSION_NO_GAIN = 'no_gain'
CONCLUSION_INCONCLUSIVE = 'inconclusive'

assert LEG_TIMEOUT_MS <= NORMAL_REVIEW_MAX_WAIT_MS, '测量单腿超时不得超过普通复核 2 秒等待上限'


def new_round(seq, valid_pairs):
    """按已完成的有效对数轮换先后：作废/半轮不推进轮换，重试不重复计数。"""
    order = ORDER_ORIGINAL_FIRST if valid_pairs % 2 == 0 else ORDER_CANDIDATE_FIRST
    return {
        'seq': seq,
        'order': order,
        'first_leg': 'original' if order == ORDER_ORIGINAL_FIRST else 'candidate',
        'status': PAIR_HALF,
        'original_ms': None,
        'candidate_ms': None,
        'invalid_reason': None,
        'overlap_batch_id': None,
    }


def can_start_pair(elapsed_ms, valid_pairs):
    """15 秒预算内能否再开一对：必须留得下两条各 1.2 秒的查询。"""
    if valid_pairs >= MAX_VALID_PAIRS:
        return False
    if elapsed_ms >= TIME_BUDGET_MS:
        return False
    return TIME_BUDGET_MS - elapsed_ms >= 2 * LEG_TIMEOUT_MS


def invalidate_pair(pair, reason, overlap_batch_id=None):
    """把一个样本对标记作废（与普通复核重叠、中断重启、超时、执行错误）。"""
    pair['status'] = PAIR_INVALID
    pair['invalid_reason'] = reason
    pair['overlap_batch_id'] = overlap_batch_id
    return pair


def recover_half_rounds(rounds):
    """worker 重启恢复：被中断截断的半轮一律作废，随后按有效对数重新轮换重试。"""
    recovered = []
    for pair in rounds:
        if pair.get('status') == PAIR_HALF:
            invalidate_pair(pair, 'worker 中断重启，半轮样本对作废后重试')
        recovered.append(pair)
    return recovered


def valid_rounds(rounds):
    return [p for p in rounds if p.get('status') == PAIR_VALID
            and p.get('original_ms') is not None and p.get('candidate_ms') is not None]


def conclude(rounds):
    """根据有效样本对给出 faster / no_gain / inconclusive 及依据。"""
    valid = valid_rounds(rounds)
    invalid = [p for p in rounds if p.get('status') == PAIR_INVALID]
    if len(valid) < MIN_VALID_PAIRS:
        return CONCLUSION_INCONCLUSIVE, (
            f'有效样本对仅 {len(valid)} 个（至少需要 {MIN_VALID_PAIRS} 个），'
            f'15 秒测量窗口内证据不足，可重新发起复测。')
    med_original = round(median(p['original_ms'] for p in valid), 3)
    med_candidate = round(median(p['candidate_ms'] for p in valid), 3)
    gain = (med_original - med_candidate) / med_original if med_original else 0.0
    orders = '/'.join(p['order'] for p in valid)
    detail = '；'.join(
        f"第{p['seq'] + 1}对({p['order']}) 原始 {p['original_ms']}ms / 候选 {p['candidate_ms']}ms"
        for p in valid)
    head = (f'有效样本对 {len(valid)} 个，先后顺序 {orders} 轮换；'
            f'原始中位 {med_original}ms，候选中位 {med_candidate}ms，'
            f'中位改善 {gain * 100:.1f}%（容差 ±{int(SPEED_MARGIN * 100)}%）。{detail}。')
    if invalid:
        head += ' 作废 ' + str(len(invalid)) + ' 对：' + '；'.join(
            (f"第{p['seq'] + 1}对 {p.get('invalid_reason') or '规则作废'}"
             + (f"（普通复核 #{p['overlap_batch_id']}）" if p.get('overlap_batch_id') else ''))
            for p in invalid) + '。'
    if gain >= SPEED_MARGIN:
        return CONCLUSION_FASTER, head + ' 改善达到容差下限，判定提速。'
    if gain <= -SPEED_MARGIN:
        return CONCLUSION_NO_GAIN, head + ' 候选中位反而更慢且超过容差，判定未提速。'
    return CONCLUSION_INCONCLUSIVE, head + ' 差异落在容差区间内，证据不足。'


def next_step(elapsed_ms, wall_ms, rounds):
    """汇总决策：继续测量 / 收尾给结论。"""
    valid = valid_rounds(rounds)
    if wall_ms >= HARD_DEADLINE_MS:
        return 'conclude'
    if can_start_pair(elapsed_ms, len(valid)):
        return 'measure'
    return 'conclude'
