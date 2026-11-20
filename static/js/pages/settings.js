import { api } from '../api.js';

export async function renderSettings(view, setMsg) {
  const j = await api('/api/settings');
  view.innerHTML = `
    <section class="card">
      <h2>台参数</h2>
      <p class="muted">压实阈值与对账模式；保存后立即写库。</p>
      <div class="wall">
        ${(j.items || []).map(s => `<article class="card">
          <h3>${s.label}</h3>
          <p class="muted">${s.key}</p>
          <input data-key="${s.key}" value="${s.value}" />
          <button data-save="${s.key}" class="primary" type="button">保存</button>
        </article>`).join('')}
      </div>
    </section>`;
  view.querySelectorAll('[data-save]').forEach(btn => {
    btn.onclick = async () => {
      try {
        const key = btn.dataset.save;
        const input = view.querySelector('input[data-key="'+key+'"]');
        await api('/api/settings', { method:'POST', body: JSON.stringify({ key, value: input.value }) });
        setMsg('已保存 ' + key);
        await renderSettings(view, setMsg);
      } catch (e) { setMsg(e.message, true); }
    };
  });

  try {
    const dash = await api('/api/gate_bypass/dash');
    view.innerHTML += `<section class="card" style="margin-top:1rem">
      <h3>闸检绕过旁路</h3>
      <span class="tag">${dash.chip}</span>
      <p class="muted">真相 ${dash.truth} · 假绿 ${dash.fake_green}</p>
      <div class="row">
        <button id="note_gate_bypass" type="button">记一笔</button>
        <button id="half_gate_bypass" type="button">半修对齐</button>
      </div>
    </section>`;
    document.getElementById('note_gate_bypass').onclick = async () => {
      try {
        await api('/api/gate_bypass/note', { method:'POST', body: JSON.stringify({plan_id:1, note:'闸检绕过'}) });
        setMsg('已记旁路');
        await renderSettings(view, setMsg);
      } catch (e) { setMsg(e.message, true); }
    };
    document.getElementById('half_gate_bypass').onclick = async () => {
      try {
        const r = await api('/api/gate_bypass/half', { method:'POST', body:'{}' });
        setMsg('半修 ' + r.panel_chip + ' / ' + r.truth);
        await renderSettings(view, setMsg);
      } catch (e) { setMsg(e.message, true); }
    };
  } catch (e) { /* surface optional */ }

}
