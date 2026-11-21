import { api } from '../api.js';

// 碎件列：显示与阈值同源的闸检状态与被拒原因
function gateTagHtml(f) {
  const cls = f.gate_status === '合格' ? 'ok' : (f.gate_status === '已拒' ? 'bad' : 'warn');
  const label = f.gate_status === '合格' ? '合格'
    : (f.gate_status === '已拒' ? '闸检拒' : '低于阈值');
  return `<span class="tag ${cls}">${label}</span>`;
}

export async function renderFiles(view, setMsg) {
  const j = await api('/api/files');
  const kb = j.threshold_kb || 256;
  view.innerHTML = `
    <section class="card">
      <h2>小文件清单</h2>
      <p class="muted">登记湖区碎文件；作废后不再进入压实计划。现行阈值 ${kb} KB，低于阈值的碎件不进入合并队列。</p>
      <div class="row">
        <label>路径<input id="path" placeholder="lake/dw_x/part-9.parquet" /></label>
        <label>表名<input id="table" value="dw_orders" /></label>
        <label>字节<input id="size" type="number" value="250000" /></label>
        <button class="primary" id="reg" type="button">登记碎文件</button>
      </div>
    </section>
    <section class="wall" style="margin-top:1rem">
      ${(j.stats || []).map(s => `<article class="card"><h3>${s.table_name}</h3>
        <p>文件 ${s.file_count} · 碎文件 ${s.loose_count}</p>
        <p class="muted">${s.total_bytes} 字节${s.low_count ? ' · 低阈 ' + s.low_count : ''}</p></article>`).join('')}
    </section>
    <section class="wall" style="margin-top:1rem">
      ${(j.items || []).map(f => `<article class="card">
        <h3>${f.path}</h3>
        <span class="tag">${f.status}</span> ${gateTagHtml(f)}
        <p class="muted">${f.table_name} · ${f.size_bytes} 字节</p>
        ${f.reject_reason ? `<p class="err">${f.reject_reason}</p>` : ''}
        <button data-void="${f.id}" type="button" ${f.status==='已合并'?'disabled':''}>作废</button>
      </article>`).join('') || '<p class="muted">暂无文件</p>'}
    </section>`;
  document.getElementById('reg').onclick = async () => {
    try {
      await api('/api/files', { method:'POST', body: JSON.stringify({
        path: document.getElementById('path').value,
        table_name: document.getElementById('table').value,
        size_bytes: Number(document.getElementById('size').value),
      })});
      setMsg('已登记碎文件');
      await renderFiles(view, setMsg);
    } catch (e) { setMsg(e.message, true); }
  };
  view.querySelectorAll('[data-void]').forEach(btn => {
    btn.onclick = async () => {
      try {
        await api('/api/files/' + btn.dataset.void + '/void', { method:'POST', body:'{}' });
        setMsg('已作废');
        await renderFiles(view, setMsg);
      } catch (e) { setMsg(e.message, true); }
    };
  });
}
