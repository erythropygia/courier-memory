/* Küçük SVG grafikleri (Sahne 6–7): çizgi + güven bandı, şelale, aralık şeridi.
   Kurallar (dataviz): 2px çizgi, bant %10 dolgu, ince ızgara, ≥ 2 seride lejant + seçici doğrudan etiket,
   yazı mürekkep renginde (seri renginde değil), her grafikte üzerine gelince ipucu ve "Tablo" görünümü.
   Kol renkleri ui/ ile aynı doğrulanmış yuvalar (A #eda100, B #1baf7a, C #eb6834, D #2a78d6; zemin #FBF8F2'de geçti). */
(function (CM) {
  CM.ARM = { A: '#eda100', B: '#1baf7a', C: '#eb6834', D: '#2a78d6' };
  CM.GRAY = '#8A8177';
  const NS = 'http://www.w3.org/2000/svg';
  const GRID = 'rgba(26,23,20,0.10)', AXIS = 'rgba(26,23,20,0.28)';

  function svg(w, h) {
    const s = document.createElementNS(NS, 'svg');
    s.setAttribute('viewBox', `0 0 ${w} ${h}`);
    s.setAttribute('width', w); s.setAttribute('height', h);
    return s;
  }
  function el(name, at, parent) {
    const e = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(at || {})) if (v != null) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(t, at, parent) { const e = el('text', at, parent); e.textContent = t; return e; }
  // temiz tikler
  function ticks(min, max, n = 5) {
    const ham = (max - min) / n, us = Math.pow(10, Math.floor(Math.log10(ham)));
    const step = [1, 2, 2.5, 5, 10].map((k) => k * us).find((k) => k >= ham) || ham;
    const out = [];
    for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(6));
    return out;
  }
  CM.ticks = ticks;

  // ------------------------------------------------------------ ortak kabuk: başlık, lejant, Tablo düğmesi, ipucu
  let hint = null;
  function showHint(html, x, y) {
    if (!hint) { hint = document.createElement('div'); hint.id = 'chart-hint'; document.body.appendChild(hint); }
    hint.innerHTML = html;
    hint.style.display = 'block';
    const r = hint.getBoundingClientRect();
    hint.style.left = Math.min(innerWidth - r.width - 12, x + 16) + 'px';
    hint.style.top = Math.max(8, y - r.height - 12) + 'px';
  }
  function hideHint() { if (hint) hint.style.display = 'none'; }
  CM.hideHint = hideHint;
  const key = (color, type = 'line') => `<i class="key ${type}" style="background:${color}"></i>`;

  /* kap: konteyner; o: {baslik, alt, lejant:[{ad, renk, tur}], tablo:{basliklar, satirlar}} → {govde} */
  CM.chartShell = function (container, o) {
    container.innerHTML = '';
    container.classList.add('chart');
    const head = document.createElement('div');
    head.className = 'g-head';
    head.innerHTML = `<div><div class="g-title">${o.title || ''}</div>${o.alt ? `<div class="g-alt">${o.alt}</div>` : ''}</div>` +
      `<div class="g-right">${(o.legend || []).map((l) => `<span class="leg">${key(l.color, l.type)}${l.name}</span>`).join('')}` +
      (o.table ? '<button class="g-table" type="button">Tablo</button>' : '') + '</div>';
    const body = document.createElement('div');
    body.className = 'g-body';
    container.append(head, body);
    if (o.table) {
      const t = document.createElement('div');
      t.className = 'g-table-view';
      t.hidden = true;
      t.innerHTML = `<table><thead><tr>${o.table.titles.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>` +
        o.table.rows.map((r) => `<tr>${r.map((c, i) => `<td${i ? ' class="s"' : ''}>${c}</td>`).join('')}</tr>`).join('') + '</tbody></table>';
      container.appendChild(t);
      const b = head.querySelector('.g-table');
      b.onclick = () => { const open = t.hidden; t.hidden = !open; body.hidden = open; b.classList.toggle('active', open); };
    }
    return { body };
  };

  /* Çizgi + bant. o: {seriler:[{ad, renk, noktalar:[{x, y, alt?, ust?}], etiket?}], x:{ad, bicim}, y:{ad, bicim, min?, max?},
     cizgiler:[{y, ad}] (yatay başvuru), hintX: (x) => başlık} */
  CM.lineChart = function (body, o) {
    const W = body.clientWidth || 800, H = body.clientHeight || 400;
    const m = { l: 58, r: 150, t: 14, b: 46 };
    const s = svg(W, H);
    const xs = o.series.flatMap((q) => q.points.map((p) => p.x));
    const ys = o.series.flatMap((q) => q.points.flatMap((p) => [p.y, p.alt ?? p.y, p.top ?? p.y]));
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    const y0 = o.y.min ?? 0, y1 = o.y.max ?? Math.max(...ys) * 1.08;
    const X = (v) => m.l + ((v - x0) / (x1 - x0)) * (W - m.l - m.r);
    const Y = (v) => H - m.b - ((v - y0) / (y1 - y0)) * (H - m.t - m.b);
    const fmtY = o.y.format || ((v) => CM.count(v, 0)), fmtX = o.x.format || ((v) => v);
    for (const v of ticks(y0, y1, 4)) {
      el('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: GRID, 'stroke-width': 1 }, s);
      text(fmtY(v), { x: m.l - 10, y: Y(v) + 5, 'text-anchor': 'end', class: 'tick' }, s);
    }
    for (const v of ticks(x0, x1, Math.min(8, x1 - x0)).filter((v) => Number.isInteger(v))) text(fmtX(v), { x: X(v), y: H - m.b + 22, 'text-anchor': 'middle', class: 'tick' }, s);
    el('line', { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: AXIS, 'stroke-width': 1 }, s);
    if (o.x.name) text(o.x.name, { x: (m.l + W - m.r) / 2, y: H - 6, 'text-anchor': 'middle', class: 'axis-name' }, s);
    for (const c of o.lines || []) {
      el('line', { x1: m.l, x2: W - m.r, y1: Y(c.y), y2: Y(c.y), stroke: 'rgba(26,23,20,0.45)', 'stroke-width': 1 }, s);
      text(c.name, { x: W - m.r + 8, y: Y(c.y) + 4, class: 'line-name' }, s);
    }
    const groups = [];
    for (const q of o.series) {
      const g = el('g', { class: 'series', opacity: 1 }, s);
      const band = q.points.filter((p) => p.alt != null);
      if (band.length) {
        const d = band.map((p, i) => `${i ? 'L' : 'M'}${X(p.x)},${Y(p.top)}`).join('') + band.slice().reverse().map((p) => `L${X(p.x)},${Y(p.alt)}`).join('') + 'Z';
        el('path', { d, fill: q.color, 'fill-opacity': 0.1 }, g);
      }
      const d = q.points.map((p, i) => `${i ? 'L' : 'M'}${X(p.x)},${Y(p.y)}`).join('');
      const path = el('path', { d, fill: 'none', stroke: q.color, 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, g);
      const last = q.points[q.points.length - 1];
      el('circle', { cx: X(last.x), cy: Y(last.y), r: 4.5, fill: q.color, stroke: '#FBF8F2', 'stroke-width': 2 }, g);
      groups.push({ q, g, path, lastY: Y(last.y) });
    }
    // uç etiketleri: çakışırsa aşağı it (bağlantı çizgisiyle)
    const order = groups.slice().sort((a, b) => a.lastY - b.lastY);
    let last = -1e9;
    for (const k of order) {
      const y = Math.max(k.lastY, last + 20);
      last = y;
      const xe = W - m.r + 10;
      if (Math.abs(y - k.lastY) > 2) el('line', { x1: X(x1) + 5, y1: k.lastY, x2: xe - 2, y2: y - 4, stroke: AXIS, 'stroke-width': 1 }, s);
      text(k.q.label || k.q.name, { x: xe, y: y, class: 'end-name' }, s);
    }
    // ipucu: dikey artı imleci, en yakın x
    const cursor = el('line', { y1: m.t, y2: H - m.b, stroke: AXIS, 'stroke-width': 1, opacity: 0 }, s);
    const area = el('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent' }, s);
    area.addEventListener('mousemove', (ev) => {
      const r = s.getBoundingClientRect(), px = ((ev.clientX - r.left) / r.width) * W;
      const xv = Math.round(x0 + ((px - m.l) / (W - m.l - m.r)) * (x1 - x0));
      cursor.setAttribute('x1', X(xv)); cursor.setAttribute('x2', X(xv)); cursor.setAttribute('opacity', 1);
      const row = o.series.map((q) => {
        const p = q.points.find((n) => n.x === xv);
        return p ? `<div>${key(q.color)}${q.name} <b>${fmtY(p.y)}</b>${p.alt != null ? ` <span>[${fmtY(p.alt)}–${fmtY(p.top)}]</span>` : ''}</div>` : '';
      }).join('');
      showHint(`<div class="ib">${o.hintX ? o.hintX(xv) : fmtX(xv)}</div>${row}`, ev.clientX, ev.clientY);
    });
    area.addEventListener('mouseleave', () => { cursor.setAttribute('opacity', 0); hideHint(); });
    body.innerHTML = '';
    body.appendChild(s);
    // çizim animasyonu
    for (const k of groups) {
      const L = k.path.getTotalLength();
      k.path.style.strokeDasharray = L; k.path.style.strokeDashoffset = L;
      k.path.getBoundingClientRect();
      k.path.style.transition = 'stroke-dashoffset 1400ms cubic-bezier(.4,0,.2,1)';
      k.path.style.strokeDashoffset = 0;
    }
    return { svg: s, X, Y, groups };
  };

  /* Şelale. adimlar: [{ad, deger (TL/gün), tur: baslangic|azalis|artis|sonuc}] */
  CM.waterfallChart = function (body, steps, { format = (v) => CM.count(v) } = {}) {
    const W = body.clientWidth || 900, H = body.clientHeight || 380;
    const m = { l: 70, r: 16, t: 34, b: 74 };
    const s = svg(W, H);
    let cum = 0;
    const box = steps.map((a) => {
      let alt, top;
      if (a.type === 'start' || a.type === 'result') { alt = 0; top = a.value; cum = a.value; }
      else { const y = cum + a.value; alt = Math.min(cum, y); top = Math.max(cum, y); cum = y; }
      return { ...a, alt, top };
    });
    const ymax = Math.max(...box.map((k) => k.top)) * 1.06;
    const Y = (v) => H - m.b - (v / ymax) * (H - m.t - m.b);
    const bw = (W - m.l - m.r) / steps.length, cw = Math.min(110, bw * 0.56);
    for (const v of ticks(0, ymax, 4)) {
      el('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: GRID }, s);
      text(CM.count(v / 1000) + ' bin', { x: m.l - 10, y: Y(v) + 5, 'text-anchor': 'end', class: 'tick' }, s);
    }
    const COLOR = { start: '#1A1714', result: '#1A1714', decrease: '#2C7A4B', increase: '#D2261C' };
    box.forEach((k, i) => {
      const x = m.l + i * bw + (bw - cw) / 2, y = Y(k.top), h = Math.max(2, Y(k.alt) - Y(k.top));
      const r = el('path', { d: round(x, y, cw, h, 4, k.type === 'start' || k.type === 'result' || k.type === 'increase'), fill: COLOR[k.type] }, s);
      r.classList.add('column');
      r.style.transitionDelay = i * 160 + 'ms';
      if (i < box.length - 1) {
        const next = k.type === 'start' ? k.top : k.value >= 0 ? k.top : k.alt;
        el('line', { x1: x + cw, x2: x + bw, y1: Y(k.type === 'start' || k.type === 'result' ? k.top : next), y2: Y(k.type === 'start' || k.type === 'result' ? k.top : next), stroke: AXIS }, s);
      }
      const label = k.type === 'start' || k.type === 'result' ? format(k.value) : (k.value > 0 ? '+' : '−') + format(Math.abs(k.value));
      text(label, { x: x + cw / 2, y: y - 9, 'text-anchor': 'middle', class: 'value' + (k.type === 'increase' ? ' red' : '') }, s);
      const rows = k.name.split('\n');
      rows.forEach((t, j) => text(t, { x: x + cw / 2, y: H - m.b + 22 + j * 17, 'text-anchor': 'middle', class: 'times' + (j ? ' secondary' : '') }, s));
      const hit = el('rect', { x: m.l + i * bw, y: m.t, width: bw, height: H - m.t - m.b, fill: 'transparent' }, s);
      hit.addEventListener('mousemove', (ev) => showHint(`<div class="ib">${k.full || k.name.replace('\n', ' ')}</div><div><b>${label}</b> TL/gün</div>`, ev.clientX, ev.clientY));
      hit.addEventListener('mouseleave', hideHint);
    });
    el('line', { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), stroke: AXIS }, s);
    body.innerHTML = '';
    body.appendChild(s);
    requestAnimationFrame(() => requestAnimationFrame(() => s.querySelectorAll('.column').forEach((r) => r.classList.add('view'))));
  };
  // yalnız veri ucu yuvarlak (taban kare)
  function round(x, y, w, h, r, topRound) {
    r = Math.min(r, h / 2, w / 2);
    if (topRound) return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
    return `M${x},${y}H${x + w}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x + r}Q${x},${y + h} ${x},${y + h - r}Z`;
  }

  /* Aralık şeridi: satirlar [{ad, alt, degerler[], renk, bicim}] her satır kendi ölçeğinde değil, ortak sıfır çizgili ölçek.
     Her nokta bir kombinasyon; kalın çizgi min–maks; dikey çentik medyan. */
  CM.intervalChart = function (body, rows, { min, max, format = (v) => CM.count(v, 2), unit = '' } = {}) {
    const W = body.clientWidth || 900, H = body.clientHeight || 260;
    const m = { l: 250, r: 130, t: 18, b: 36 };
    const s = svg(W, H);
    const all = rows.flatMap((r) => r.values);
    const lo = min ?? Math.min(0, ...all), hi = max ?? Math.max(...all);
    const pad = (hi - lo) * 0.06;
    const X = (v) => m.l + ((v - (lo - pad)) / (hi - lo + 2 * pad)) * (W - m.l - m.r);
    const sh = (H - m.t - m.b) / rows.length;
    for (const v of ticks(lo - pad, hi + pad, 6)) {
      el('line', { x1: X(v), x2: X(v), y1: m.t, y2: H - m.b, stroke: v === 0 ? 'rgba(26,23,20,0.55)' : GRID }, s);
      text(format(v) + unit, { x: X(v), y: H - m.b + 22, 'text-anchor': 'middle', class: 'tick' + (v === 0 ? ' zero' : '') }, s);
    }
    rows.forEach((r, i) => {
      const cy = m.t + sh * (i + 0.5);
      const a = Math.min(...r.values), b = Math.max(...r.values);
      const med = r.values.slice().sort((p, q) => p - q)[Math.floor(r.values.length / 2)];
      text(r.name, { x: 0, y: cy - 4, class: 'row-name' }, s);
      if (r.alt) text(r.alt, { x: 0, y: cy + 15, class: 'row-alt' }, s);
      el('line', { x1: X(a), x2: X(b), y1: cy, y2: cy, stroke: r.color, 'stroke-width': 6, 'stroke-linecap': 'round', opacity: 0.28 }, s);
      r.values.forEach((v, j) => {
        const c = el('circle', { cx: X(v), cy: cy + (((j * 37) % 11) - 5) * 1.6, r: 3.2, fill: r.color, opacity: 0.85 }, s);
        c.addEventListener('mousemove', (ev) => showHint(`<div class="ib">${r.name}</div><div>kombinasyon ${j + 1}: <b>${format(v)}${unit}</b></div>`, ev.clientX, ev.clientY));
        c.addEventListener('mouseleave', hideHint);
      });
      el('line', { x1: X(med), x2: X(med), y1: cy - 14, y2: cy + 14, stroke: '#1A1714', 'stroke-width': 2 }, s);
      text(`${format(a)} … ${format(b)}${unit}`, { x: W - m.r + 12, y: cy + 5, class: 'end-name' }, s);
    });
    body.innerHTML = '';
    body.appendChild(s);
  };

  /* Teslim zamanı örneği: x = gün, y = saat; noktalar geçmiş denemeler (dolu: teslim, halka: alıcı yok), yatay dilimler,
     kötü dilim kırmızı tül, iyi dilim yeşil tül; o gün: zamansız varış → hafızalı varış oku. saat: "HH:MM" */
  CM.timeChart = function (body, o) {
    const W = body.clientWidth || 700, H = body.clientHeight || 380;
    const m = { l: 64, r: 210, t: 16, b: 44 };
    const s = svg(W, H);
    const mins = (h) => { const [a, b] = h.split(':').map(Number); return a * 60 + b; };
    const days = o.history.map((g) => g.day).concat([o.day]);
    const g0 = 0, g1 = Math.max(...days) + 2;
    const s0 = 9 * 60, s1 = 20 * 60;
    const X = (g) => m.l + ((g - g0) / (g1 - g0)) * (W - m.l - m.r);
    const Y = (v) => m.t + ((v - s0) / (s1 - s0)) * (H - m.t - m.b);
    const LANGUAGE = [[540, 720, '09–12'], [720, 840, '12–14'], [840, 960, '14–16'], [960, 1080, '16–18'], [1080, 1200, '18 sonrası']];
    LANGUAGE.forEach(([a, b, name]) => {
      const bad = name === o.bad, good = name === o.good;
      if (bad || good) el('rect', { x: m.l, y: Y(a), width: W - m.l - m.r, height: Y(b) - Y(a), fill: bad ? '#D2261C' : '#2C7A4B', 'fill-opacity': 0.1 }, s);
      el('line', { x1: m.l, x2: W - m.r, y1: Y(a), y2: Y(a), stroke: GRID }, s);
      text(name, { x: m.l - 10, y: (Y(a) + Y(b)) / 2 + 5, 'text-anchor': 'end', class: 'tick' + (bad ? ' red' : '') }, s);
    });
    for (const v of ticks(g0, g1, 6)) text('gün ' + v, { x: X(v), y: H - m.b + 22, 'text-anchor': 'middle', class: 'tick' }, s);
    el('line', { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: AXIS }, s);
    o.history.forEach((g, i) => {
      const x = X(g.day), y = Y(mins(g.hour)), ok = g.result === 'delivery';
      const c = el('circle', ok ? { cx: x, cy: y, r: 6, fill: '#1A1714', stroke: '#FBF8F2', 'stroke-width': 2 } : { cx: x, cy: y, r: 6, fill: '#FBF8F2', stroke: '#D2261C', 'stroke-width': 3 }, s);
      c.style.opacity = 0; c.style.transition = `opacity 300ms ${200 + i * 120}ms`;
      requestAnimationFrame(() => requestAnimationFrame(() => (c.style.opacity = 1)));
      const hit = el('circle', { cx: x, cy: y, r: 14, fill: 'transparent' }, s);
      hit.addEventListener('mousemove', (ev) => showHint(`<div class="ib">Gün ${g.day} · ${g.weekday} ${g.hour}</div><div>${ok ? 'Teslim' : 'Alıcı yok'}</div>`, ev.clientX, ev.clientY));
      hit.addEventListener('mouseleave', hideHint);
    });
    if (o.legacy && o.is_new) {
      const x = X(o.day), y0 = Y(mins(o.legacy)), y1 = Y(mins(o.is_new));
      const g = el('g', { class: 'ok-group' }, s);
      el('line', { x1: x, x2: x, y1: y0 + (y1 < y0 ? -9 : 9), y2: y1 + (y1 < y0 ? 12 : -12), stroke: '#1A1714', 'stroke-width': 2 }, g);
      el('path', { d: y1 < y0 ? `M${x - 6},${y1 + 14} L${x},${y1 + 6} L${x + 6},${y1 + 14}` : `M${x - 6},${y1 - 14} L${x},${y1 - 6} L${x + 6},${y1 - 14}`, fill: 'none', stroke: '#1A1714', 'stroke-width': 2 }, g);
      el('circle', { cx: x, cy: y0, r: 7, fill: '#FBF8F2', stroke: '#D2261C', 'stroke-width': 3, 'stroke-dasharray': '3 2' }, g);
      el('circle', { cx: x, cy: y1, r: 7, fill: '#2C7A4B', stroke: '#FBF8F2', 'stroke-width': 2 }, g);
      text(`gün ${o.day}, ${o.legacy}: alıcı yok`, { x: x + 14, y: y0 + 5, class: 'end-name' }, g);
      text(`(teslim zamanı analizi olmadan)`, { x: x + 14, y: y0 + 22, class: 'row-alt' }, g);
      text(`${o.is_new}: teslim (hafızalı)`, { x: x + 14, y: y1 + 5, class: 'end-name' }, g);
      g.style.opacity = 0; g.style.transition = 'opacity 600ms 1600ms';
      requestAnimationFrame(() => requestAnimationFrame(() => (g.style.opacity = 1)));
    }
    body.innerHTML = '';
    body.appendChild(s);
  };
})(window.CM);
