/* Sahne 2 · Sabah: orkestratör canlı çalışır. İz API'den (SSE, yoksa poll; API yoksa kayıtlı iz) gelir,
   her araç adımı bir "vuruş"tur ve haritada karşılık bulur. Sunucu → ile vuruş vuruş ilerler. Müdür önerisinde durur. */
(function (CM) {
  const API = new URLSearchParams(location.search).get('api') || (location.pathname.match(/^(.*?\/proxy\/\d+)\//) || [])[1] || '';
  const DAY = 32;
  const TYPES = ['start', 'decision', 'tool', 'result', 'error', 'fallback', 'proposal', 'awaiting_approval', 'human_decision', 'response', 'done'];
  const GROUP = { delivery_time_analysis: 'time', apply_time_constraint: 'time', time_alternatives: 'time', present_proposal: 'proposal' };
  const INK = '#3A332D';

  let data = null, match = null, branch = null;
  let session = null;              // {olaylar, bitti, kaynak, mod, id, es}
  let shown = -1, requested = -1, displayNo = 0;
  let tools = {};             // id → işaret
  const color = (r) => CM.PALET[r % CM.PALET.length];

  // ------------------------------------------------------------ iz kaynağı
  async function timed(url, opt = {}, ms = 2500) {
    const open = new AbortController();
    const t = setTimeout(() => open.abort(), ms);
    try { return await fetch(url, { ...opt, signal: open.signal }); } finally { clearTimeout(t); }
  }
  async function startSession() {
    const k = { events: [], done: false, source: 'api', mod: '', id: null };
    session = k;
    try {
      const d = await (await timed(API + '/api/status')).json();
      k.mod = d.mode;
      await timed(API + '/api/memory/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ day: DAY }) }, 8000).catch(() => null);
      const r = await timed(API + '/api/orchestrator/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ day: DAY }) }, 8000);
      if (!r.ok) throw new Error('baslat ' + r.status);
      const oz = await r.json();
      k.id = oz.session_id;
      CM.session2 = { id: k.id, source: 'api' };
      writeMode(k);
      stream(k);
    } catch (e) {
      console.warn('API yok, kayıtlı iz oynatılıyor:', e);
      k.source = 'record';
      writeMode(k);
      const d = await (await fetch('data/trace_fallback.json')).json();
      k.id = d.session_id;
      CM.session2 = { id: k.id, source: 'record' };
      for (const ev of d.events) { if (session !== k) return; await CM.wait(90); addEvent(k, ev); }
      k.done = true; update();
    }
  }
  function stream(k) {
    if (!window.EventSource) return poll(k);
    const es = new EventSource(`${API}/api/orchestrator/session/${k.id}/stream?tempo_ms=0`);
    k.es = es;
    TYPES.forEach((t) => es.addEventListener(t, (m) => addEvent(k, JSON.parse(m.data))));
    es.addEventListener('last', () => { k.done = true; es.close(); update(); });
    es.onerror = () => { if (!k.done) { es.close(); poll(k); } };
  }
  async function poll(k) {
    while (session === k && !k.done) {
      try {
        const d = await (await timed(`${API}/api/orchestrator/session/${k.id}?after=${k.events.length}`)).json();
        d.events.forEach((e) => addEvent(k, e));
        if (d.status !== 'running') { k.done = true; break; }
      } catch (e) { /* tekrar dene */ }
      await CM.wait(400);
    }
    update();
  }
  function addEvent(k, e) {
    if (session !== k || k.events.some((x) => x.i === e.i)) return;
    k.events.push(e);
    k.events.sort((a, b) => a.i - b.i);
    update();
  }
  function writeMode(k) {
    const m = CM.$('mod');
    const name = { mock: 'mock · kurallı yedek', live: 'canlı · LLM', record: 'canlı · kayıt', replay: 'kayıttan · LLM' }[k.mod] || k.mod;
    m.textContent = k.source === 'record' ? 'API yok · kayıtlı iz' : 'Mod: ' + name;
    m.classList.toggle('live', k.mod === 'live' || k.mod === 'record');
  }

  // olaylar → vuruşlar: her araç çağrısı (aynı gruptaki ardışık çağrılar birlikte) bir vuruş; karar satırları sonraki vuruşa
  function beats() {
    if (!session) return [];
    const out = [];
    let pending = [];
    for (const e of session.events) {
      if (e.type === 'tool') {
        const g = GROUP[e.tool] || e.tool;
        const last = out[out.length - 1];
        if (last && last.group === g) last.events.push(...pending, e);
        else out.push({ group: g, events: [...pending, e] });
        pending = [];
      } else if (e.type === 'decision' || e.type === 'start') pending.push(e);
      else if (out.length) out[out.length - 1].events.push(...pending, e), (pending = []);
      else pending.push(e);
    }
    if (pending.length && out.length) out[out.length - 1].events.push(...pending);
    out.forEach((v, i) => {
      const tool = v.events.filter((e) => e.type === 'tool').length, result = v.events.filter((e) => e.type === 'result' || e.type === 'error').length;
      v.full = session.done || i < out.length - 1 || (v.group === 'proposal' ? v.events.some((e) => e.type === 'awaiting_approval') : result >= tool);
    });
    return out;
  }
  const resultOf = (v, tool) => v.events.filter((e) => e.type === 'result' && (!tool || e.tool === tool));

  function update() {
    const V = beats();
    CM.$('trace-wait').hidden = !(requested > shown && !(V[requested] && V[requested].full));
    if (requested > shown && V[requested] && V[requested].full) show(requested, true);
    drawStep();
  }
  function drawStep() {
    const V = beats();
    const n = Math.max(8, V.length + 1);
    CM.drawStep(n, shown + 1);
  }

  // ------------------------------------------------------------ iz paneli
  const row = (e) => CM.traceRow(e);
  function drawTrace(k, next) {
    const V = beats(), ul = CM.$('trace-list');
    ul.innerHTML = '';
    const no = displayNo;
    V.slice(0, k + 1).forEach((v, vi) => {
      v.events.forEach((e, j) => {
        const li = row(e);
        if (vi < k) li.classList.add('legacy', 'view');
        ul.appendChild(li);
        if (vi === k) {
          if (next) setTimeout(() => no === displayNo && li.classList.add('view'), 120 + j * 260);
          else li.classList.add('view');
        }
      });
    });
    // taşan eski satırları at (liste alttan dolar)
    while (ul.children.length > 26) ul.removeChild(ul.firstChild);
  }

  // ------------------------------------------------------------ harita
  function camera() {
    if (!CM.H.gl) return null;
    const w = innerWidth, h = innerHeight;
    const c = CM.H.map.cameraForBounds([[29.064, 41.047], [29.332, 41.235]], { padding: { left: w * 0.24, right: w * 0.24, top: h * 0.05, bottom: h * 0.12 }, bearing: -8 });
    return { center: c.center, zoom: c.zoom + 0.3, pitch: 42, bearing: -8 };
  }
  function routeCamera(seq) {
    const lng = seq.map((q) => q[1]), lat = seq.map((q) => q[0]);
    const w = innerWidth, h = innerHeight;
    const c = CM.H.map.cameraForBounds([[Math.min(...lng), Math.min(...lat)], [Math.max(...lng), Math.max(...lat)]],
      { padding: { left: w * 0.3, right: w * 0.3, top: h * 0.18, bottom: h * 0.24 }, bearing: -20 });
    return { center: c.center, zoom: Math.min(15.2, c.zoom + 0.2), pitch: 56, bearing: -20 };
  }
  const degree = (a, b) => Math.hypot((a[0] - b[0]) * 111, (a[1] - b[1]) * 84);

  function setupTool(candidates, proposed) {
    for (const a of candidates) {
      if (!proposed.includes(a.id) || tools[a.id]) continue;
      const m = CM.H.mark(CM.toolEl(color(a.target_cluster), a.name), [0, 0], 'center');
      m.candidate = a;
      tools[a.id] = m;
    }
  }
  function toolEntry(a) {
    const dep = [data.depot[1], data.depot[0]];
    const yon = { O01: 'east', O02: 'north' }[a.id] || 'east'; // senaryo: O01 doğu sınırı, O02 kuzey sınırı (sim/config/scenarios/borrowed_courier.yaml)
    return yon === 'north' ? [dep[0] + 0.01, dep[1] + 0.12] : [dep[0] + 0.2, dep[1] + 0.01];
  }
  function clusterPoint(r) {
    const R = data.routes.find((x) => x.route === r);
    return R && R.at ? [R.at[1], R.at[0]] : [data.depot[1], data.depot[0]];
  }
  function positionTools(phase, next) {
    const dep = [data.depot[1], data.depot[0]];
    for (const m of Object.values(tools)) {
      const a = m.candidate;
      m.dur = true;
      if (phase === 'hidden') { m.transparent(0); continue; }
      m.transparent(1);
      const target = phase === 'cluster' ? clusterPoint(a.target_cluster) : [dep[0] - 0.004, dep[1] + 0.012 * a.order];
      if (!next) { m.position(target); continue; }
      m.dur = false;
      const head = phase === 'cluster' ? dep : toolEntry(a);
      m.position(head);
      CM.H.execute(m, [head, target], phase === 'cluster' ? 2600 : 3200 + (a.order - 1) * 500);
    }
  }

  // ------------------------------------------------------------ vuruş gösterimi
  function show(k, next) {
    const V = beats();
    shown = k;
    displayNo++;
    CM.$('trace-wait').hidden = true;
    CM.$('trace').hidden = false;
    requestAnimationFrame(() => CM.$('trace').classList.add('open'));
    drawTrace(k, next);
    drawStep();
    const flag = new Set(V.slice(0, k + 1).map((v) => v.group));
    const v = V[k], g = v.group;
    if (CM.drawNarration) CM.drawNarration(2, g);
    const volume = flag.has('read_volume'), assignment = flag.has('core_assignment'), candidate = flag.has('neighbor_candidates');
    const hist = next ? 1 : 0.35;
    CM.tween({ v26: volume ? 0 : 1 }, 1400 * hist);
    CM.tween({ v32: volume ? 1 : 0 }, 2600 * hist, CM.easing.out);
    CM.tween({ ter: assignment ? 1 : 0, color: assignment ? 1 : 0 }, 2800 * hist);
    CM.tween({ time: flag.has('time') ? 1 : 0 }, 900 * hist);
    CM.tween({ focus: g === 'compute_route' ? 1 : 0 }, 700);
    CM.cards('');
    CM.action('');
    if (g !== 'compute_route') CM.H.end(camera(), next ? 2200 : 900);

    // araçlar
    const nameV = V.find((x) => x.group === 'neighbor_candidates');
    const nameS = nameV && resultOf(nameV, 'neighbor_candidates')[0];
    if (nameS) setupTool(nameS.data.candidates, nameS.data.proposed);
    const newPhase = !candidate ? 'hidden' : assignment ? 'cluster' : 'branch';
    positionTools(newPhase, next && ((g === 'neighbor_candidates' && newPhase === 'branch') || (g === 'core_assignment' && newPhase === 'cluster')));

    if (flag.has('time')) S2.timePoints();
    const s = resultOf(v)[0];
    const x = s && s.data;
    if (g === 'read_volume' && x) {
      CM.figure([{ v: (x.volume_diff >= 0 ? '+%' : '−%') + Math.round(Math.abs(x.volume_diff) * 100), l: 'gönderi' }],
        `${CM.fmt.format(x.shipment)} gönderi · olağan ${x.weekday} ${CM.fmt.format(x.usual_shipments)} · ${CM.fmt.format(x.stop)} durak`);
    } else if (g === 'capacity_gap' && x) {
      CM.figure([{ v: x.shortfall, l: 'kurye eksik', cls: x.shortfall > 0 ? 'red' : '', unit: { full: x.local_available, empty: x.shortfall } }],
        `${x.required_courier_day} kurye-gün gerekli · yerelde ${x.local_available} müsait`);
    } else if (g === 'neighbor_candidates' && x) {
      CM.figure([]);
      const card = x.candidates.slice().sort((a, b) => a.order - b.order).map((a) => {
        const select = x.proposed.includes(a.id);
        return `<div class="card ${select ? 'picked' : 'unselected'}"><div class="top"><span>${a.order}.</span><span>${select ? 'önerildi' : 'gelmesin'}</span></div>` +
          `<div class="name">${select ? `<b style="background:${color(a.target_cluster)}"></b>` : ''}${a.name}</div>` +
          `<div class="p">${CM.percent(a.familiar_share)}</div><div class="pl">tanıdık durak</div><div class="bar"><i data-w="${a.familiar_share}"></i></div></div>`;
      }).join('');
      CM.cards(`<div class="title">Kim gitsin? · komşu şubeden aday</div>${card}`);
      [...CM.$('cards').querySelectorAll('.card')].forEach((c, i) => setTimeout(() => {
        c.classList.add('view');
        const b = c.querySelector('.bar i'); b.style.width = Math.round(parseFloat(b.dataset.w) * 100) + '%';
      }, (next ? 300 : 0) + i * 220));
    } else if (g === 'core_assignment' && x) {
      CM.figure([{ v: x.total.courier_count, l: 'kurye' }, { v: CM.percent(x.own_zone_share), l: 'kendi bölgesinde' }],
        `Çekirdek bölgeli atama · beklenen başarısız ${CM.count(x.total.expected_fails, 1)} (geçmişe bakmadan ${CM.count(x.history_blind_expected_fails, 1)})`);
    } else if (g === 'time') {
      const a = resultOf(v, 'delivery_time_analysis')[0], u = resultOf(v, 'apply_time_constraint')[0];
      const n = u ? u.data.applied : a ? a.data.fits_route : 0;
      const z = resultOf(v, 'time_alternatives')[0];
      const k = z && z.data.unshiftable ? ` · ${z.data.unshiftable} durak rota uzamadan kaydırılamadı → müdüre alternatif` : '';
      CM.figure([{ v: n, l: 'adreste teslim saati kaydırıldı' }],
        (a ? `Teslim kayıtlarından saat örüntüsü · ${a.data.confirmation_pending} adres kuryeye sorulacak` : '') + k);
    } else if (g === 'sorting_plan' && x) {
      CM.figure([{ v: x.departure.presorted, l: 'tahmini çıkış' }, { v: x.shelf_count, l: 'raf' }],
        `Ayrıştırma indirme okutmasında: kurye ayrıştırma yapmaz · bugünkü süreçte çıkış ${x.departure.today}`);
    } else if (g === 'compute_route') {
      routeOrder(v, next);
    } else if (g === 'proposal') {
      const o = (v.events.find((e) => e.type === 'proposal') || {}).proposal;
      if (o) {
        CM.figure([{ v: o.assignment.length, l: 'kurye' }, { v: o.borrowed.length, l: 'komşu şubeden' }, { v: CM.percent(o.own_zone_share), l: 'kendi bölgesinde' }],
          o.borrowed.map((q) => q.name).join(' ve ') + ' gelsin · karar müdürde');
      }
      CM.action('<button class="approval" id="approve">Müdür ekranı <span class="kbd">→</span></button><span class="hint">Karar müdürde: onay ve “Onur gelmezse?” sorusu</span>', true);
      CM.$('approve').onclick = () => CM.openScene && CM.openScene(3);
    } else {
      CM.figure([]);
    }
  }

  async function routeOrder(v, next) {
    const no = displayNo;
    const rs = resultOf(v, 'compute_route');
    for (let i = 0; i < rs.length; i++) {
      if (no !== displayNo) return;
      if (!next && i < rs.length - 1) continue;
      const r = rs[i].data;
      const R = data.routes.find((q) => q.route === r.cluster);
      if (!R) continue;
      for (const id of ['s2-ter-o', 's2-ter-oc', 's2-p32o']) CM.H.filtre(id, ['==', ['get', 'r'], r.cluster]);
      CM.H.end(routeCamera(R.seq), next ? 2000 : 800);
      const type = { borrowed: 'komşu şubeden', new: 'yeni kurye', reserve: 'yedek' }[r.courier_type] || '';
      CM.figure([{ v: r.estimated_return, l: `${r.name} · tahmini dönüş` }, { v: r.stop, l: 'durak' }],
        `Küme ${r.cluster} · ${CM.count(r.km, 1)} km · beklenen ${Math.round(r.expected_min)} dk (planlanan ${Math.round(r.planned_min)}) ${type ? '· ' + type : ''}`);
      if (i < rs.length - 1) await CM.wait(3600);
    }
  }

  // ------------------------------------------------------------ sahne
  const S2 = {
    no: 2, name: 'Sabah', stepCount: 8,
    title: 'Gün 32 · Çarşamba sabahı · orkestratör günü planlıyor',
    attribution: '<b>Uygulama verisi · 1 aylık geçmiş</b> · Harita: OpenStreetMap (OpenFreeMap © OpenMapTiles) · konumlar Beykoz saha verisi · sonuçlar simülasyon',

    async enter() {
      if (!data) {
        [data, match] = await Promise.all([fetch('data/scene2.json').then((r) => r.json()), fetch('data/sim_mapping.json').then((r) => r.json())]);
      }
      CM.adjust({ v26: 0, v32: 0, ter: 0, color: 0, time: 0, focus: 0 });
      CM.H.frame([29.064, 41.047, 29.332, 41.235]);
      const dep = data.depot;
      const dd = (la, lo) => Math.min(1, degree([la, lo], dep) / 16);
      const ter = CM.gj(data.routes.filter((r) => r.rings.length).map((r) => CM.multi(r.rings, { c: color(r.route), r: r.route, d: dd(r.at[0], r.at[1]) })));
      const p26 = CM.gj(data.pts26.map((p) => CM.point(p[0], p[1], { d: dd(p[0], p[1]) })));
      const p32 = CM.gj(data.pts32.map((p) => CM.point(p[0], p[1], { c: color(p[2]), r: p[2], d: dd(p[0], p[1]) })));
      const rad = ['interpolate', ['linear'], ['zoom'], 10, 1.8, 11, 2.2, 13, 3.2, 16, 6];
      const g = CM.dg, NB = 10, NF = 8, H = CM.H;
      const fill = (o) => ({ 'fill-color': ['get', 'c'], 'fill-opacity': 0.3 * o });
      const line = (o) => ({ 'line-color': ['get', 'c'], 'line-width': 1.6, 'line-opacity': 0.95 * o });
      const dot = (color, o, sw = 0.7) => ({ 'circle-radius': rad, 'circle-color': color, 'circle-opacity': o, 'circle-stroke-color': '#FBF8F2', 'circle-stroke-width': sw, 'circle-stroke-opacity': o });
      const offline = ['==', ['get', 'r'], -999];
      // bölgeler (atamada dalgayla), odaktaki küme ayrı katmanda (filtre yalnız odak değişince güncellenir)
      H.add({ id: 's2-ter', type: 'fill', data: ter, box: NF, paint: (S, mins) => fill(g(S.ter, mins) * (1 - 0.8 * S.focus)) });
      H.add({ id: 's2-ter-c', type: 'line', data: ter, box: NF, paint: (S, mins) => line(g(S.ter, mins) * (1 - 0.7 * S.focus)) });
      H.add({ id: 's2-ter-o', type: 'fill', data: ter, filtre: offline, paint: (S) => fill(S.focus * 1.3) });
      H.add({ id: 's2-ter-oc', type: 'line', data: ter, filtre: offline, paint: (S) => ({ ...line(S.focus), 'line-width': 2.6 }) });
      // olağan gün (gün 26) → bugün (gün 32): talep yoğunlaşır; atamada mürekkep → küme rengi
      H.add({ id: 's2-p26', type: 'circle', data: p26, paint: (S) => dot(INK, 0.6 * S.v26, 0) });
      H.add({ id: 's2-p32m', type: 'circle', data: p32, box: NB, paint: (S, mins) => dot(INK, g(S.v32, mins) * (1 - g(S.color, mins)) * (1 - 0.8 * S.focus)) });
      H.add({ id: 's2-p32', type: 'circle', data: p32, box: NB, paint: (S, mins) => dot(['get', 'c'], g(S.v32, mins) * g(S.color, mins) * (1 - 0.8 * S.focus)) });
      H.add({ id: 's2-p32o', type: 'circle', data: p32, filtre: offline, paint: (S) => dot(['get', 'c'], S.focus, 1) });
      H.add({ id: 's-2-time', type: 'circle', data: CM.gj([]), paint: (S) => ({ 'circle-radius': 12, 'circle-color': '#FBF8F2', 'circle-opacity': 0.0,
        'circle-stroke-color': '#1A1714', 'circle-stroke-width': 3, 'circle-stroke-opacity': S.time * (1 - 0.8 * S.focus) }) });
      branch = H.mark(CM.branchEl(), [dep[1], dep[0]], 'left');
      CM.$('trace').hidden = false;
      CM.$('trace').querySelector('.trace-head span').textContent = 'Orkestratör izi';
      CM.$('trace-list').innerHTML = '';
      this.restart(true);
    },

    // zaman bulgusu adresleri: iz geldikçe eşlemeden
    timePoints() {
      const V = beats(), v = V.find((x) => x.group === 'time');
      const a = v && resultOf(v, 'delivery_time_analysis')[0];
      const f = [];
      if (a) for (const b of a.data.findings || []) {
        if (!b.fits_route) continue;
        const q = match.address['a' + b.address];
        if (q) f.push(CM.point(q[0], q[1], {}));
      }
      CM.H.data('s-2-time', CM.gj(f));
    },

    restart(first) {
      if (session && session.es) session.es.close();
      session = null;
      for (const m of Object.values(tools)) m.remove();
      tools = {};
      CM.$('trace-list').innerHTML = '';
      CM.$('mod').textContent = '';
      this.empty(first);
    },
    empty(first) {
      shown = -1; requested = -1; displayNo++;
      if (CM.drawNarration) CM.drawNarration(2, 'empty');
        for (const m of Object.values(tools)) m.transparent(0);
      CM.$('trace-wait').hidden = true;
      CM.$('trace').classList.remove('open');
      CM.cards(''); CM.figure([]);
      CM.tween({ v26: 1, v32: 0, ter: 0, color: 0, time: 0, focus: 0 }, first ? 1600 : 700);
      CM.H.end(camera(), first ? 1800 : 900);
      CM.action('<button id="plan">Günü planla <span class="kbd">→</span></button><span class="hint">Harita: olağan bir Çarşamba sabahı</span>');
      CM.$('plan').onclick = () => this.next();
      drawStep();
    },

    next() {
      if (!session) { startSession(); }
      const V = beats();
      if (shown >= 0 && V[shown] && V[shown].group === 'proposal') return false;
      requested = shown + 1;
      CM.action('');
      update();
      if (requested > shown) CM.$('trace-wait').hidden = false, CM.$('trace').classList.add('open');
      return true;
    },
    back() {
      if (shown < 0) return false;
      if (shown === 0) { this.empty(); return true; }
      requested = shown - 1;
      show(requested, false);
      return true;
    },
    leaving() {
      if (session && session.es) session.es.close();
      session = null;
      for (const m of Object.values(tools)) m.remove();
      tools = {};
      if (branch) branch.remove();
      CM.$('trace').classList.remove('open');
      CM.cards(''); CM.figure([]); CM.action('');
      CM.H.clear();
    },
  };
  CM.scenes = CM.scenes || {};
  CM.scenes[2] = S2;
})(window.CM);
