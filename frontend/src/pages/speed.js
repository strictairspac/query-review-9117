import{speedTests}from'../stores/speedTest.js';import{batches}from'../stores/batch.js';import{createSpeedTest}from'../api/speedTest.js';import{header}from'../components/common/header.js';import{table}from'../components/common/table.js';import{esc}from'../utils/html.js';import{notify}from'../hooks/feedback.js';import{session}from'../stores/session.js';import{SPEED_STATUSES,PAIR_STATUSES}from'../constants/enums.js';
const speedBadge=s=>'<span class="badge speed-'+esc(s)+'">'+esc(SPEED_STATUSES[s]||s)+'</span>';
const orderText=o=>o==='CO'?'先候选后原始':'先原始后候选';
export async function speedPage(el){
  const [tests,batchRows]=await Promise.all([speedTests.load(),batches.load()]);
  const batchName=id=>{const b=batchRows.find(x=>x.id===id);return b?('#'+b.id+' '+b.name):('#'+id)};
  const writable=session.get().role!=='viewer';
  const passable=batchRows.filter(b=>b.status==='passed');
  el.innerHTML=header('05','提速复测：成对轮换，十五秒给结论','复核通过后才能发起。每轮原始与候选成对计时并轮换先后；与普通复核重叠或中断截断的样本对作废，恢复后重试不重复计数。普通复核到达时测量最多再等一条查询（不超过 2 秒）。')
  +`<section class="panel"><div class="actions" style="margin-top:0"><h2 style="margin:0">发起提速复测</h2><button id="refresh">刷新</button></div>`
  +(passable.length?`<label>选择复核通过的批次</label><div class="actions" id="start-row"><select id="batch-pick">${passable.map(b=>`<option value="${b.id}">${esc(batchName(b.id))}</option>`).join('')}</select><button class="primary" id="start" ${writable?'':'disabled'}>发起复测 →</button></div>`:'<p class="helper">还没有复核通过（结果一致）的批次。先到 SQL 复核页提交候选并通过复核。</p>')
  +(writable?'':'<p class="helper">观察员仅可查看，不能发起复测。</p>')
  +`<p class="helper">保留查询限制：单条查询 1.2 秒超时，普通复核并发到达时测量多等不超过 2 秒；测量窗口 15 秒，最多 4 个有效样本对，至少 2 个有效对才下结论。中位耗时改善 ≥10% 判提速，反向恶化 ≥10% 判未提速，其间证据不足。</p></section>`
  +`<section class="panel"><h2>复测记录（${tests.length}）</h2>`
  +(tests.length?table(['编号 / 批次','状态','有效/作废对','测量耗时','结论依据','样本对明细'],tests.map(t=>{
    const rounds=t.rounds||[];const valid=rounds.filter(p=>p.status==='valid').length;const invalid=rounds.filter(p=>p.status==='invalid').length;
    const detail=rounds.length?`<details><summary>${rounds.length} 个样本对</summary><div class=tablewrap><table><thead><tr><th>对</th><th>先后</th><th>状态</th><th>原始 ms</th><th>候选 ms</th><th>作废原因</th></tr></thead><tbody>`
      +rounds.map((p,i)=>`<tr><td>${i+1}</td><td>${esc(orderText(p.order))}</td><td>${esc(PAIR_STATUSES[p.status]||p.status)}</td><td>${esc(p.original_ms??'—')}</td><td>${esc(p.candidate_ms??'—')}</td><td>${esc(p.invalid_reason||'')}${p.overlap_batch_id?('（普通复核 #'+p.overlap_batch_id+'）'):''}</td></tr>`).join('')
      +`</tbody></table></div></details>`:'<span class="muted">排队中</span>';
    return ['<span class="mono">#'+t.id+'</span><br>'+esc(batchName(t.batch_id)),speedBadge(t.status),valid+' / '+invalid,(t.elapsed_ms||0)+' ms',esc(t.result?.basis||'测量尚未完成，等待 worker。'),detail]
  })):'<div class="empty">还没有提速复测。上方选择一个复核通过的批次发起。</div>')
  +`</section>`;
  el.querySelector('#refresh').onclick=()=>speedPage(el);
  const startBtn=el.querySelector('#start');
  if(startBtn)startBtn.onclick=()=>{const id=Number(el.querySelector('#batch-pick').value);startBtn.disabled=true;createSpeedTest(id).then(t=>{notify('复测 #'+t.id+' 已进入测量队列，普通复核优先于复测');setTimeout(()=>speedPage(el),600)}).catch(e=>{notify(e.message);startBtn.disabled=false})};
}
