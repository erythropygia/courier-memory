/* Sahne altyapısı: animasyonlu durum (S), harita sarmalayıcı (MapLibre ya da WebGL yoksa 2D tuval), işaretler, ortak UI. */
(function (CM) {
  // ------------------------------------------------------------ durum + ara değer (tween)
  const S = (CM.S = {});
  const tweens = new Map();
  let shelf = 0;
  CM.tween = function (target, ms = 900, ease = CM.easing.io) {
    const t0 = performance.now();
    for (const [k, v] of Object.entries(target)) {
      const a = S[k] ?? 0;
      if (ms <= 0 || a === v) { S[k] = v; tweens.delete(k); continue; }
      tweens.set(k, { a, b: v, t0, ms, ease });
    }
    CM.paint();
    if (!shelf) shelf = requestAnimationFrame(frame);
  };
  CM.adjust = (h) => CM.tween(h, 0);
  function frame(now) {
    shelf = 0;
    for (const [k, tw] of tweens) {
      const u = Math.min(1, (now - tw.t0) / tw.ms);
      S[k] = tw.a + (tw.b - tw.a) * tw.ease(u);
      if (u >= 1) tweens.delete(k);
    }
    CM.paint();
    if (tweens.size) shelf = requestAnimationFrame(frame);
  }
  CM.wait = (ms) => new Promise((r) => setTimeout(r, ms));

  // ------------------------------------------------------------ harita
  const H = (CM.H = { layers: new Map(), marks: new Set(), gl: false, map: null });

  function hasWebgl() {
    try {
      const c = document.createElement('canvas');
      return !!(c.getContext('webgl2') || c.getContext('webgl'));
    } catch (e) { return false; }
  }

  H.setup = async function (camera) {
    const force2D = new URLSearchParams(location.search).has('2d');
    H.gl = !force2D && hasWebgl() && !!window.maplibregl;
    if (!H.gl) return setup2D(camera);
    let local = !new URLSearchParams(location.search).has('online');
    if (local) {
      try { const r = await fetch('tiles/12/2379/1534.pbf', { method: 'HEAD' }); local = r.ok; } catch (e) { local = false; }
    }
    H.local = local;
    H.map = new maplibregl.Map({
      container: 'map', style: CM.style(local), interactive: false, attributionControl: false,
      maxPitch: 70, fadeDuration: 0, ...camera, pixelRatio: Math.min(2, window.devicePixelRatio || 1),
    });
    window.__map = H.map;
    await new Promise((r) => H.map.once('load', r));
  };

  H.firstLabel = () => (H.map && H.map.getLayer('water-name') ? 'water-name' : undefined);

  /* def: {id, tur: fill|line|circle, veri: GeoJSON, boya: (S, dk) => paint, kutu?: n, filtre?: ifade, layout?}
     Önemli: animasyon sırasında veriye bağlı (["get"…]) boya ifadesi DEĞİŞTİRİLMEZ (MapLibre her değişimde kaynağı
     yeniden döşer, işçi kuyruğu tıkanır). Dalga etkisi için özellikler gecikmelerine (d) göre "kutu"lara ayrılır;
     her kutu ayrı katmandır ve yalnız sabit opaklık alır. dk = kutunun ortalama gecikmesi. */
  function subtitles(k) { return k.box ? [...Array(k.box).keys()].map((i) => ({ id: `${k.id}#${i}`, i, mins: (i + 0.5) / k.box })) : [{ id: k.id, i: -1, mins: 0.5 }]; }
  function fitBox(k) {
    if (!k.box) return;
    for (const f of k.data.features) f.properties.b = Math.min(k.box - 1, Math.floor((f.properties.d || 0) * k.box));
  }
  function filtreOf(k, a) {
    const f = [];
    if (a.i >= 0) f.push(['==', ['get', 'b'], a.i]);
    if (k.filtre) f.push(k.filtre);
    return f.length === 0 ? null : f.length === 1 ? f[0] : ['all', ...f];
  }
  H.add = function (def) {
    const k = { ...def, last: {} };
    fitBox(k);
    H.layers.set(def.id, k);
    if (H.gl) {
      if (!H.map.getSource(def.id)) H.map.addSource(def.id, { type: 'geojson', data: k.data });
      for (const a of subtitles(k)) {
        const L = { id: a.id, type: def.type, source: def.id, layout: def.layout || {}, paint: def.paint(S, a.mins) };
        const f = filtreOf(k, a); if (f) L.filter = f;
        H.map.addLayer(L, def.once || H.firstLabel());
      }
    }
    CM.paint();
  };
  H.data = function (id, data) {
    const k = H.layers.get(id);
    if (!k) return;
    k.data = data;
    fitBox(k);
    if (H.gl) H.map.getSource(id).setData(data);
    CM.paint();
  };
  H.filtre = function (id, filtre) {
    const k = H.layers.get(id);
    if (!k || JSON.stringify(k.filtre) === JSON.stringify(filtre)) return;
    k.filtre = filtre;
    if (H.gl) for (const a of subtitles(k)) H.map.setFilter(a.id, filtreOf(k, a));
    CM.paint();
  };
  H.remove = function (id) {
    const k = H.layers.get(id);
    if (!k) return;
    H.layers.delete(id);
    if (H.gl) {
      for (const a of subtitles(k)) if (H.map.getLayer(a.id)) H.map.removeLayer(a.id);
      if (H.map.getSource(id)) H.map.removeSource(id);
    }
    CM.paint();
  };
  H.clear = function () {
    for (const id of [...H.layers.keys()]) H.remove(id);
    for (const m of [...H.marks]) m.remove();
  };

  let paintWaiting = false;
  CM.paint = function () {
    if (H.gl) {
      for (const k of H.layers.values()) {
        for (const a of subtitles(k)) {
          const p = k.paint(S, a.mins);
          for (let [name, v] of Object.entries(p)) {
            if (typeof v === 'number') { v = Math.round(v * 1e4) / 1e4; if (name.endsWith('opacity')) v = Math.min(1, Math.max(0, v)); }
            const s = JSON.stringify(v), key = a.id + '|' + name;
            if (k.last[key] !== s) { k.last[key] = s; H.map.setPaintProperty(a.id, name, v); }
          }
        }
      }
    } else if (!paintWaiting) {
      paintWaiting = true;
      requestAnimationFrame(() => { paintWaiting = false; draw2D(); });
    }
  };

  // kamera: MapLibre'de uçuş, 2D'de yok sayılır (tüm alan sabit çerçevede)
  H.end = function (k, ms = 2600) {
    if (!H.gl) return;
    H.map.flyTo({ ...k, duration: ms, essential: true, curve: 1.3, easing: CM.easing.io });
  };
  H.skip = function (k) { if (H.gl) H.map.jumpTo(k); };

  // ------------------------------------------------------------ HTML işaretleri (araç, şube, etiket)
  H.mark = function (el, lngLat, anchor = 'center') {
    const m = { el, ll: lngLat, op: 1 };
    if (H.gl) {
      m.mk = new maplibregl.Marker({ element: el, anchor }).setLngLat(lngLat).addTo(H.map);
    } else {
      el.style.position = 'fixed';
      el.style.transform = 'translate(-50%,-50%)';
      document.body.appendChild(el);
    }
    m.position = (ll) => { m.ll = ll; if (m.mk) m.mk.setLngLat(ll); else place2D(m); };
    // MapLibre işaretin opaklığını kendisi de yazar (perspektif örtmesi): gizlemek için görünürlük de ayarlanır
    m.transparent = (o) => { m.op = o; el.style.opacity = o; el.style.visibility = o <= 0.01 ? 'hidden' : ''; };
    m.remove = () => { if (m.mk) m.mk.remove(); else el.remove(); H.marks.delete(m); };
    H.marks.add(m);
    if (!H.gl) place2D(m);
    return m;
  };
  // işareti bir yol boyunca yürüt (ll dizisi), süre ms
  H.execute = function (m, path, ms, ease = CM.easing.io) {
    return new Promise((res) => {
      const L = [0];
      for (let i = 1; i < path.length; i++) L.push(L[i - 1] + Math.hypot(path[i][0] - path[i - 1][0], (path[i][1] - path[i - 1][1]) * 1.32));
      const tot = L[L.length - 1] || 1, t0 = performance.now();
      const step = (now) => {
        const u = ease(Math.min(1, (now - t0) / ms)), s = u * tot;
        let i = 1; while (i < L.length - 1 && L[i] < s) i++;
        const f = (s - L[i - 1]) / ((L[i] - L[i - 1]) || 1);
        m.position([path[i - 1][0] + (path[i][0] - path[i - 1][0]) * f, path[i - 1][1] + (path[i][1] - path[i - 1][1]) * f]);
        if (u < 1 && !m.dur) requestAnimationFrame(step); else res();
      };
      requestAnimationFrame(step);
    });
  };

  // ------------------------------------------------------------ 2D yedek
  let cv, cx, proj;
  function setup2D() {
    cv = document.getElementById('canvas');
    cv.hidden = false;
    document.getElementById('map').hidden = true;
    cx = cv.getContext('2d');
    const size = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      cv.width = innerWidth * dpr; cv.height = innerHeight * dpr;
      cx.setTransform(dpr, 0, 0, dpr, 0, 0);
      H.frame(H.coverage || [29.06, 41.04, 29.34, 41.24]);
    };
    window.addEventListener('resize', size);
    size();
  }
  const merc = (lng, lat) => [(lng + 180) / 360, (1 - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) / Math.PI) / 2];
  H.frame = function (b) {
    H.coverage = b;
    if (H.gl) return;
    const [x0, y1] = merc(b[0], b[1]), [x1, y0] = merc(b[2], b[3]);
    const pad = { l: innerWidth * 0.08, r: innerWidth * 0.08, t: innerHeight * 0.1, b: innerHeight * 0.16 };
    const sc = Math.min((innerWidth - pad.l - pad.r) / (x1 - x0), (innerHeight - pad.t - pad.b) / (y1 - y0));
    const ox = pad.l + (innerWidth - pad.l - pad.r - (x1 - x0) * sc) / 2, oy = pad.t + (innerHeight - pad.t - pad.b - (y1 - y0) * sc) / 2;
    proj = (ll) => { const [x, y] = merc(ll[0], ll[1]); return [ox + (x - x0) * sc, oy + (y - y0) * sc]; };
    CM.paint();
  };
  function place2D(m) {
    if (!proj) return;
    const [x, y] = proj(m.ll);
    m.el.style.left = x + 'px'; m.el.style.top = y + 'px';
  }
  function color(c, a) {
    if (a >= 0.999) return c;
    const h = c.replace('#', '');
    const n = parseInt(h.length === 3 ? h.split('').map((q) => q + q).join('') : h, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }
  function draw2D() {
    if (!cx || !proj) return;
    cx.fillStyle = CM.MAP_COLOR.land;
    cx.fillRect(0, 0, innerWidth, innerHeight);
    const ev = CM.evaluate;
    for (const k of H.layers.values()) {
      const pk = {};
      for (const f of k.data.features) {
        const pr = f.properties;
        if (k.filtre && !ev(k.filtre, pr)) continue;
        const bi = k.box ? pr.b : -1;
        const p = pk[bi] || (pk[bi] = k.paint(S, k.box ? (bi + 0.5) / k.box : 0.5));
        if (k.type === 'fill' || k.type === 'line') {
          const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates : f.geometry.type === 'LineString' ? [[f.geometry.coordinates]] : [];
          cx.beginPath();
          for (const poly of polys) for (const ring of poly) ring.forEach((c, i) => { const [x, y] = proj(c); i ? cx.lineTo(x, y) : cx.moveTo(x, y); });
          if (k.type === 'fill') {
            const o = ev(p['fill-opacity'] ?? 1, pr);
            if (o > 0.003) { cx.fillStyle = color(ev(p['fill-color'], pr), o); cx.fill('evenodd'); }
          } else {
            const o = ev(p['line-opacity'] ?? 1, pr);
            if (o > 0.003) { cx.strokeStyle = color(ev(p['line-color'], pr), o); cx.lineWidth = ev(p['line-width'] ?? 1, pr); cx.lineJoin = 'round'; cx.stroke(); }
          }
        } else if (k.type === 'circle') {
          const o = ev(p['circle-opacity'] ?? 1, pr);
          if (o <= 0.003) continue;
          const [x, y] = proj(f.geometry.coordinates);
          const r = ev(p['circle-radius'] ?? 3, pr);
          cx.beginPath(); cx.arc(x, y, Math.max(0.5, r), 0, Math.PI * 2);
          cx.fillStyle = color(ev(p['circle-color'], pr), o); cx.fill();
          const sw = ev(p['circle-stroke-width'] ?? 0, pr);
          if (sw > 0) { cx.lineWidth = sw; cx.strokeStyle = color(ev(p['circle-stroke-color'] ?? '#fff', pr), ev(p['circle-stroke-opacity'] ?? o, pr)); cx.stroke(); }
        }
      }
    }
    for (const m of H.marks) place2D(m);
  }

  // ------------------------------------------------------------ geojson yardımcıları
  CM.gj = (features) => ({ type: 'FeatureCollection', features });
  CM.point = (lat, lng, props) => ({ type: 'Feature', properties: props, geometry: { type: 'Point', coordinates: [lng, lat] } });
  CM.multi = (rings, props) => ({ type: 'Feature', properties: props, geometry: { type: 'MultiPolygon', coordinates: rings } });
  CM.line = (latlngs, props) => ({ type: 'Feature', properties: props, geometry: { type: 'LineString', coordinates: latlngs.map((q) => [q[1], q[0]]) } });

  // ------------------------------------------------------------ ortak UI
  const $ = (id) => document.getElementById(id);
  CM.$ = $;
  const fmt = new Intl.NumberFormat('tr-TR');
  CM.count = (x, nd = 0) => new Intl.NumberFormat('tr-TR', { minimumFractionDigits: nd, maximumFractionDigits: nd }).format(x);
  CM.percent = (x) => '%' + Math.round(x * 100);
  CM.fmt = fmt;

  // stats: [{v, l, cls}], not: metin, birim: {dolu, bos}
  CM.figure = function (stats, note, extra) {
    const box = $('figure');
    if (!stats || !stats.length) { box.innerHTML = ''; return; }
    const sat = document.createElement('div');
    sat.className = 'row';
    for (const s of stats) {
      const d = document.createElement('div');
      d.className = 'stat ' + (s.cls || '');
      d.innerHTML = `<div class="v ${s.boy || ''}">${s.v}</div><div class="l">${s.l}</div>`;
      if (s.unit) {
        const b = document.createElement('div'); b.className = 'unit';
        for (let i = 0; i < s.unit.full + s.unit.empty; i++) { const q = document.createElement('i'); if (i >= s.unit.full) q.className = 'empty'; b.appendChild(q); }
        d.appendChild(b);
      }
      sat.appendChild(d);
    }
    box.innerHTML = '';
    box.appendChild(sat);
    if (note) { const n = document.createElement('div'); n.className = 'note'; n.innerHTML = note; box.appendChild(n); }
    requestAnimationFrame(() => requestAnimationFrame(() => {
      [...sat.children].forEach((c, i) => setTimeout(() => c.classList.add('view'), i * 140));
      const n = box.querySelector('.note'); if (n) n.classList.add('view');
    }));
    if (extra) extra(box);
  };
  CM.message = function (rows) {
    const m = $('message');
    m.innerHTML = (rows || []).map((s) => `<p>${s}</p>`).join('');
    [...m.children].forEach((p, i) => setTimeout(() => p.classList.add('view'), 120 + i * 500));
  };
  CM.action = function (html, up) { $('action').innerHTML = html || ''; document.body.classList.toggle('actionable', !!(html && up)); };
  CM.cards = function (html) { $('cards').innerHTML = html || ''; };

  // araç işareti (özgün: kare gövde + yön çentiği, kurye renginde)
  CM.toolEl = function (color, name) {
    const el = document.createElement('div');
    el.className = 'tool';
    el.innerHTML = `<svg viewBox="0 0 40 40"><rect x="5" y="9" width="30" height="22" fill="${color}" stroke="#1A1714" stroke-width="2.5"/>` +
      `<path d="M27 9 L35 9 L35 20 L27 20 Z" fill="#FBF8F2" stroke="#1A1714" stroke-width="2.5"/>` +
      `<rect x="10" y="29" width="6" height="6" fill="#1A1714"/><rect x="24" y="29" width="6" height="6" fill="#1A1714"/></svg>` +
      (name ? `<span>${name}</span>` : '');
    return el;
  };
  CM.branchEl = function () {
    const el = document.createElement('div');
    el.className = 'branch';
    el.innerHTML = '<i></i><span>ŞUBE</span>';
    return el;
  };
})(window.CM);
