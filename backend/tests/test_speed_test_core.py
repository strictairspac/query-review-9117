"""提速复测纯逻辑测试，仅依赖标准库：python -m unittest -v tests.test_speed_test_core

覆盖需求验证项：先后偏差（轮换）、复核插队（重叠作废）、半轮重启（不重复计数），
以及 15 秒预算、2 秒普通复核等待上限、最少有效对和 ±10% 结论容差。
"""
import unittest
from src.services import speed_test_core as core


class RotationTests(unittest.TestCase):
    def test_first_round_runs_original_first(self):
        pair = core.new_round(0, 0)
        self.assertEqual(pair['order'], core.ORDER_ORIGINAL_FIRST)
        self.assertEqual(pair['first_leg'], 'original')
        self.assertEqual(pair['status'], core.PAIR_HALF)

    def test_order_alternates_per_valid_pair(self):
        orders = [core.new_round(seq, valid)['order']
                  for seq, valid in enumerate([0, 1, 2, 3])]
        self.assertEqual(orders, ['OC', 'CO', 'OC', 'CO'])

    def test_invalid_pair_does_not_advance_rotation(self):
        # 作废后重试：有效对数不变，新一轮仍是同样先后顺序，且 seq 递增不重复计数
        first = core.new_round(0, 0)
        core.invalidate_pair(first, '与普通复核重叠，样本对作废', overlap_batch_id=7)
        retry = core.new_round(1, 0)
        self.assertEqual(first['order'], retry['order'])
        self.assertEqual(retry['seq'], 1)
        self.assertEqual(core.valid_rounds([first, retry]), [])


class BudgetTests(unittest.TestCase):
    def test_leg_timeout_keeps_normal_review_wait_under_two_seconds(self):
        self.assertLessEqual(core.LEG_TIMEOUT_MS, core.NORMAL_REVIEW_MAX_WAIT_MS)
        self.assertEqual(core.LEG_TIMEOUT_MS, 1200)

    def test_pair_needs_two_legs_inside_budget(self):
        self.assertTrue(core.can_start_pair(0, 0))
        # 剩余预算不足两条 1.2 秒查询时不得再开对
        self.assertFalse(core.can_start_pair(core.TIME_BUDGET_MS - 2 * core.LEG_TIMEOUT_MS + 1, 0))
        self.assertTrue(core.can_start_pair(core.TIME_BUDGET_MS - 2 * core.LEG_TIMEOUT_MS, 0))

    def test_budget_caps_at_fifteen_seconds(self):
        self.assertFalse(core.can_start_pair(core.TIME_BUDGET_MS, 0))

    def test_max_four_valid_pairs(self):
        self.assertFalse(core.can_start_pair(0, core.MAX_VALID_PAIRS))

    def test_hard_deadline_forces_conclusion(self):
        self.assertEqual(core.next_step(0, core.HARD_DEADLINE_MS, []), 'conclude')
        self.assertEqual(core.next_step(0, 0, []), 'measure')


class InterleavingTests(unittest.TestCase):
    def _valid_pair(self, seq, order, original_ms, candidate_ms):
        pair = core.new_round(seq, seq)
        pair['order'] = order
        pair['original_ms'] = original_ms
        pair['candidate_ms'] = candidate_ms
        pair['status'] = core.PAIR_VALID
        return pair

    def test_overlapped_pair_invalidated_and_not_counted(self):
        good = self._valid_pair(0, 'OC', 100, 80)
        overlapped = core.new_round(1, 1)
        overlapped['original_ms'] = 90
        core.invalidate_pair(overlapped, '与普通复核重叠，样本对作废', overlap_batch_id=9)
        rounds = [good, overlapped]
        self.assertEqual(len(core.valid_rounds(rounds)), 1)
        self.assertEqual(overlapped['overlap_batch_id'], 9)
        self.assertEqual(overlapped['status'], core.PAIR_INVALID)

    def test_half_round_restart_invalidates_then_retries_without_double_count(self):
        p1 = self._valid_pair(0, 'OC', 100, 70)
        half = core.new_round(1, 1)  # 第二对应为 CO 先候选
        half['candidate_ms'] = 55   # 只跑完第一条腿就被中断
        rounds = core.recover_half_rounds([p1, half])
        self.assertEqual(rounds[1]['status'], core.PAIR_INVALID)
        self.assertIn('中断重启', rounds[1]['invalid_reason'])
        # 重试：有效对数仍为 1，新对继续按第 2 对的 CO 顺序，不产生重复计数
        retry = core.new_round(2, len(core.valid_rounds(rounds)))
        self.assertEqual(retry['order'], core.ORDER_CANDIDATE_FIRST)
        self.assertEqual(retry['status'], core.PAIR_HALF)

    def test_repeated_interruptions_keep_valid_count_stable(self):
        rounds = [self._valid_pair(0, 'OC', 100, 90)]
        for seq in range(1, 4):
            pair = core.new_round(seq, 1)
            rounds.append(pair)
            core.recover_half_rounds(rounds)
        self.assertEqual(len(core.valid_rounds(rounds)), 1)
        # 有效对的序号和测量值从未被覆盖
        self.assertEqual(rounds[0]['candidate_ms'], 90)


class ConclusionTests(unittest.TestCase):
    def _pairs(self, specs):
        rounds = []
        for seq, (o, c) in enumerate(specs):
            pair = core.new_round(seq, seq)
            pair['original_ms'], pair['candidate_ms'] = o, c
            pair['status'] = core.PAIR_VALID
            rounds.append(pair)
        return rounds

    def test_inconclusive_when_fewer_than_two_valid_pairs(self):
        conclusion, basis = core.conclude([])
        self.assertEqual(conclusion, core.CONCLUSION_INCONCLUSIVE)
        self.assertIn('证据不足', basis)
        one = self._pairs([(100, 10)])
        self.assertEqual(core.conclude(one)[0], core.CONCLUSION_INCONCLUSIVE)

    def test_faster_when_median_gain_beyond_margin(self):
        rounds = self._pairs([(100, 80), (120, 90)])  # 中位改善约 23%
        conclusion, basis = core.conclude(rounds)
        self.assertEqual(conclusion, core.CONCLUSION_FASTER)
        self.assertIn('判定提速', basis)
        self.assertIn('OC/CO', basis)

    def test_no_gain_when_candidate_slower_beyond_margin(self):
        rounds = self._pairs([(100, 130), (100, 140)])
        conclusion, _ = core.conclude(rounds)
        self.assertEqual(conclusion, core.CONCLUSION_NO_GAIN)

    def test_margin_band_is_inconclusive(self):
        rounds = self._pairs([(100, 95), (100, 97)])  # 改善 4% 落在 ±10% 内
        self.assertEqual(core.conclude(rounds)[0], core.CONCLUSION_INCONCLUSIVE)

    def test_basis_records_invalid_pairs(self):
        rounds = self._pairs([(100, 70), (110, 80)])
        bad = core.new_round(2, 2)
        core.invalidate_pair(bad, '与普通复核重叠，样本对作废', overlap_batch_id=3)
        rounds.append(bad)
        conclusion, basis = core.conclude(rounds)
        self.assertEqual(conclusion, core.CONCLUSION_FASTER)
        self.assertIn('作废 1 对', basis)
        self.assertIn('#3', basis)


if __name__ == '__main__':
    unittest.main()
