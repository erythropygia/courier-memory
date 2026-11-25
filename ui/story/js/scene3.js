/* Sahne 3 · Acil durum: müdür ekranı. Zincir normalde temassızdır (Sahne 2: plan müdüre gitmeden kesinleşir); müdür yalnız
   acil durumda yetkilidir (kapasite açığı kapanmıyor, ciddi fazla mesai, ajan planı çıkaramadı ya da müdür acil durum bildirdi).
   Burada müdür acil durum bildirir (manager_review): orkestratörün önerisi (gerekçe), riskler (bant üstü ilk 3, kaydırılamayan
   teslim saati → alternatif + SMS), "Onur gelmezse?" sorusu (ajan iki yolu araçla hesaplar), insan onayı. Eskale edilmiş bir
   Sahne 2 koşusu varsa devralınır; yoksa /api/orchestrator/plan {manager_review: true} ile yenisi açılır. API yoksa kayıtlı
   yanıtlar (data/fallback.json). */
(function (CM) {
  const DAY = 32;
  let data = null, session = null, proposal = null, ask = null, decision = null, trace = [];
  let marks = [], no = 0;
  const color = (r) => CM.PALET[r % CM.PALET.length];
  const cluster = (ids) => ['match', ['get', 'r'], ids.length ? ids : [-999], true, false];

  async function getSession() {
    const k2 = CM.session2;
    if (k2 && k2.id && !CM.apiStatus.offline && k2.source === 'api') {
      try {
        const d = await CM.api(`/api/orchestrator/session/${k2.id}`);
        if (d.status === 'awaiting_approval') return d;          // Sahne 2'nin koşusu zaten eskale edildiyse
      } catch (e) { /* yeni koşu */ }
    }
    CM.waitTrace(true);
    // müdür acil durum bildirdi: plan temassız kesinleşmez, müdürün kararını bekler
    try { return await CM.api('/api/orchestrator/plan', { day: DAY, manager_review: true }, { ms: 120000 }); } finally { CM.waitTrace(false); }
  }

  function camera() {
    if (!CM.H.gl) return null;
    const w = innerWidth, h = innerHeight;
    const c = CM.H.map.cameraForBounds([[29.064, 41.047], [29.332, 41.235]], { padding: { left: w * 0.06, right: w * 0.34, top: h * 0.08, bottom: h * 0.2 }, bearing: -8 });
    return { center: c.center, zoom: c.zoom + 0.25, pitch: 30, bearing: -8 };
  }
  function at(r) { const R = data.routes.find((x) => x.route === r); return R && R.at ? [R.at[1], R.at[0]] : null; }
  function label(r, top, alt, css_class) {
    const ll = at(r);
    if (!ll) return;
    marks.push(CM.H.mark(CM.labelEl(top, alt, css_class), ll, 'bottom'));
  }
  function highlight(ids, ms = 700) {
    CM.H.filtre('s-3-hit', cluster(ids));
    CM.H.filtre('s-3-hit-c', cluster(ids));
    CM.tween({ s3Hit: ids.length ? 1 : 0 }, ms);
  }

  function sideRationale() {
    const g = (proposal.rationale || []).map((s) => `<li>${CM.escape(s)}</li>`).join('');
    CM.side(`<div class="side-head"><span>Müdür ekranı · acil durum</span><span class="mod" id="mod3"></span></div>
      <div class="side-inner"><div class="y-title">Gerekçe</div><ol class="rationale">${g}</ol></div>`, 'open');
    CM.writeMode(CM.$('mod3'));
  }
  function sideRisk() {
    const alt = (proposal.time_alternatives || [])[0];
    const r = (proposal.risks || []).map((s) => `<li>${CM.escape(s)}</li>`).join('');
    const SELECT = { transfer: 'Başka kuryeye aktar', next_day: 'Ertesi gün', evening_delivery_point: 'Akşam teslimi / teslim noktası' };
    CM.side(`<div class="side-head"><span>Müdür ekranı · riskler</span><span class="mod" id="mod3"></span></div>
      <div class="side-inner"><ol class="rationale risk">${r}</ol>
      ${alt ? `<div class="y-title">Kaydırılamayan teslim saati · karar sizde</div>
        <div class="alt-card"><div class="a-name">${CM.escape(alt.label)} · ${CM.escape(alt.courier_name)}</div>
        <div class="a-select">${SELECT[alt.option] || alt.option}</div>
        <div class="a-rule">Kural: rota uzamaz, fazla mesai yok. Aynı rotada uygun saate taşımak rotayı uzatırdı.</div>
        <div class="sms"><b>Alıcıya SMS (öneri)</b>${CM.escape(alt.sms_text || '')}</div></div>` : ''}</div>`, 'open');
    CM.writeMode(CM.$('mod3'));
  }

  function questionCards() {
    if (!ask) return;
    const cards = (ask.alternatives || []).map((a, i) => {
      const f = a.diff || {};
      const select = i === 0;
      const row = (name, v, unit, nd) => `<div class="fk ${v > 0 ? 'bad' : ''}"><span>${name}</span><b>${v > 0 ? '+' : v < 0 ? '−' : '±'}${CM.count(Math.abs(v), nd)}${unit ? ' ' + unit : ''}</b></div>`;
      return `<div class="card wide ${select ? 'picked' : 'unselected'}"><div class="top"><span>${i + 1}. yol</span><span>${select ? 'ajanın önerisi' : ''}</span></div>
        <div class="name">${CM.escape(a.name)}</div>
        ${row('bant üstü süre', f.over_band_min || 0, 'dk', 0)}${row('bandı aşan kurye', f.over_band_courier || 0, '', 0)}${row('beklenen başarısız', f.expected_fails || 0, '', 1)}</div>`;
    }).join('');
    CM.cards(`<div class="title">“${CM.escape(ask.question || 'Onur gelmezse ne olur?')}” · ajan iki yolu araçla hesapladı</div>${cards}`);
    [...CM.$('cards').querySelectorAll('.card')].forEach((c, i) => setTimeout(() => c.classList.add('view'), 200 + i * 240));
  }

  function questionChips(questions) {
    CM.action(questions.map((s, j) => `<button class="chip" data-j="${j}">${CM.escape(s)}</button>`).join('') +
      '<form id="sorf" class="serbest"><input id="ask-text" autocomplete="off" placeholder="Kendi sorunuz: “Onur yerine Melis giderse?”"><button class="secondary">Sor</button></form>', true);
    CM.$('action').querySelectorAll('.chip').forEach((b) => (b.onclick = () => askQuestion(questions[+b.dataset.j])));
    CM.$('sorf').onsubmit = (e) => { e.preventDefault(); const m = CM.$('ask-text').value.trim(); if (m) askQuestion(m); };
  }
  async function askQuestion(text) {
    const n = no;
    CM.action('');
    CM.openTrace('Orkestratör izi · senaryo');
    CM.writeMode();
    CM.waitTrace(true);
    try {
      if (!ask || ask.question !== text) {
        if (session.status !== 'awaiting_approval') throw new Error('Plan onaylandı; senaryo sorusu onaydan önce sorulur.');
        const name = text === 'Onur gelmezse ne olur?' ? 'onur' : text === 'Gökhan gelmezse ne olur?' ? 'gokhan' : 'serbest';
        let s;
        try { s = await CM.api(`/api/orchestrator/session/${session.session_id}/ask`, { question: text }, { name, ms: 120000 }); }
        catch (e) { if (e.noRecord) throw new Error('API yok: serbest soru canlı hesap ister; hazır sorulardan birini seçin.'); throw e; }
        s.question = text;
        ask = s;
      }
      if (n !== no) return;
      CM.waitTrace(false);
      await CM.writeTrace(ask.trace || [], { duration: 160 });
      if (n !== no) return;
      highlight((ask.diff || {}).changed_clusters || []);
      CM.figure([]);
      questionCards();
      CM.action(`<span class="hint response">${CM.escape(ask.response)}</span><form id="sorf" class="serbest small"><input id="ask-text" autocomplete="off" placeholder="Başka bir soru: “Onur yerine Melis giderse?”"><button class="secondary">Sor</button></form>`, true);
      CM.$('sorf').onsubmit = (e) => { e.preventDefault(); const m = CM.$('ask-text').value.trim(); if (m) askQuestion(m); };
      if (!(ask.alternatives || []).length) CM.cards('');
    } catch (e) {
      CM.waitTrace(false);
      questionChips(proposal.questions && proposal.questions.length ? proposal.questions : ['Onur gelmezse ne olur?']);
      CM.$('action').insertAdjacentHTML('beforeend', `<span class="hint error">${CM.escape(e.detail || e.message)}</span>`);
    }
  }

  async function approve() {
    const n = no;
    CM.action('');
    CM.openTrace('Orkestratör izi');
    CM.writeMode();
    try {
      if (!decision) {
        if (session.status === 'awaiting_approval') {
          decision = await CM.api(`/api/orchestrator/session/${session.session_id}/decision`, { decision: 'approval' }, { name: 'approval' });
          session.status = decision.status;
        } else decision = { status: session.status, plan: session.plan };
        // insan kararı ve kapanış olayları izden
        try {
          const d = await CM.api(`/api/orchestrator/session/${session.session_id}?after=${session.total_event || 0}`);
          decision.events = d.events.filter((e) => e.type === 'human_decision' || e.type === 'done');
        } catch (e) { decision.events = []; }
        if (!decision.events.length) decision.events = [{ i: 0, type: 'human_decision', source: 'human', decision: 'approval', note: null }, { i: 1, type: 'done', source: 'rule', status: decision.status }];
      }
      if (n !== no) return;
      await CM.writeTrace(decision.events, { duration: 400 });
      if (n !== no) return;
      highlight([]);
      CM.cards('');
      const p = decision.plan || proposal;
      CM.figure([{ v: 'Onaylandı', boy: 'mid', l: 'acil durumda karar müdürün' }, { v: p.assignment.length, l: 'kurye' }],
        'Kurye brifingleri ve hafızalı rotalar bu planı okur · normal günde zincir temassız, müdür yalnız acil durumda');
      CM.action('');
    } catch (e) {
      CM.action(`<span class="hint error">${CM.escape(e.detail || e.message)}</span>`);
    }
  }

  // onaylı plan indirmeye gider. Gönderi okutulunca "raf · kurye · yükleme sırası"; kurye ayrıştırma yapmaz.
  async function unload(n) {
    CM.curtain(true);
    CM.closeTrace();
    let s;
    try { s = await CM.api(`/api/morning/${DAY}`, null, { ms: 60000 }); } catch (e) {
      CM.figure([{ v: '—', boy: 'mid', l: 'ayrıştırma planı alınamadı' }], CM.escape(e.detail || e.message)); return;
    }
    if (n !== no) return;
    const p = s.plan, leaving = s.departures.filter((c) => c.departure != null);
    const mean = (k) => leaving.reduce((t, c) => t + (c[k] || 0), 0) / Math.max(1, leaving.filter((c) => c[k] != null).length);
    CM.board(`<div class="unload"><div class="chart"><div class="g-head"><div><div class="g-title">İndirme okutması → raf</div>
      <div class="g-alt">${p.shelf_count} raf · ${CM.count(p.shipment)} gönderi · yükleme sırası rotanın tersi (son durak önce) · ertesi gün rafı ${p.next_day_shelf}</div></div></div>
      <div class="shelves">${p.shelves.map((r) => `<div class="shelf" data-shelf="${r.shelf}"><b>${r.shelf}</b><span>${CM.escape(r.name)}</span><i>${r.shipment}</i></div>`).join('')}</div></div>
      <div class="chart scan"><div class="g-head"><div><div class="g-title">Okutulan gönderiler</div><div class="g-alt">Ekran her okutmada rafı söyler; kurye rafını zimmetleyip yükler</div></div></div>
      <ol id="scan-list"></ol></div></div>`, 'full');
    CM.figure([{ v: CM.hhmm(mean('departure')), l: 'ortalama çıkış · okutmada ayrıştırma' }, { v: CM.hhmm(mean('departure_current')), l: 'bugünkü süreç', cls: 'faded' },
      { v: CM.marked(mean('departure') - mean('departure_current')), l: 'dk' }],
      `Gün ${DAY}, kol D'nin rotaları; aynı rota bugünkü sabahla dönüş ${CM.hhmm(mean('return_current'))} → ${CM.hhmm(mean('return_time'))} · sabah süreleri şube beyanı, büyüklüğü pilot ölçer`);
    const ul = CM.$('scan-list');
    const ids = (s.example_shipments || []).slice(0, 8).concat([`G${DAY}-0-1`]);
    for (const id of ids) {
      if (n !== no) return;
      let r;
      try { r = await CM.api('/api/morning/scan', { day: DAY, shipment: id }, { name: id }); } catch (e) { continue; }
      if (n !== no || !ul.isConnected) return;
      const li = document.createElement('li');
      li.className = r.exception ? 'exception' : '';
      li.innerHTML = `<code>${CM.escape(id)}</code><span>${CM.escape(r.instruction)}</span>`;
      ul.appendChild(li);
      while (ul.children.length > 9) ul.removeChild(ul.firstChild);
      CM.$('board').querySelectorAll('.shelf.active').forEach((x) => x.classList.remove('active'));
      const shelf = CM.$('board').querySelector(`.shelf[data-shelf="${r.shelf}"]`);
      if (shelf) { shelf.classList.add('active', 'filled'); }
      await CM.wait(650);
    }
  }

  const S3 = {
    no: 3, name: 'Acil durum', stepCount: 6,
    title: 'Gün 32 · acil durum: müdür devreye girer · zincir normalde temassız',
    attribution: '<b>Uygulama verisi · 1 aylık geçmiş</b> · Harita: OpenFreeMap © OpenMapTiles © OpenStreetMap · konumlar Beykoz saha verisi, sonuçlar simülasyon',

    async enter() {
      no++;
      [data] = await Promise.all([CM.scene2Data(), CM.mapping()]);
      CM.adjust({ s3ter: 0, s3Hit: 0 });
      CM.H.frame([29.064, 41.047, 29.332, 41.235]);
      const ter = CM.gj(data.routes.filter((r) => r.rings.length).map((r) => CM.multi(r.rings, { c: color(r.route), r: r.route })));
      CM.H.add({ id: 's3-ter', type: 'fill', data: ter, paint: (S) => ({ 'fill-color': ['get', 'c'], 'fill-opacity': 0.22 * S.s3ter * (1 - 0.6 * S.s3Hit) }) });
      CM.H.add({ id: 's3-ter-c', type: 'line', data: ter, paint: (S) => ({ 'line-color': ['get', 'c'], 'line-width': 1.2, 'line-opacity': 0.8 * S.s3ter * (1 - 0.5 * S.s3Hit) }) });
      CM.H.add({ id: 's-3-hit', type: 'fill', data: ter, filtre: cluster([]), paint: (S) => ({ 'fill-color': ['get', 'c'], 'fill-opacity': 0.55 * S.s3Hit }) });
      CM.H.add({ id: 's-3-hit-c', type: 'line', data: ter, filtre: cluster([]), paint: (S) => ({ 'line-color': '#1A1714', 'line-width': 2.4, 'line-opacity': S.s3Hit }) });
      CM.H.add({ id: 's-3-addr', type: 'circle', data: CM.gj([]), paint: (S) => ({ 'circle-radius': 9, 'circle-color': '#D2261C', 'circle-opacity': S.s3Addr || 0, 'circle-stroke-color': '#FBF8F2', 'circle-stroke-width': 3, 'circle-stroke-opacity': S.s3Addr || 0 }) });
      CM.H.end(camera(), 1400);
      CM.tween({ s3ter: 1 }, 1200);
      CM.openTrace('Orkestratör izi');
      CM.$('trace-list').innerHTML = '';
      CM.closeTrace();
      CM.figure([]);
      try {
        session = await getSession();
        proposal = session.proposal || session.plan;
        if (session.status === 'finalized') decision = { status: 'finalized', plan: session.plan };
        else decision = null;
        // geçmiş izden yalnız öneri anı (iz paneli bağlam için)
        const ol = (session.events || []).filter((e) => e.type === 'proposal' || e.type === 'escalation' || e.type === 'awaiting_approval');
        CM.writeTrace(ol, { next: false });
      } catch (e) {
        CM.action(`<span class="hint error">Öneri alınamadı: ${CM.escape(e.detail || e.message)}</span>`);
        proposal = null;
      }
    },

    step(i, previous) {
      no++;
      if (!proposal) return;
      CM.cards(''); CM.action('');
      if (i < 5) { CM.curtain(false); CM.board(''); CM.$('scene-title').textContent = S3.title; }
      CM.deleteMark(marks);
      CM.tween({ s3Addr: 0 }, 300);
      const borrowed = proposal.assignment.filter((a) => a.source === 'neighbor' || a.courier_type === 'borrowed');
      if (i === 0) {
        CM.closeTrace();
        highlight(borrowed.map((a) => a.cluster));
        for (const a of borrowed) label(a.cluster, a.courier_name, 'komşu şubeden · ' + CM.count(a.stop) + ' durak', 'dark');
        CM.figure([{ v: proposal.assignment.length, l: 'kurye' }, { v: proposal.borrowed.length, l: 'komşu şubeden' }, { v: CM.percent(proposal.own_zone_share), l: 'kendi bölgesinde' }],
          `Beklenen başarısız teslim ${CM.count(proposal.total.expected_fails, 1)} · kuryeler geçmişe bakmadan atansaydı ${CM.count(proposal.comparison.history_blind_expected_fails, 1)}`);
        sideRationale();
      } else if (i === 1) {
        CM.closeTrace();
        const band = proposal.assignment.filter((a) => a.over_band).sort((a, b) => b.expected_min - a.expected_min);
        const first3 = band.slice(0, 3);
        highlight(first3.map((a) => a.cluster));
        for (const a of first3) label(a.cluster, `${a.courier_name} · ${CM.count(a.expected_min)} dk`, `bant üstü · ${CM.count(a.stop)} durak`);
        CM.figure([{ v: proposal.total.over_band_courier, l: 'kurye vardiya bandının üstünde', cls: 'red' }, { v: CM.count(proposal.total.over_band_min), l: 'dk bant üstü (toplam)' }],
          `İlk 3 gösteriliyor · beklenen süre kuryeye özgü tahmin (planlanan değil) · bant 378–528 dk`);
        const alt = (proposal.time_alternatives || [])[0];
        if (alt) {
          const ll = CM.position(alt.address);
          if (ll) {
            CM.H.data('s-3-addr', CM.gj([CM.point(ll[1], ll[0], {})]));
            CM.tween({ s3Addr: 1 }, 600);
            marks.push(CM.H.mark(CM.labelEl(alt.label, 'teslim saati kaydırılamadı · alternatif', 'red'), ll, 'top'));
          }
        }
        sideRisk();
      } else if (i === 2) {
        CM.side('');
        const questions = proposal.questions && proposal.questions.length ? proposal.questions : ['Onur gelmezse ne olur?'];
        CM.figure([]);
        if (ask && previous != null && i < previous) { askQuestion(ask.question); return; }
        CM.openTrace('Orkestratör izi · senaryo');
        questionChips(questions);
        if (previous != null && i > previous) askQuestion(questions[0]);
      } else if (i === 3) {
        CM.side('');
        highlight([]);
        CM.closeTrace();
        if (decision && decision.events) {
          CM.figure([{ v: 'Onaylandı', boy: 'mid', l: 'plan kesinleşti · karar müdürün' }], 'Onay bir kez verilir; koşu kapandı');
          return;
        }
        CM.figure([{ v: proposal.assignment.length, l: 'kurye' }, { v: proposal.borrowed.map((q) => q.name).join(' + '), boy: 'mid', l: 'komşu şubeden' }], 'Öneri değişmedi: Onur ve Gökhan geliyor · karar müdürde');
        CM.action('<button class="approval" id="approve3">ONAYLA <span class="kbd">→</span></button><span class="hint">Onaydan sonra plan kesinleşir; brifingler ve rotalar onaylı planı okur</span>', true);
        CM.$('approve3').onclick = () => CM.next && CM.next();
      } else if (i === 4) {
        CM.side('');
        highlight([]);
        approve();
      } else if (i === 5) {
        CM.side(''); CM.cards(''); CM.action('');
        highlight([]);
        CM.$('scene-title').textContent = 'Gün 32 · 08:30 araç geldi · ayrıştırma indirme okutmasında';
        unload(no);
      }
    },

    leaving() {
      no++;
      CM.deleteMark(marks);
      CM.cards(''); CM.figure([]); CM.action(''); CM.side(''); CM.board(''); CM.curtain(false);
      CM.closeTrace();
      CM.H.clear();
    },
  };
  CM.scenes = CM.scenes || {};
  CM.scenes[3] = S3;
})(window.CM);
