/* Courier Memory · grafikler (SVG). dataviz yöntemi:
   ince işaretler (2px çizgi, ≥8px nokta, ≤24px çubuk, 4px yuvarlak veri ucu), saç teli ızgara,
   lejant + seçici doğrudan etiket, metin daima mürekkep renginde, üzerine gelince ipucu, tablo görünümü. */
'use strict';

(function () {
  const CM = window.CM;
  const R = CM.COLOR;

  function scale(d0, d1, r0, r1) {
    const k = (r1 - r0) / (d1 - d0 || 1);
    const f = (v) => r0 + (v - d0) * k;
    f.reverse = (p) => d0 + (p - r0) / k;
    return f;
  }

  function size(container, minH) {
    const r = container.getBoundingClientRect();
    return { w: Math.max(160, Math.floor(r.width)), h: Math.max(minH || 120, Math.floor(r.height)) };
  }

  /* Veri ucu yuvarlak (4px), taban kare yatay çubuk yolu */
  function horizontalBar(x0, y, x1, h, rad) {
    const w = Math.max(0, x1 - x0);
    const r = Math.min(rad, h / 2, w);
    return `M${x0} ${y}h${w - r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 ${-r} ${r}h${-(w - r)}z`;
  }

  /* Uç etiketleri: çakışırsa üst üste yığma yok; ayır ve kılavuz çizgisiyle bağla. */
  function labelLayout(items, min, max, interval) {
    const s = items.slice().sort((a, b) => a.y - b.y);
    for (let i = 0; i < s.length; i++) {
      s[i].ly = Math.max(s[i].y, i ? s[i - 1].ly + interval : min);
    }
    if (s.length && s[s.length - 1].ly > max) {
      s[s.length - 1].ly = max;
      for (let i = s.length - 2; i >= 0; i--) s[i].ly = Math.min(s[i].ly, s[i + 1].ly - interval);
    }
    return s;
  }

  /* ---------------------------------------------------------------- lejant */
  CM.legend = function (series, type) {
    return CM.h(
      'div',
      { class: 'legend' },
      series.map((s) =>
        CM.h(
          'span',
          { class: 'lj' },
          CM.h('i', { class: type === 'bar-fill' ? 'lj-block' : 'lj-line', style: { background: s.color } }),
          s.name
        )
      )
    );
  };

  /* ---------------------------------------------------------------- kart + tablo görünümü */
  CM.chartCard = function (body, button, draw, table) {
    if (body._card) {
      body._card.adjust(draw, table);
      return body._card;
    }
    let mod = 'chart';
    const refresh = () => {
      CM.clear(body);
      if (mod === 'chart') draw(body);
      else body.appendChild(CM.h('div', { class: 'table-container' }, table()));
    };
    if (button) {
      button.onclick = () => {
        mod = mod === 'chart' ? 'table' : 'chart';
        button.textContent = mod === 'chart' ? 'Tablo' : 'Grafik';
        button.setAttribute('aria-pressed', mod === 'table');
        refresh();
      };
    }
    let last = 0;
    const ro = new ResizeObserver(() => {
      const w = body.clientWidth + 'x' + body.clientHeight;
      if (w === last || mod !== 'chart') return;
      last = w;
      refresh();
    });
    ro.observe(body);
    refresh();
    body._card = {
      refresh,
      adjust(c, t) {
        draw = c;
        table = t;
        refresh();
      },
    };
    return body._card;
  };

  CM.table = function (titles, rows) {
    return CM.h(
      'table',
      { class: 'data-table' },
      CM.h('thead', null, CM.h('tr', null, titles.map((b) => CM.h('th', { text: b })))),
      CM.h(
        'tbody',
        null,
        rows.map((r) => CM.h('tr', null, r.map((c, i) => CM.h(i ? 'td' : 'th', { text: c }))))
      )
    );
  };

  /* ---------------------------------------------------------------- çizgi grafiği */
  CM.lineChart = function (container, o) {
    const { w, h } = size(container, 90);
    const m = { l: 44, r: o.lastLabel === false ? 12 : 92, t: 10, b: 24 };
    const pw = w - m.l - m.r,
      ph = h - m.t - m.b;
    if (pw < 24 || ph < 24) return null; // kap henüz görünür değil; boyut değişince yeniden çizilir
    const X = scale(o.xArea[0], o.xArea[1], m.l, m.l + pw);
    const Y = scale(o.yArea[0], o.yArea[1], m.t + ph, m.t);
    const svg = CM.s('svg', { width: w, height: h, class: 'chart', role: 'img', 'aria-label': o.label || '' });

    // ızgara + eksen
    const g = CM.s('g', { class: 'axis' });
    for (const t of o.yTick) {
      const y = Y(t);
      g.appendChild(CM.s('line', { x1: m.l, x2: m.l + pw, y1: y, y2: y, class: (o.zero ? Math.abs(t) < 1e-12 : t === o.yArea[0]) ? 'base' : 'grid' }));
      g.appendChild(CM.s('text', { x: m.l - 6, y, dy: '0.32em', 'text-anchor': 'end', class: 'tick', text: o.yFormat(t) }));
    }
    for (const t of o.xTick) {
      g.appendChild(CM.s('text', { x: X(t), y: m.t + ph + 16, 'text-anchor': 'middle', class: 'tick', text: o.xFormat(t) }));
    }
    svg.appendChild(g);

    // seçili x işareti
    if (o.markX !== null && o.markX !== undefined && o.markX >= o.xArea[0] && o.markX <= o.xArea[1]) {
      const x = X(o.markX);
      svg.appendChild(CM.s('line', { x1: x, x2: x, y1: m.t, y2: m.t + ph, class: 'selected-x' }));
      if (o.markLabel) svg.appendChild(CM.s('text', { x: x + 4, y: m.t + 9, class: 'tick selected-x-text', text: o.markLabel }));
    }

    // seriler
    const gs = CM.s('g', { class: 'series' });
    for (const s of o.series) {
      const pts = s.points.filter((p) => p.y !== null && p.y !== undefined);
      if (!pts.length) continue;
      gs.appendChild(
        CM.s('polyline', {
          points: pts.map((p) => X(p.x).toFixed(1) + ',' + Y(p.y).toFixed(1)).join(' '),
          class: 'series-line' + (s.thin ? ' thin' : ''),
          style: `stroke:${s.color}`,
        })
      );
      if (o.pointMark && !s.thin) {
        for (const p of pts) gs.appendChild(CM.s('circle', { cx: X(p.x), cy: Y(p.y), r: 4, class: 'series-point', style: `fill:${s.color}` }));
      }
    }
    svg.appendChild(gs);

    // uç etiketleri (kılavuz çizgili)
    if (o.lastLabel !== false) {
      const items = [];
      for (const s of o.series) {
        const pts = s.points.filter((p) => p.y !== null && p.y !== undefined);
        if (!pts.length || s.unlabeled) continue;
        const p = pts[pts.length - 1];
        items.push({ s, x: X(p.x), y: Y(p.y), v: p.y });
      }
      const place = labelLayout(items, m.t + 4, m.t + ph - 2, 13);
      const ge = CM.s('g', { class: 'end-label' });
      for (const it of place) {
        const lx = m.l + pw + 12;
        ge.appendChild(CM.s('circle', { cx: it.x, cy: it.y, r: 4, class: 'end-point', style: `fill:${it.s.color}` }));
        ge.appendChild(CM.s('polyline', { points: `${it.x + 5},${it.y} ${lx - 3},${it.ly}`, class: 'guide' }));
        ge.appendChild(CM.s('text', { x: lx, y: it.ly, dy: '0.32em', class: 'end-text' }, CM.s('tspan', { class: 'end-name', text: it.s.short || it.s.name }), CM.s('tspan', { dx: 4, text: o.yFormat(it.v, true) })));
      }
      svg.appendChild(ge);
    }

    // artı imleç + ipucu
    const xs = Array.from(new Set(o.series.flatMap((s) => s.points.map((p) => p.x)))).sort((a, b) => a - b);
    const cross = CM.s('line', { y1: m.t, y2: m.t + ph, class: 'plus', style: 'display:none' });
    const rings = CM.s('g', { class: 'plus-ring' });
    svg.appendChild(cross);
    svg.appendChild(rings);
    const target = CM.s('rect', { x: m.l, y: m.t, width: pw, height: ph, class: 'beat', tabindex: 0 });
    svg.appendChild(target);
    let focus = -1;
    const show = (xi, cx, cy) => {
      if (xi < 0) return;
      const xv = xs[xi];
      const px = X(xv);
      cross.setAttribute('x1', px);
      cross.setAttribute('x2', px);
      cross.style.display = '';
      CM.clear(rings);
      const content = [CM.h('div', { class: 'tt-title', text: o.hintTitle ? o.hintTitle(xv) : String(xv) })];
      for (const s of o.series) {
        const p = s.points.find((q) => q.x === xv);
        if (!p || p.y === null || p.y === undefined) continue;
        rings.appendChild(CM.s('circle', { cx: px, cy: Y(p.y), r: 4.5, style: `fill:${s.color}` }));
        content.push(CM.hintRow(s.color, o.yFormat(p.y, true), s.name + (p.extra ? ' · ' + p.extra : '')));
      }
      if (o.hintExtra) {
        const extra = o.hintExtra(xv);
        if (extra) content.push(extra);
      }
      if (o.onTick) content.push(CM.h('div', { class: 'tt-note', text: 'Tıklayın: günü seç' }));
      const r = svg.getBoundingClientRect();
      CM.hint.show(cx !== undefined ? cx : r.left + px, cy !== undefined ? cy : r.top + m.t + 10, content);
    };
    const hide = () => {
      cross.style.display = 'none';
      CM.clear(rings);
      CM.hint.hide();
    };
    const nearestX = (evt) => {
      const r = svg.getBoundingClientRect();
      const v = X.reverse(evt.clientX - r.left);
      let bi = -1,
        bd = Infinity;
      xs.forEach((x, i) => {
        const d = Math.abs(x - v);
        if (d < bd) {
          bd = d;
          bi = i;
        }
      });
      return bi;
    };
    target.addEventListener('pointermove', (e) => show(nearestX(e), e.clientX, e.clientY));
    target.addEventListener('pointerleave', hide);
    target.addEventListener('blur', hide);
    target.addEventListener('click', (e) => {
      const i = nearestX(e);
      if (i >= 0 && o.onTick) o.onTick(xs[i]);
    });
    target.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        focus = Math.min(xs.length - 1, Math.max(0, focus + (e.key === 'ArrowRight' ? 1 : -1)));
        show(focus);
        e.preventDefault();
      } else if (e.key === 'Enter' && focus >= 0 && o.onTick) o.onTick(xs[focus]);
    });
    if (o.onTick) target.style.cursor = 'pointer';
    container.appendChild(svg);
    return svg;
  };

  /* ---------------------------------------------------------------- gruplu yatay çubuk */
  CM.groupBar = function (container, o) {
    const { w, h } = size(container, 140);
    const m = { l: o.leftGap || 150, r: 44, t: 4, b: 22 };
    const pw = w - m.l - m.r,
      ph = h - m.t - m.b;
    if (pw < 24 || ph < 24) return null; // kap henüz görünür değil; boyut değişince yeniden çizilir
    const n = o.series.length;
    const gh = ph / o.groups.length;
    const bh = Math.min(24, Math.max(4, Math.floor((gh - 10) / n) - 2));
    const max = o.max || Math.max(...o.groups.flatMap((g) => o.series.map((s) => g.values[s.id] || 0)));
    const X = scale(0, max, m.l, m.l + pw);
    const svg = CM.s('svg', { width: w, height: h, class: 'chart', role: 'img', 'aria-label': o.label || '' });
    const ge = CM.s('g', { class: 'axis' });
    for (const t of o.ticks) {
      ge.appendChild(CM.s('line', { x1: X(t), x2: X(t), y1: m.t, y2: m.t + ph, class: t === 0 ? 'base' : 'grid' }));
      ge.appendChild(CM.s('text', { x: X(t), y: m.t + ph + 15, 'text-anchor': 'middle', class: 'tick', text: o.format(t) }));
    }
    svg.appendChild(ge);
    o.groups.forEach((gr, gi) => {
      const y0 = m.t + gi * gh;
      const blockH = n * (bh + 2) - 2;
      const by = y0 + (gh - blockH) / 2;
      const gg = CM.s('g', { class: 'group ' + (gr.accent ? 'accent' : 'faded') });
      if (gr.accent) gg.appendChild(CM.s('rect', { x: 0, y: y0 + 1, width: w, height: gh - 2, class: 'group-bg', rx: 4 }));
      gg.appendChild(CM.s('text', { x: m.l - 10, y: y0 + gh / 2 - (gr.alt ? 6 : 0), dy: '0.32em', 'text-anchor': 'end', class: 'group-name', text: gr.name }));
      if (gr.alt) gg.appendChild(CM.s('text', { x: m.l - 10, y: y0 + gh / 2 + 8, dy: '0.32em', 'text-anchor': 'end', class: 'group-alt', text: gr.alt }));
      o.series.forEach((s, si) => {
        const v = gr.values[s.id] || 0;
        const y = by + si * (bh + 2);
        const bar = CM.s('path', { d: horizontalBar(m.l, y, X(v), bh, 4), class: 'bar-fill', style: `fill:${s.color}`, tabindex: 0 });
        const info = (e) => {
          const r = bar.getBoundingClientRect();
          CM.hint.show(e && e.clientX ? e.clientX : r.right, e && e.clientY ? e.clientY : r.top, [
            CM.h('div', { class: 'tt-title', text: gr.name }),
            CM.hintRow(s.color, o.format(v, true), s.name),
          ]);
        };
        bar.addEventListener('pointermove', info);
        bar.addEventListener('focus', () => info());
        bar.addEventListener('pointerleave', () => CM.hint.hide());
        bar.addEventListener('blur', () => CM.hint.hide());
        gg.appendChild(bar);
        if (o.labelSeries && s.id === o.labelSeries) {
          gg.appendChild(CM.s('text', { x: X(v) + 5, y: y + bh / 2, dy: '0.32em', class: 'bar-value', text: o.format(v, true) }));
        }
      });
      svg.appendChild(gg);
    });
    container.appendChild(svg);
    return svg;
  };

  /* ---------------------------------------------------------------- nokta grafiği (sıfırsız eksen için) */
  CM.pointChart = function (container, o) {
    const { w, h } = size(container, 90);
    const m = { l: o.leftGap || 150, r: 54, t: 4, b: 20 };
    const pw = w - m.l - m.r,
      ph = h - m.t - m.b;
    if (pw < 24 || ph < 24) return null; // kap henüz görünür değil; boyut değişince yeniden çizilir
    const X = scale(o.area[0], o.area[1], m.l, m.l + pw);
    const rh = ph / o.rows.length;
    const svg = CM.s('svg', { width: w, height: h, class: 'chart', role: 'img', 'aria-label': o.label || '' });
    const ge = CM.s('g', { class: 'axis' });
    for (const t of o.ticks) {
      ge.appendChild(CM.s('line', { x1: X(t), x2: X(t), y1: m.t, y2: m.t + ph, class: 'grid' }));
      ge.appendChild(CM.s('text', { x: X(t), y: m.t + ph + 14, 'text-anchor': 'middle', class: 'tick', text: o.format(t) }));
    }
    svg.appendChild(ge);
    o.rows.forEach((s, i) => {
      const y = m.t + i * rh + rh / 2;
      svg.appendChild(CM.s('line', { x1: m.l, x2: m.l + pw, y1: y, y2: y, class: 'point-trace' }));
      svg.appendChild(CM.s('text', { x: m.l - 10, y, dy: '0.32em', 'text-anchor': 'end', class: 'group-name', text: s.name }));
      if (s.value === null || s.value === undefined) return;
      const c = CM.s('circle', { cx: X(s.value), cy: y, r: 5.5, class: 'series-point', style: `fill:${s.color}`, tabindex: 0 });
      const info = (e) => {
        const r = c.getBoundingClientRect();
        CM.hint.show(e && e.clientX ? e.clientX : r.right, e && e.clientY ? e.clientY : r.top, [
          CM.h('div', { class: 'tt-title', text: o.title || '' }),
          CM.hintRow(s.color, o.format(s.value, true), s.name),
        ]);
      };
      c.addEventListener('pointermove', info);
      c.addEventListener('focus', () => info());
      c.addEventListener('pointerleave', () => CM.hint.hide());
      c.addEventListener('blur', () => CM.hint.hide());
      svg.appendChild(c);
      svg.appendChild(CM.s('text', { x: m.l + pw + 8, y, dy: '0.32em', class: 'bar-value', text: o.format(s.value, true) }));
    });
    container.appendChild(svg);
    return svg;
  };

  /* ---------------------------------------------------------------- şelale (yatay)
     satirlar: [{ad, alt, bas, son, tur: 'artis'|'azalis'|'toplam'|'yan', etiket}] ; ayirac: bu indeksten önce çizgi */
  CM.waterfall = function (container, o) {
    const { w, h } = size(container, 160);
    const m = { l: o.leftGap || 190, r: 78, t: 4, b: 22 };
    const pw = w - m.l - m.r,
      ph = h - m.t - m.b;
    if (pw < 24 || ph < 24) return null; // kap henüz görünür değil; boyut değişince yeniden çizilir
    const n = o.rows.length;
    const rh = ph / n;
    const bh = Math.min(22, Math.max(8, rh - 14));
    const hasAlt = rh >= 30; // sıkışık satırda alt açıklama yalnız ipucunda
    const X = scale(0, o.max, m.l, m.l + pw);
    const COLOR = { increase: o.colorIncrease, decrease: o.colorDecrease, total: o.colorTotal, side: o.colorSide };
    const svg = CM.s('svg', { width: w, height: h, class: 'chart waterfall', role: 'img', 'aria-label': o.label || '' });
    const ge = CM.s('g', { class: 'axis' });
    for (const t of o.ticks) {
      ge.appendChild(CM.s('line', { x1: X(t), x2: X(t), y1: m.t, y2: m.t + ph, class: t === 0 ? 'base' : 'grid' }));
      ge.appendChild(CM.s('text', { x: X(t), y: m.t + ph + 15, 'text-anchor': 'middle', class: 'tick', text: o.format(t) }));
    }
    svg.appendChild(ge);
    let previous = null;
    o.rows.forEach((r, i) => {
      const y0 = m.t + i * rh;
      const yc = y0 + rh / 2;
      if (o.divider === i) svg.appendChild(CM.s('line', { x1: 0, x2: w, y1: y0, y2: y0, class: 'waterfall-divider' }));
      const a = Math.min(r.head, r.last),
        b = Math.max(r.head, r.last);
      const g = CM.s('g', { class: 'waterfall-row ' + r.type, tabindex: 0 });
      g.appendChild(CM.s('text', { x: m.l - 10, y: yc - (r.alt && hasAlt ? 6 : 0), dy: '0.32em', 'text-anchor': 'end', class: 'group-name' + (r.type === 'total' ? ' bold' : ''), text: r.name }));
      if (r.alt && hasAlt) g.appendChild(CM.s('text', { x: m.l - 10, y: yc + 8, dy: '0.32em', 'text-anchor': 'end', class: 'group-alt', text: r.alt }));
      const x0 = X(a),
        x1 = Math.max(X(b), x0 + 1.5);
      const rr = Math.min(4, bh / 2, (x1 - x0) / 2);
      g.appendChild(CM.s('rect', { x: x0, y: yc - bh / 2, width: x1 - x0, height: bh, rx: rr, class: 'waterfall-bar', style: `fill:${COLOR[r.type] || '#999'}` }));
      g.appendChild(CM.s('text', { x: x1 + 6, y: yc, dy: '0.32em', class: 'bar-value' + (r.type === 'total' ? ' bold' : ''), text: r.label }));
      // bağlayıcı: önceki satırın sonundan bu satırın başına saç teli
      if (previous && r.type !== 'side' && previous.type !== 'side') {
        const xb = X(previous.last);
        svg.appendChild(CM.s('line', { x1: xb, x2: xb, y1: previous.yc + bh / 2, y2: yc - bh / 2, class: 'waterfall-link' }));
      }
      const info = (e) => {
        const rc = g.getBoundingClientRect();
        CM.hint.show(e && e.clientX ? e.clientX : rc.right, e && e.clientY ? e.clientY : rc.top, [
          CM.h('div', { class: 'tt-title', text: r.name }),
          CM.hintRow(COLOR[r.type], r.label, r.alt || ''),
          r.note ? CM.h('div', { class: 'tt-note', text: r.note }) : null,
        ]);
      };
      g.addEventListener('pointermove', info);
      g.addEventListener('focus', () => info());
      g.addEventListener('pointerleave', () => CM.hint.hide());
      g.addEventListener('blur', () => CM.hint.hide());
      svg.appendChild(g);
      previous = Object.assign({ yc }, r);
    });
    container.appendChild(svg);
    return svg;
  };

  /* ---------------------------------------------------------------- dikey şelale (başlangıç → adımlar → sonuç)
     adimlar: [{ad, alt, aciklama, deger, tur: 'baslangic'|'azalis'|'artis'|'sonuc'}]
     deger: başlangıç/sonuçta mutlak, adımlarda işaretli. Etiketler sütunların altında HTML olarak. */
  CM.waterfallVertical = function (container, o) {
    const { w, h } = size(container, 220);
    const labelH = o.labelHeight || 74;
    const sh = h - labelH;
    const m = { l: 58, r: o.diff ? 128 : 16, t: 22, b: 6 };
    const pw = w - m.l - m.r,
      ph = sh - m.t - m.b;
    if (pw < 24 || ph < 24) return null; // kap henüz görünür değil; boyut değişince yeniden çizilir
    const n = o.steps.length;
    const cw = pw / n;
    const bw = Math.min(78, cw * 0.56);
    // seviyeler
    let lvl = 0;
    const boxes = o.steps.map((a) => {
      let alt, top;
      if (a.type === 'start' || a.type === 'result') {
        alt = 0;
        top = a.value;
        lvl = a.value;
      } else {
        alt = lvl;
        top = lvl + a.value;
        lvl = top;
      }
      return { a, lo: Math.min(alt, top), hi: Math.max(alt, top), last: lvl };
    });
    const mx = Math.max(...boxes.map((k) => k.hi), 1);
    const step = CM.tickStep(mx, 4);
    const max = Math.ceil((mx * 1.04) / step) * step;
    const Y = scale(0, max, m.t + ph, m.t);
    const wrap = CM.h('div', { class: 'vertical-waterfall' });
    const svg = CM.s('svg', { width: w, height: sh, class: 'chart', role: 'img', 'aria-label': o.label || '' });
    const ge = CM.s('g', { class: 'axis' });
    for (const t of CM.ticks(0, max, step)) {
      ge.appendChild(CM.s('line', { x1: m.l, x2: m.l + pw, y1: Y(t), y2: Y(t), class: t === 0 ? 'base' : 'grid' }));
      ge.appendChild(CM.s('text', { x: m.l - 8, y: Y(t), dy: '0.32em', 'text-anchor': 'end', class: 'tick', text: o.format(t) }));
    }
    svg.appendChild(ge);
    boxes.forEach((k, i) => {
      const cx = m.l + (i + 0.5) * cw;
      const x0 = cx - bw / 2;
      const g = CM.s('g', { class: 'vertical-column ' + k.a.type, tabindex: 0 });
      g.appendChild(CM.s('rect', { x: m.l + i * cw, y: m.t, width: cw, height: ph, class: 'beat' }));
      const y1 = Y(k.hi),
        y0 = Y(k.lo);
      const hh = Math.max(1.5, y0 - y1);
      const full = k.a.type === 'start' || k.a.type === 'result';
      // tam sütun: tabanda kare, veri ucunda 4px yuvarlak; adım: iki uç yuvarlak (yüzen)
      const r = Math.min(4, hh / 2, bw / 2);
      const d = full
        ? `M${x0} ${y0}V${y1 + r}a${r} ${r} 0 0 1 ${r} ${-r}H${x0 + bw - r}a${r} ${r} 0 0 1 ${r} ${r}V${y0}z`
        : `M${x0 + r} ${y1}H${x0 + bw - r}a${r} ${r} 0 0 1 ${r} ${r}V${y1 + hh - r}a${r} ${r} 0 0 1 ${-r} ${r}H${x0 + r}a${r} ${r} 0 0 1 ${-r} ${-r}V${y1 + r}a${r} ${r} 0 0 1 ${r} ${-r}z`;
      g.appendChild(CM.s('path', { d, class: 'vertical-bar', style: `fill:${o.color[k.a.type] || '#999'}` }));
      g.appendChild(CM.s('text', { x: cx, y: y1 - 7, 'text-anchor': 'middle', class: 'vertical-value' + (full ? ' bold' : ''), text: o.label2(k.a.value, k.a.type) }));
      if (i < boxes.length - 1) {
        const nx = m.l + (i + 1.5) * cw - bw / 2;
        g.appendChild(CM.s('line', { x1: x0 + bw, x2: nx, y1: Y(k.last), y2: Y(k.last), class: 'waterfall-link' }));
      }
      const info = (e) => {
        const rc = g.getBoundingClientRect();
        CM.hint.show(e && e.clientX ? e.clientX : rc.left + rc.width / 2, e && e.clientY ? e.clientY : rc.top + 20, [
          CM.h('div', { class: 'tt-title', text: k.a.name }),
          CM.hintRow(o.color[k.a.type], o.label2(k.a.value, k.a.type), full ? 'operasyon maliyeti' : 'değişim'),
          !full ? CM.hintRow(null, o.label2(k.last, 'result'), 'bu adımdan sonra') : null,
          k.a.explanation ? CM.h('div', { class: 'tt-alt', text: k.a.explanation }) : null,
        ]);
      };
      g.addEventListener('pointermove', info);
      g.addEventListener('focus', () => info());
      g.addEventListener('pointerleave', () => CM.hint.hide());
      g.addEventListener('blur', () => CM.hint.hide());
      svg.appendChild(g);
    });
    // başlangıç ile sonuç arası fark parantezi
    if (o.diff && boxes.length > 1) {
      const first = boxes[0],
        last = boxes[boxes.length - 1];
      const xs = m.l + (n - 0.5) * cw + bw / 2 + 14;
      const xa = xs - 12; // başlangıç düzeyi yalnız parantezin yanında (etiketlerin üstünden geçmez)
      const ya = Y(first.hi),
        yb = Y(last.hi);
      const gf = CM.s('g', { class: 'diff-parantez' });
      gf.appendChild(CM.s('line', { x1: xa, x2: xs + 4, y1: ya, y2: ya, class: 'diff-trace' }));
      gf.appendChild(CM.s('line', { x1: xs, x2: xs, y1: ya, y2: yb, class: 'diff-line' }));
      gf.appendChild(CM.s('line', { x1: xs - 4, x2: xs + 4, y1: yb, y2: yb, class: 'diff-line' }));
      gf.appendChild(CM.s('line', { x1: xs - 4, x2: xs + 4, y1: ya, y2: ya, class: 'diff-line' }));
      const ym = (ya + yb) / 2;
      gf.appendChild(CM.s('text', { x: xs + 9, y: ym - 7, class: 'diff-text', text: o.diff.text }));
      gf.appendChild(CM.s('text', { x: xs + 9, y: ym + 9, class: 'diff-alt', text: o.diff.alt || '' }));
      svg.appendChild(gf);
    }
    wrap.appendChild(svg);
    const et = CM.h('div', { class: 'vertical-labels', style: { paddingLeft: m.l + 'px', paddingRight: m.r + 'px', height: labelH + 'px', gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` } });
    for (const k of boxes) {
      et.appendChild(CM.h('div', { class: 'vertical-label ' + k.a.type }, CM.h('b', { text: k.a.name }), k.a.alt ? CM.h('span', { class: 'de-alt', text: k.a.alt }) : null, k.a.explanation ? CM.h('span', { class: 'de-explanation', text: k.a.explanation }) : null));
    }
    wrap.appendChild(et);
    container.appendChild(wrap);
    return wrap;
  };

  /* ---------------------------------------------------------------- tek renkli yatay çubuk (nominal kategoriler) */
  CM.simpleBar = function (container, o) {
    const { w, h } = size(container, 60);
    const m = { l: o.leftGap || 130, r: o.rightGap || 120, t: 2, b: 2 };
    const pw = w - m.l - m.r;
    if (pw < 24) return null;
    const n = o.rows.length;
    const rh = (h - m.t - m.b) / n;
    const bh = Math.min(16, Math.max(6, rh - 10));
    const max = o.max || Math.max(...o.rows.map((r) => r.value), 1e-9);
    const X = scale(0, max, m.l, m.l + pw);
    const svg = CM.s('svg', { width: w, height: h, class: 'chart', role: 'img', 'aria-label': o.label || '' });
    svg.appendChild(CM.s('line', { x1: m.l, x2: m.l, y1: m.t, y2: h - m.b, class: 'base' }));
    o.rows.forEach((r, i) => {
      const yc = m.t + i * rh + rh / 2;
      const g = CM.s('g', { class: 'simple-row' + (r.accent ? ' accent' : ''), tabindex: 0 });
      g.appendChild(CM.s('text', { x: m.l - 8, y: yc, dy: '0.32em', 'text-anchor': 'end', class: 'group-name' + (r.accent ? ' bold' : ''), text: r.name }));
      g.appendChild(CM.s('path', { d: horizontalBar(m.l, yc - bh / 2, Math.max(m.l + 1.5, X(r.value)), bh, 4), class: 'bar-fill', style: `fill:${o.color}` }));
      g.appendChild(CM.s('text', { x: Math.max(m.l + 1.5, X(r.value)) + 6, y: yc, dy: '0.32em', class: 'bar-value', text: r.label }));
      const info = (e) => {
        const rc = g.getBoundingClientRect();
        CM.hint.show(e && e.clientX ? e.clientX : rc.right, e && e.clientY ? e.clientY : rc.top, [CM.h('div', { class: 'tt-title', text: r.name }), CM.hintRow(o.color, r.label, o.title || ''), r.note ? CM.h('div', { class: 'tt-note', text: r.note }) : null]);
      };
      g.addEventListener('pointermove', info);
      g.addEventListener('focus', () => info());
      g.addEventListener('pointerleave', () => CM.hint.hide());
      g.addEventListener('blur', () => CM.hint.hide());
      svg.appendChild(g);
    });
    container.appendChild(svg);
    return svg;
  };

  /* Hareketli ortalama (geriye dönük, n gün) */
  CM.movingMean = function (series, n) {
    return series.map((_, i) => {
      const part = series.slice(Math.max(0, i - n + 1), i + 1).filter((v) => v !== null && v !== undefined);
      return part.length ? part.reduce((a, b) => a + b, 0) / part.length : null;
    });
  };

  /* Okunur tik adımı: yaklaşık n aralık */
  CM.tickStep = function (max, n) {
    const ham = max / (n || 4);
    const us = Math.pow(10, Math.floor(Math.log10(ham || 1)));
    return [1, 2, 2.5, 5, 10].map((x) => x * us).find((x) => x >= ham) || ham;
  };

  /* Temiz tik değerleri */
  CM.ticks = function (a, b, step) {
    const out = [];
    const s = Math.ceil(a / step - 1e-9) * step;
    for (let v = s; v <= b + 1e-9; v += step) out.push(+v.toFixed(6));
    return out;
  };
})();
