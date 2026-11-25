/* Courier Memory · SVG harita: blok ızgarası altlığı, rotalar, duraklar, işaretçi.
   Harita karosu yok; yakınlaştırma/kaydırma viewBox ile. */
'use strict';

(function () {
  const CM = window.CM;

  /* Blok altlığı tonları: veri değil bağlam; çok soluk. Kırsal neredeyse boş. */
  const BLOCK_TONE = {
    busy_residential: '#ece7de',
    site: '#e3eaee',
    industrial: '#e9e7ed',
    business_center: '#f0e4e4',
    rural: '#f8f8f4',
  };
  CM.BLOCK_TONE = BLOCK_TONE;

  /* --------------------------------------------------------------- projeksiyon */
  CM.projection = function (blocks) {
    const F = {};
    (blocks.fields || ['id', 'row', 'col', 'kind', 'lat', 'lng']).forEach((f, i) => (F[f] = i));
    const bl = blocks.blocks || [];
    let minLat = Infinity,
      maxLat = -Infinity,
      minLng = Infinity,
      maxLng = -Infinity;
    for (const b of bl) {
      const la = b[F.lat],
        ln = b[F.lng];
      if (la < minLat) minLat = la;
      if (la > maxLat) maxLat = la;
      if (ln < minLng) minLng = ln;
      if (ln > maxLng) maxLng = ln;
    }
    const dlat = blocks.dlat || 0.0027,
      dlng = blocks.dlng || 0.0035;
    minLat -= dlat / 2;
    maxLat += dlat / 2;
    minLng -= dlng / 2;
    maxLng += dlng / 2;
    const lat0 = ((minLat + maxLat) / 2) * (Math.PI / 180);
    const kx = 111320 * Math.cos(lat0);
    const ky = 110540;
    const x = (lng) => (lng - minLng) * kx;
    const y = (lat) => (maxLat - lat) * ky;
    const bw = dlng * kx,
      bh = dlat * ky;
    const roads = {};
    for (const b of bl) {
      const k = b[F.kind];
      if (k === 'rural') continue;
      const cx = x(b[F.lng]),
        cy = y(b[F.lat]);
      roads[k] = (roads[k] || '') + `M${(cx - bw / 2).toFixed(1)} ${(cy - bh / 2).toFixed(1)}h${bw.toFixed(1)}v${bh.toFixed(1)}h${(-bw).toFixed(1)}z`;
    }
    return { x, y, W: (maxLng - minLng) * kx, H: (maxLat - minLat) * ky, roads, bw, bh };
  };

  /* --------------------------------------------------------------- işaret şekilleri (piksel birimi) */
  function circle(r) {
    return `M${-r} 0a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0z`;
  }
  function frame(s) {
    return `M${-s} ${-s}h${2 * s}v${2 * s}h${-2 * s}z`;
  }

  function markParts(status, color, hint, mini) {
    const k = mini ? 0.8 : 1;
    const out = [];
    if (hint) out.push(CM.s('path', { d: circle(5.4 * k), class: 'm-hint' }));
    if (status === 'fail') out.push(CM.s('path', { d: circle(3.7 * k), class: 'm-fail' }));
    else if (status === 'deferred') out.push(CM.s('path', { d: frame(3.2 * k), class: 'm-deferred' }));
    else if (status === 'plan') out.push(CM.s('path', { d: circle(2.5 * k), class: 'm-plan', style: `stroke:${color}` }));
    else if (status === 'hidden') {
      /* gösterilmeyen başarılı durak (mini haritada) */
    } else out.push(CM.s('path', { d: circle(2.1 * k), class: 'm-ok', style: `fill:${color}` }));
    return out;
  }
  CM.markParts = markParts;

  /* --------------------------------------------------------------- Harita sınıfı */
  class MapView {
    constructor(container, opts) {
      this.opts = Object.assign({ mini: false, onSelect: null, onOver: null, onView: null }, opts || {});
      this.p = this.opts.proj;
      this.container = container;
      container.classList.add('map');
      if (this.opts.mini) container.classList.add('mini');
      this.svg = CM.s('svg', { class: 'map-svg', preserveAspectRatio: 'xMidYMid meet', role: 'img', 'aria-label': this.opts.label || 'MapView' });
      this.gBlock = CM.s('g', { class: 'k-block' });
      this.gRoute = CM.s('g', { class: 'k-route' });
      this.gPoint = CM.s('g', { class: 'k-point' });
      this.gLabel = CM.s('g', { class: 'k-label' });
      this.gTop = CM.s('g', { class: 'k-top' });
      this.svg.append(this.gBlock, this.gRoute, this.gPoint, this.gLabel, this.gTop);
      container.appendChild(this.svg);
      this.scaled = []; // {el, x, y}
      this.points = []; // vuruş testi
      this.routeEl = new Map();
      this.stopEl = new Map();
      this.vb = { x: 0, y: 0, w: this.p.W, h: this.p.H };
      this.border = null;
      this._basemap();
      this._controls();
      this._interaction();
      this._ro = new ResizeObserver(() => this._size());
      this._ro.observe(container);
    }

    _basemap() {
      const g = this.gBlock;
      g.appendChild(CM.s('rect', { x: 0, y: 0, width: this.p.W, height: this.p.H, fill: BLOCK_TONE.rural }));
      for (const [k, d] of Object.entries(this.p.roads)) {
        g.appendChild(CM.s('path', { d, fill: BLOCK_TONE[k] || '#eee', class: 'block block-' + k }));
      }
    }

    _controls() {
      const k = CM.h('div', { class: 'map-check' });
      const btn = (t, title, fn) => CM.h('button', { type: 'button', class: 'hk', title, 'aria-label': title, onclick: fn }, t);
      if (!this.opts.mini) {
        k.append(btn('+', 'Yakınlaştır', () => this.zoomIn(0.7)), btn('−', 'Uzaklaştır', () => this.zoomIn(1 / 0.7)));
      }
      k.append(btn('⤢', 'Görünümü sıfırla', () => this.limit(this.border)));
      this.container.appendChild(k);
    }

    /* ------------------------------------------------ görünüm */
    _size() {
      const r = this.svg.getBoundingClientRect();
      if (!r.width || !r.height) return;
      const asp = r.width / r.height;
      const cx = this.vb.x + this.vb.w / 2,
        cy = this.vb.y + this.vb.h / 2;
      // görünümü kap oranına getir (alanı koru)
      const area = this.vb.w * this.vb.h;
      let w = Math.sqrt(area * asp),
        h = w / asp;
      if (!this._first) {
        this._first = true;
        this.limit(this.border);
        return;
      }
      this.vb = { x: cx - w / 2, y: cy - h / 2, w, h };
      this._apply(true);
    }

    limit(b, pad) {
      this.border = b || this.border;
      const s = this.border || { x0: 0, y0: 0, x1: this.p.W, y1: this.p.H };
      const r = this.svg.getBoundingClientRect();
      const asp = r.width && r.height ? r.width / r.height : 1.3;
      const pd = pad === undefined ? 0.06 : pad;
      let w = (s.x1 - s.x0) * (1 + 2 * pd),
        h = (s.y1 - s.y0) * (1 + 2 * pd);
      w = Math.max(w, 900);
      h = Math.max(h, 900 / asp);
      if (w / h > asp) h = w / asp;
      else w = h * asp;
      const cx = (s.x0 + s.x1) / 2,
        cy = (s.y0 + s.y1) / 2;
      this.vb = { x: cx - w / 2, y: cy - h / 2, w, h };
      this._apply();
    }

    adjustView(vb) {
      const r = this.svg.getBoundingClientRect();
      const asp = r.width && r.height ? r.width / r.height : vb.w / vb.h;
      const cx = vb.x + vb.w / 2,
        cy = vb.y + vb.h / 2;
      let w = vb.w,
        h = w / asp;
      this.vb = { x: cx - w / 2, y: cy - h / 2, w, h };
      this._apply(true);
    }

    zoomIn(f, px, py) {
      const r = this.svg.getBoundingClientRect();
      const ux = px === undefined ? 0.5 : (px - r.left) / r.width;
      const uy = py === undefined ? 0.5 : (py - r.top) / r.height;
      const wx = this.vb.x + ux * this.vb.w,
        wy = this.vb.y + uy * this.vb.h;
      let w = this.vb.w * f;
      w = Math.min(Math.max(w, 500), this.p.W * 1.6);
      const k = w / this.vb.w;
      const h = this.vb.h * k;
      this.vb = { x: wx - ux * w, y: wy - uy * h, w, h };
      this._apply();
    }

    _upp() {
      const r = this.svg.getBoundingClientRect();
      if (!r.width) return this.vb.w / 800;
      return Math.max(this.vb.w / r.width, this.vb.h / r.height);
    }

    _apply(silent) {
      const v = this.vb;
      this.svg.setAttribute('viewBox', `${v.x.toFixed(1)} ${v.y.toFixed(1)} ${v.w.toFixed(1)} ${v.h.toFixed(1)}`);
      if (this._shelf) return;
      this._shelf = requestAnimationFrame(() => {
        this._shelf = null;
        const u = this._upp();
        this.u = u;
        const us = u.toFixed(3);
        for (const o of this.scaled) o.el.setAttribute('transform', `translate(${o.x.toFixed(1)} ${o.y.toFixed(1)}) scale(${us})`);
      });
      if (!silent && this.opts.onView) this.opts.onView(this.vb);
    }

    _scaled(el, x, y) {
      const o = { el, x, y };
      el.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${(this.u || this._upp()).toFixed(3)})`);
      this.scaled.push(o);
      return o;
    }

    _world(evt) {
      const r = this.svg.getBoundingClientRect();
      const u = this._upp();
      // meet: içerik ortalanır
      const cw = this.vb.w / u,
        ch = this.vb.h / u;
      const ox = (r.width - cw) / 2,
        oy = (r.height - ch) / 2;
      return { x: this.vb.x + (evt.clientX - r.left - ox) * u, y: this.vb.y + (evt.clientY - r.top - oy) * u, u };
    }

    nearest(evt, px) {
      const w = this._world(evt);
      const lim = (px || 10) * w.u;
      let best = null,
        bd = lim * lim;
      for (const n of this.points) {
        const dx = n.x - w.x,
          dy = n.y - w.y;
        const d = dx * dx + dy * dy;
        if (d < bd) {
          bd = d;
          best = n;
        }
      }
      return best;
    }

    /* ------------------------------------------------ etkileşim */
    _interaction() {
      const svg = this.svg;
      let drag = null;
      svg.addEventListener(
        'wheel',
        (e) => {
          e.preventDefault();
          this.zoomIn(Math.exp(e.deltaY * 0.0016), e.clientX, e.clientY);
        },
        { passive: false }
      );
      svg.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return;
        drag = { x: e.clientX, y: e.clientY, vb: Object.assign({}, this.vb), motion: false, id: e.pointerId };
      });
      svg.addEventListener('pointermove', (e) => {
        if (drag) {
          const dx = e.clientX - drag.x,
            dy = e.clientY - drag.y;
          if (!drag.motion && Math.hypot(dx, dy) > 4) {
            drag.motion = true;
            svg.setPointerCapture(drag.id);
            svg.classList.add('dragging');
            CM.hint.hide();
          }
          if (drag.motion) {
            const u = this._upp();
            this.vb = Object.assign({}, this.vb, { x: drag.vb.x - dx * u, y: drag.vb.y - dy * u });
            this._apply();
            return;
          }
        }
        if (this._hoverShelf) return;
        const ev = { clientX: e.clientX, clientY: e.clientY };
        this._hoverShelf = requestAnimationFrame(() => {
          this._hoverShelf = null;
          const n = this.nearest(ev, 10);
          if (this.opts.onOver) this.opts.onOver(n, ev);
        });
      });
      const finish = (e) => {
        if (!drag) return;
        const tick = !drag.motion;
        svg.classList.remove('dragging');
        try {
          svg.releasePointerCapture(drag.id);
        } catch (_) {
          /* yok */
        }
        drag = null;
        if (tick && this.opts.onSelect) this.opts.onSelect(this.nearest(e, 14), e);
      };
      svg.addEventListener('pointerup', finish);
      svg.addEventListener('pointercancel', () => {
        drag = null;
        svg.classList.remove('dragging');
      });
      svg.addEventListener('pointerleave', () => {
        if (this.opts.onOver) this.opts.onOver(null, null);
      });
      svg.addEventListener('dblclick', (e) => {
        e.preventDefault();
        this.zoomIn(0.55, e.clientX, e.clientY);
      });
    }

    /* ------------------------------------------------ çizim
       rotalar: [{id, renk, kalinlik, sinif, duraklar:[{lat,lng,durum,ipucu,veri}], etiket:{metin, kalin}, veri, drawFromDepot}] */
    draw({ routes, depot, border }) {
      CM.clear(this.gRoute);
      CM.clear(this.gPoint);
      CM.clear(this.gLabel);
      CM.clear(this.gTop);
      this.scaled = [];
      this.points = [];
      this.routeEl.clear();
      this.stopEl.clear();
      this._marker = null;
      this._ring = null;
      const p = this.p;
      let x0 = Infinity,
        y0 = Infinity,
        x1 = -Infinity,
        y1 = -Infinity;
      const expand = (x, y) => {
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      };
      const depotXY = depot ? [p.x(depot[1]), p.y(depot[0])] : null;
      for (const r of routes) {
        const pts = r.stops.map((d) => [p.x(d.lng), p.y(d.lat)]);
        const g = CM.s('g', { class: 'route ' + (r.css_class || ''), 'data-id': r.id });
        if (r.drawFromDepot && depotXY && pts.length) {
          g.appendChild(
            CM.s('polyline', {
              points: `${depotXY[0].toFixed(1)},${depotXY[1].toFixed(1)} ${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`,
              class: 'route-line bag',
              style: `stroke:${r.color};stroke-width:${(r.thickness || 1.6) * 0.8}px`,
            })
          );
        }
        if (pts.length > 1) {
          g.appendChild(
            CM.s('polyline', {
              points: pts.map((q) => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' '),
              class: 'route-line',
              style: `stroke:${r.color};stroke-width:${r.thickness || 1.6}px`,
            })
          );
        }
        this.gRoute.appendChild(g);
        const gn = CM.s('g', { class: 'route-points ' + (r.css_class || ''), 'data-id': r.id });
        const els = [];
        r.stops.forEach((d, i) => {
          const [x, y] = pts[i];
          expand(x, y);
          const m = CM.s('g', { class: 'stop' });
          CM.add(m, [markParts(d.status, r.color, d.hint, this.opts.mini)]);
          this._scaled(m, x, y);
          gn.appendChild(m);
          els.push({ el: m, x, y });
          this.points.push({ x, y, route: r.id, i, data: d.data, r: r.data });
        });
        this.gPoint.appendChild(gn);
        this.routeEl.set(r.id, { g, gn, color: r.color, css_class: r.css_class });
        this.stopEl.set(r.id, els);
        if (r.label && pts.length && !this.opts.mini) {
          const cx = pts.reduce((a, q) => a + q[0], 0) / pts.length;
          const cy = pts.reduce((a, q) => a + q[1], 0) / pts.length;
          const t = CM.s('g', { class: 'route-label ' + (r.label.bold ? 'bold ' : '') + (r.css_class || ''), 'data-id': r.id });
          t.appendChild(CM.s('text', { class: 'halo', 'text-anchor': 'middle', dy: '0.35em', text: r.label.text }));
          t.appendChild(CM.s('text', { 'text-anchor': 'middle', dy: '0.35em', text: r.label.text }));
          this._scaled(t, cx, cy);
          this.gLabel.appendChild(t);
        }
      }
      if (depotXY) {
        expand(depotXY[0], depotXY[1]);
        const d = CM.s('g', { class: 'depot' });
        d.appendChild(CM.s('path', { d: frame(5.5), class: 'm-depot' }));
        if (!this.opts.mini) {
          d.appendChild(CM.s('text', { class: 'halo', x: 9, dy: '0.35em', text: 'Şube' }));
          d.appendChild(CM.s('text', { x: 9, dy: '0.35em', text: 'Şube' }));
        }
        this._scaled(d, depotXY[0], depotXY[1]);
        this.gTop.appendChild(d);
      }
      if (border !== false) {
        const b = border || (x0 < Infinity ? { x0, y0, x1, y1 } : null);
        this.limit(b);
      }
    }

    routeBorder(id) {
      const els = this.stopEl.get(id);
      if (!els || !els.length) return null;
      let x0 = Infinity,
        y0 = Infinity,
        x1 = -Infinity,
        y1 = -Infinity;
      for (const e of els) {
        x0 = Math.min(x0, e.x);
        x1 = Math.max(x1, e.x);
        y0 = Math.min(y0, e.y);
        y1 = Math.max(y1, e.y);
      }
      return { x0, y0, x1, y1 };
    }

    /* Seçim/odak: diğer rotalar soluklaşır */
    highlight(id, type) {
      const cls = type === 'hover' ? 'top-hover' : 'selected';
      this.svg.classList.toggle('var-' + cls, id !== null && id !== undefined);
      for (const [rid, o] of this.routeEl) {
        const on = rid === id;
        o.g.classList.toggle(cls, on);
        o.gn.classList.toggle(cls, on);
        if (on) {
          this.gRoute.appendChild(o.g);
          this.gPoint.appendChild(o.gn);
        }
      }
      CM.$$('.route-label', this.gLabel).forEach((t) => t.classList.toggle(cls, String(t.dataset.id) === String(id)));
    }

    updateStop(rid, i, status, hint) {
      const els = this.stopEl.get(rid);
      const o = this.routeEl.get(rid);
      if (!els || !els[i]) return;
      CM.clear(els[i].el, markParts(status, o ? o.color : '#888', hint, this.opts.mini));
    }

    marker(lat, lng) {
      if (lat === null || lat === undefined) {
        if (this._marker) this._marker.el.style.display = 'none';
        return;
      }
      const x = this.p.x(lng),
        y = this.p.y(lat);
      if (!this._marker) {
        const g = CM.s('g', { class: 'marker' });
        g.appendChild(CM.s('path', { d: circle(11), class: 'i-hale' }));
        g.appendChild(CM.s('path', { d: circle(6.5), class: 'i-body' }));
        this.gTop.appendChild(g);
        this._marker = this._scaled(g, x, y);
      }
      const o = this._marker;
      o.x = x;
      o.y = y;
      o.el.style.display = '';
      o.el.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${(this.u || this._upp()).toFixed(3)})`);
    }

    ring(lat, lng) {
      if (lat === null || lat === undefined) {
        if (this._ring) this._ring.el.style.display = 'none';
        return;
      }
      const x = this.p.x(lng),
        y = this.p.y(lat);
      if (!this._ring) {
        const g = CM.s('g', { class: 'selection-ring' });
        g.appendChild(CM.s('path', { d: circle(9) }));
        this.gTop.insertBefore(g, this.gTop.firstChild);
        this._ring = this._scaled(g, x, y);
      }
      const o = this._ring;
      o.x = x;
      o.y = y;
      o.el.style.display = '';
      o.el.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${(this.u || this._upp()).toFixed(3)})`);
    }

    center(lat, lng) {
      const x = this.p.x(lng),
        y = this.p.y(lat);
      const v = this.vb;
      if (x > v.x + v.w * 0.12 && x < v.x + v.w * 0.88 && y > v.y + v.h * 0.12 && y < v.y + v.h * 0.88) return;
      this.vb = Object.assign({}, v, { x: x - v.w / 2, y: y - v.h / 2 });
      this._apply();
    }
  }

  CM.MapView = MapView;

  /* Harita lejantı (HTML; metin mürekkep renginde, işaret yanında) */
  CM.mapLegend = function (items) {
    const el = CM.h('div', { class: 'map-legend' });
    for (const o of items) {
      let sw;
      if (o.type === 'line') sw = CM.h('i', { class: 'lj-line', style: { background: o.color } });
      else if (o.type === 'block') sw = CM.h('i', { class: 'lj-block', style: { background: o.color } });
      else {
        const svg = CM.s('svg', { width: 14, height: 14, viewBox: '-7 -7 14 14', class: 'lj-mark' });
        CM.add(svg, [markParts(o.status, o.color || '#888', o.hint, false)]);
        sw = svg;
      }
      el.appendChild(CM.h('span', { class: 'lj' }, sw, o.text));
    }
    return el;
  };
})();
