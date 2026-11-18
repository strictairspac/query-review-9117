ROLES=('admin','operator','viewer')
STATUSES=('queued','running','passed','different','failed')
# 提速复测状态：pending 待测 / measuring 提速测量中（worker 占用）
# / faster 提速 / no_gain 未提速 / inconclusive 证据不足
SPEED_STATUSES=('pending','measuring','faster','no_gain','inconclusive')
# 一轮样本对的状态：valid 有效 / invalid 作废 / half 半轮（只完成一侧，重启后重试）
PAIR_STATUSES=('valid','invalid','half')
