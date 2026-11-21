import { api } from '../api.js';

function chipClass(chip) {
  if (!chip) return 'muted';
  if (chip === '闸检已过') return 'ok';
  if (chip.indexOf('全拒') >= 0 || chip.indexOf('失准') >= 0) return 'bad';
  if (chip.indexOf('拦下') >= 0) return 'warn';
  return 'muted';
}

export async function renderSettings(view, setMsg) {
  const j = await api('/api/settings');
  view.innerHTML = `
    <section class="card">
      <h2>台参数</h2>
      <p class="muted">压实阈值与对账模式；保存后立即写库。阈值改动会作用于下一次闸检。</p>
      <div class="wall">
        ${(j.items || []).map(s => `<article class="card">
          <h3>${s.label}</h3>
          <p class="muted">${s.key}</p>
          <input data-key="${s.key}" value="${s.value}" />
          <button data-save="${s.key}" class="primary" type="button">保存</button>
        </article>`).join('')}
      </div>
    </section>`;

  try {
    const dash = await api('/api/gate_bypass/dash');
    const checks = (dash.checks || []).slice(0, 8).map(c =>
      `<p class="muted">计划#${c.plan_id} · ${c.chip} · 阈值 ${c.threshold_kb} KB ·
        合格 ${c.accepted_files} / 拒 ${c.rejected_files} · ${c.created_at}</p>`).join('');
    const rejections = (dash.rejections || []).slice(0, 8).map(r =>
      `<p class="err">${r.path || ('文件#'+r.file_id)} · ${r.reason}</p>`).join('');
    view.innerHTML += `<section class="card" style="margin-top:1rem">
      <h3>闸检凭证</h3>
      <span class="tag ${chipClass(dash.chip)}">${dash.chip}</span>
      <span class="tag ${dash.aligned ? 'ok' : 'bad'}">${dash.aligned ? '芯片与真相一致' : '芯片与真相不一致'}</span>
      <p class="muted">真相 ${dash.truth} · 假绿 ${dash.fake_green}</p>
      ${checks || '<p class="muted">尚无闸检凭证</p>'}
      ${rejections ? '<h3 style="margin-top:.6rem">被拒件</h3>' + rejections : ''}
      <div class="row">
        <button id="note_gate_bypass" type="button">记一笔旁路</button>
        <button id="half_gate_bypass" type="button">对齐四屏</button>
      </div>
    </section>`;
    document.getElementById('note_gate_bypass').onclick = async () => {
      try {
        await api('/api/gate_bypass/note', { method:'POST', body: JSON.stringify({plan_id:1, note:'闸检旁路凭证'}) });
        setMsg('已记旁路凭证');
        await renderSettings(view, setMsg);
      } catch (e) { setMsg(e.message, true); }
    };
    document.getElementById('half_gate_bypass').onclick = async () => {
      try {
        const r = await api('/api/gate_bypass/half', { method:'POST', body:'{}' });
        setMsg('对齐：' + r.panel_chip + ' / ' + r.truth);
        await renderSettings(view, setMsg);
      } catch (e) { setMsg(e.message, true); }
    };
  } catch (e) { /* surface optional */ }
}
