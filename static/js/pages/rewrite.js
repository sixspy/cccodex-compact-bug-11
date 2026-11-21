import { api } from '../api.js';

function chipClass(chip) {
  if (!chip) return 'muted';
  if (chip === '闸检已过') return 'ok';
  if (chip.indexOf('全拒') >= 0 || chip.indexOf('失准') >= 0) return 'bad';
  if (chip.indexOf('拦下') >= 0) return 'warn';
  return 'muted';
}

export async function renderRewrite(view, setMsg) {
  const plans = await api('/api/plans');
  const jobs = await api('/api/rewrite/jobs');
  const options = (plans.items || []).map(p => `<option value="${p.id}">${p.plan_code} · ${p.status} · ${p.gate_chip || '闸检未跑'}</option>`).join('');
  view.innerHTML = `
    <section class="card">
      <h2>重写合并</h2>
      <p class="muted">对已发布计划启动合并：先过阈值闸，低阈碎件被拒并记入被拒清单，只合并合格件。</p>
      <div class="row">
        <label>计划<select id="pid">${options}</select></label>
        <button class="primary" id="go" type="button">启动合并</button>
        <button id="peek" type="button">看闸检</button>
      </div>
      <div id="gatesum"></div>
    </section>
    <section class="wall" style="margin-top:1rem">
      ${(jobs.items || []).map(j => `<article class="card">
        <h3>${j.plan_code || ('计划#'+j.plan_id)}</h3>
        <span class="tag">${j.status}</span>
        <p class="muted">${j.message}</p>
        <p>合并字节 ${j.merged_bytes}</p>
      </article>`).join('') || '<p class="muted">尚无合并任务</p>'}
    </section>`;

  async function showGate(pid) {
    const box = document.getElementById('gatesum');
    if (!pid) { box.innerHTML = ''; return; }
    const r = await api('/api/plans/' + pid + '/gate');
    const g = r.gate;
    const rows = (g.rejections || []).map(x =>
      `<p class="err">${x.path || ('文件#'+x.file_id)} · ${x.reason}</p>`).join('');
    box.innerHTML = `<div class="row"><span class="tag ${chipClass(g.chip)}">${g.chip}</span>
      <span class="muted">阈值 ${g.threshold_kb} KB · 被拒 ${g.rejected_count}</span></div>
      ${g.message ? `<p class="muted">${g.message}</p>` : ''}${rows}`;
  }

  document.getElementById('peek').onclick = async () => {
    try { await showGate(document.getElementById('pid').value); }
    catch (e) { setMsg(e.message, true); }
  };

  document.getElementById('go').onclick = async () => {
    try {
      const pid = document.getElementById('pid').value;
      const r = await api('/api/rewrite/plans/' + pid + '/start', { method:'POST', body:'{}' });
      setMsg('合并完成 · ' + r.job.status
        + (r.job.rejected_count ? ' · 拒件 ' + r.job.rejected_count : ''));
      await renderRewrite(view, setMsg);
      await showGate(pid);
    } catch (e) { setMsg(e.message, true); await showGate(document.getElementById('pid').value).catch(()=>{}); }
  };

  await showGate(document.getElementById('pid').value).catch(()=>{});
}
