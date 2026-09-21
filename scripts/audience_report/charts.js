// Chart helpers for the audience report. Reads window.REPORT (set by audience_report.py).
(function(){
  const R = window.REPORT || {};
  const NS = 'http://www.w3.org/2000/svg';
  function el(n, a, txt){ const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); if (txt != null) e.textContent = txt; return e; }
  function fmt(v){ return (Math.round(v * 10) / 10).toLocaleString('en-US'); }

  // Horizontal bars. rows: [{label, value, sub}]
  function hbars(id, rows, cls, unit, opts){
    const host = document.getElementById(id); if (!host) return;
    if (!rows || !rows.length){ host.innerHTML = '<p class="note">No data yet.</p>'; return; }
    opts = opts || {}; const W = 560, rowH = 26, labW = opts.labW || 262, top = 4;
    const H = top + rows.length * rowH + 4; const max = Math.max.apply(null, rows.map(r => r.value)) || 1;
    const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': opts.aria || ''});
    const x0 = labW + 8, xw = W - x0 - 50;
    rows.forEach((r, i) => {
      const y = top + i * rowH; const w = Math.max(4, r.value / max * xw);
      const lab = r.label.length > 44 ? r.label.slice(0, 43) + '…' : r.label;
      svg.appendChild(el('text', {x: labW, y: y + 17, 'text-anchor': 'end', class: 'lbl'}, lab));
      svg.appendChild(el('rect', {x: x0, y: y + 5, width: w, height: rowH - 10, rx: 4, class: 'bar ' + (cls || '')}));
      let v = fmt(r.value) + (unit || '');
      if (r.sub && w < xw * 0.55) v += '  · ' + r.sub;
      svg.appendChild(el('text', {x: x0 + w + 6, y: y + 17, class: 'val'}, v));
    });
    svg.appendChild(el('line', {x1: x0, y1: top, x2: x0, y2: H - 4, class: 'axis'}));
    host.appendChild(svg);
  }

  // Daily line chart. data: [[label, value], ...]
  function line(id, data){
    const host = document.getElementById(id); if (!host) return;
    if (!data || data.length < 2){ host.innerHTML = '<p class="note">No data yet.</p>'; return; }
    const W = 900, H = 240, L = 36, Rm = 16, T = 14, B = 34;
    const rawMax = Math.max.apply(null, data.map(p => p[1])) || 1;
    const step = rawMax <= 10 ? 2 : rawMax <= 30 ? 6 : rawMax <= 60 ? 12 : Math.ceil(rawMax / 5 / 10) * 10;
    const max = Math.max(step, Math.ceil(rawMax / step) * step);
    const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Downloads per day'});
    const xs = i => L + i * (W - L - Rm) / (data.length - 1), ys = v => T + (H - T - B) * (1 - v / max);
    for (let v = 0; v <= max; v += step){ svg.appendChild(el('line', {x1: L, y1: ys(v), x2: W - Rm, y2: ys(v), class: 'grid'})); svg.appendChild(el('text', {x: L - 8, y: ys(v) + 4, 'text-anchor': 'end'}, v)); }
    let d = 'M' + xs(0) + ',' + ys(data[0][1]); data.forEach((p, i) => { if (i) d += ' L' + xs(i) + ',' + ys(p[1]); });
    svg.appendChild(el('path', {d: d + ' L' + xs(data.length - 1) + ',' + ys(0) + ' L' + xs(0) + ',' + ys(0) + ' Z', class: 'area'}));
    svg.appendChild(el('path', {d: d, class: 'line'}));
    const every = Math.max(1, Math.ceil(data.length / 12));
    data.forEach((p, i) => { if (i % every === 0 || i === data.length - 1) svg.appendChild(el('text', {x: xs(i), y: H - 10, 'text-anchor': 'middle'}, p[0])); });
    data.forEach((p, i) => { svg.appendChild(el('circle', {cx: xs(i), cy: ys(p[1]), r: 3, class: 'pt' + (i === data.length - 1 ? ' end' : '')})); });
    host.appendChild(svg);
  }

  // Grouped bars (views vs minutes) by country. rows: [[label, views, minutes], ...]
  function grouped(id, rows){
    const host = document.getElementById(id); if (!host) return;
    if (!rows || !rows.length){ host.innerHTML = '<p class="note">No data yet.</p>'; return; }
    const W = 560, rowH = 54, labW = 150, top = 4, H = top + rows.length * rowH + 4;
    const max = Math.max.apply(null, rows.map(r => Math.max(r[1], r[2]))) || 1; const x0 = labW + 8, xw = W - x0 - 60;
    const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'YouTube views and minutes by country'});
    rows.forEach((r, i) => { const y = top + i * rowH;
      svg.appendChild(el('text', {x: labW, y: y + 29, 'text-anchor': 'end', class: 'lbl'}, r[0]));
      const w1 = Math.max(4, r[1] / max * xw), w2 = Math.max(4, r[2] / max * xw);
      svg.appendChild(el('rect', {x: x0, y: y + 7, width: w1, height: 18, rx: 4, class: 'bar rose'}));
      svg.appendChild(el('rect', {x: x0, y: y + 29, width: w2, height: 18, rx: 4, class: 'bar gold'}));
      svg.appendChild(el('text', {x: x0 + w1 + 6, y: y + 20, class: 'val'}, fmt(r[1]) + ' views'));
      svg.appendChild(el('text', {x: x0 + w2 + 6, y: y + 42, class: 'val'}, fmt(r[2]) + ' min'));
    });
    svg.appendChild(el('line', {x1: x0, y1: top, x2: x0, y2: H - 4, class: 'axis'}));
    host.appendChild(svg);
  }

  function chips(id, rows){
    const host = document.getElementById(id); if (!host || !rows) return;
    rows.forEach(p => { const s = document.createElement('span'); s.className = 'chip'; const b = document.createElement('b'); b.textContent = p[1]; s.appendChild(b); s.appendChild(document.createTextNode(' ' + p[0])); host.appendChild(s); });
  }

  (R.hbars || []).forEach(c => hbars(c.id, c.rows, c.cls, c.unit, c.opts));
  if (R.daily) line('c-days', R.daily);
  if (R.ytgeo) grouped('c-geo-yt', R.ytgeo);
  if (R.prchips) chips('pr-chips', R.prchips);
})();
