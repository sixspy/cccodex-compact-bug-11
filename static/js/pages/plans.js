import { api } from '../api.js';

function chipClass(result) {
  if (result === '通过') return 'ok';
  if (result === '全拒' || result === '失准') return 'bad';
  if (result === '拦截') return 'warn';
  return 'muted';
}

export async function renderPlans(view, setMsg) {
  const j = await api('/api/plans');
  view.innerHTML = `
    <section class="card">
      <h2>压实计划</h2>
      <p class="muted">计划卡片上的闸检芯片取自最近一次真实闸检凭证，阈值与被拒件同源。</p>
      <div class="row">
        <label>编号<input id="code" value="CP-NEW-1" /></label>
        <label>标题<input id="title" value="新压实计划" /></label>
        <label>目标表<input id="table" value="dw_payments" /></label>
        <button class="primary" id="create" type="button">创建计划</button>
      </div>
    </section>
    <section class="wall" style="margin-top:1rem">
      ${(j.items || []).map(p => `<article class="card">
        <h3>${p.plan_code}</h3>
        <span class="tag">${p.status}</span>
        <span class="tag ${chipClass(p.gate_result)}">${p.gate_chip || '闸检未跑'}</span>
        <p>${p.title}</p>
        <p class="muted">${p.target_table} · ${p.item_count} 文件 · ${p.plan_bytes} 字节${p.gate_threshold_kb ? ' · 阈值 ' + p.gate_threshold_kb + ' KB' : ''}</p>
        ${p.gate_rejected_count ? `<p class="warn">闸检拒件 ${p.gate_rejected_count} 个（见碎件列原因）</p>` : ''}
        <div class="row">
          <button data-attach="${p.id}" type="button">挂入碎文件</button>
          <button data-pub="${p.id}" class="primary" type="button">发布</button>
          <button data-detail="${p.id}" type="button">详情</button>
        </div>
        <pre class="muted" id="d${p.id}"></pre>
      </article>`).join('') || '<p class="muted">暂无计划</p>'}
    </section>`;
  document.getElementById('create').onclick = async () => {
    try {
      await api('/api/plans', { method:'POST', body: JSON.stringify({
        plan_code: document.getElementById('code').value,
        title: document.getElementById('title').value,
        target_table: document.getElementById('table').value,
      })});
      setMsg('计划已创建');
      await renderPlans(view, setMsg);
    } catch (e) { setMsg(e.message, true); }
  };
  view.querySelectorAll('[data-attach]').forEach(btn => {
    btn.onclick = async () => {
      try {
        const r = await api('/api/plans/' + btn.dataset.attach + '/attach', { method:'POST', body:'{}' });
        setMsg('挂入 ' + r.attached + ' 个碎文件');
        await renderPlans(view, setMsg);
      } catch (e) { setMsg(e.message, true); }
    };
  });
  view.querySelectorAll('[data-pub]').forEach(btn => {
    btn.onclick = async () => {
      try {
        await api('/api/plans/' + btn.dataset.pub + '/publish', { method:'POST', body:'{}' });
        setMsg('已发布');
        await renderPlans(view, setMsg);
      } catch (e) { setMsg(e.message, true); }
    };
  });
  view.querySelectorAll('[data-detail]').forEach(btn => {
    btn.onclick = async () => {
      try {
        const r = await api('/api/plans/' + btn.dataset.detail);
        document.getElementById('d' + btn.dataset.detail).textContent = JSON.stringify(r.items, null, 2);
      } catch (e) { setMsg(e.message, true); }
    };
  });
}
