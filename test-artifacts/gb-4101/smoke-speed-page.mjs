// 提速复测页渲染冒烟：极简浏览器桩，验证空数据/含数据/观察员三种状态不抛错
// 运行：node test-artifacts/gb-4101/smoke-speed-page.mjs
import { pathToFileURL } from 'node:url';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const workspaceRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const pagePath = resolve(workspaceRoot, 'frontend/src/pages/speed.js');
const makeEl = () => ({ innerHTML: '', onclick: null, disabled: false, value: '1',
  querySelector: () => makeEl(), querySelectorAll: () => [] });
const listeners = {};
globalThis.location = { hash: '#speed' };
let role = 'operator';
globalThis.localStorage = { getItem: () => JSON.stringify({ role, token: 't', email: 'a@b' }) };
globalThis.document = { querySelector: () => makeEl() };
globalThis.setTimeout = () => 0;
globalThis.fetch = async () => ({ ok: true, json: async () => [] });
const el = makeEl();
const { speedPage } = await import(pathToFileURL(pagePath).href);

await speedPage(el);
if (!el.innerHTML.includes('提速复测')) throw new Error('页面标题缺失');
console.log('空数据渲染 OK，长度', el.innerHTML.length);

globalThis.fetch = async (path) => ({ ok: true, json: async () => {
  if (String(path).includes('/speed-tests')) return [{
    id: 1, batch_id: 5, status: 'faster', elapsed_ms: 2400,
    result: { conclusion: 'faster', basis: '有效样本对 2 个，先后顺序 OC/CO 轮换；原始中位 100ms，候选中位 60ms，中位改善 40.0%。判定提速。作废 1 对：第2对 与普通复核重叠（普通复核 #9）。', valid_pairs: 2, invalid_pairs: 1 },
    rounds: [
      { seq: 0, order: 'OC', first_leg: 'original', status: 'valid', original_ms: 100, candidate_ms: 60, invalid_reason: null, overlap_batch_id: null },
      { seq: 1, order: 'CO', first_leg: 'candidate', status: 'invalid', original_ms: null, candidate_ms: 55, invalid_reason: '与普通复核重叠，样本对作废', overlap_batch_id: 9 },
      { seq: 2, order: 'CO', first_leg: 'candidate', status: 'valid', original_ms: 100, candidate_ms: 60, invalid_reason: null, overlap_batch_id: null }],
    created_at: '2026-11-18 09:10:00', finished_at: '2026-11-18 09:10:15' }];
  if (String(path).includes('/batches')) return [{ id: 5, name: 'shift-1', sample_id: 1, candidate_sql: 'SELECT ...', status: 'passed', created_at: 't' }];
  return [];
} });
await speedPage(el);
for (const needle of ['判定提速', '作废', '先候选后原始', '先原始后候选', '发起复测', '普通复核 #9']) {
  if (!el.innerHTML.includes(needle)) throw new Error('缺少内容：' + needle);
}
console.log('含数据渲染 OK，长度', el.innerHTML.length);

role = 'viewer';
await speedPage(el);
if (!el.innerHTML.includes('观察员仅可查看')) throw new Error('观察员只读提示缺失');
console.log('观察员只读渲染 OK');
console.log('SMOKE_OK');
