/* Sahne 7 · Değer: operasyon maliyeti (TL), yüzde değil para. (0) manşet, (1) şelale, (2) dört durum yan yana, (3) ölçek +
   model karşılaştırması, (4) LLM maliyeti temkinli ↔ optimize + ajan başına model seçici, (5) parametreleri değiştirin
   (kaydırıcılar → /api/ekonomi). Eski ui/ "Değer" sekmesinin tamamı burada. Kurye-gün ve başarısız teslim maliyetleri tahmini parametredir (agents/economics.yaml). */
(function (CM) {
  let extra = null, oz = null, opt = null, no = 0, setting = {}, timer = 0;
  const SHORT = { today: 'Bugün\nsabit bölge', dynamic: 'Dinamik plan\ndaha az kurye', agentless: 'Ajansız\nbilgi kaybı', assignment: 'Atama Ajanı\nçekirdek bölge', memory: 'Hafıza +\nBrifing', morning: 'Sabah\nokutmada ayrıştırma', result: 'Sonuç\nyeni yapı + hafıza' };
  const TL = (v) => CM.count(Math.round(v));
  const million = (v) => CM.count(v / 1e6, 1) + ' mn';
  const SLIDER = [
    { k: 'courier_daily_cost_tl', name: 'Kurye-gün maliyeti', unit: 'TL', min: 1500, max: 6000, step: 100 },
    { k: 'fails_other_tl', name: 'Başarısız teslimin diğer maliyeti', unit: 'TL', min: 0, max: 150, step: 5 },
    { k: 'second_attempt_min', name: 'İkinci deneme süresi', unit: 'dk', min: 0, max: 20, step: 1 },
    { k: 'km_cost_tl', name: 'Km maliyeti', unit: 'TL', min: 0, max: 15, step: 0.5 },
  ];

  function headline(e, next = true) {
    const m = e.headline;
    CM.figure([{ v: TL(m.savings_tl_day), l: 'TL/gün daha düşük operasyon maliyeti' }, { v: million(m.savings_tl_year), boy: 'mid', l: 'TL/yıl · Beykoz bölgesi' },
      { v: `${m.quality.fails_per_day_current} → ${m.quality.fails_per_day_memory}`, boy: 'mid', l: 'başarısız teslim/gün' }],
      `Bugünkü yapıya göre · ajansız aynı geçiş günde ${TL(m.agentless_extra_cost_tl_day)} TL artırırdı · LLM maliyetinin tasarrufa oranı %${CM.count(m.llm_share * 100, 1)} · kurye-gün ve başarısız teslim maliyeti tahminidir`);
  }
  function waterfall(container, e) {
    const s = e.operation.waterfall;
    const { body } = CM.chartShell(container, {
      title: 'Operasyon maliyeti, TL/gün · Beykoz bölgesi',
      alt: 'Bugünden yeni yapıya: dinamik planlamanın kurye tasarrufu ajansız geçişte bilgi kaybıyla geri gider; ajanlar geri kazanır',
      legend: [{ name: 'azalış', color: '#2C7A4B', type: 'frame' }, { name: 'artış', color: '#D2261C', type: 'frame' }],
      table: { titles: ['Adım', 'TL/gün'], rows: s.map((a) => [a.step, (a.type === 'decrease' || a.type === 'increase') && a.tl_day > 0 ? '+' + TL(a.tl_day) : TL(a.tl_day)]) },
    });
    CM.waterfallChart(body, s.map((a) => ({ name: SHORT[a.code] || a.step, full: a.step, value: a.tl_day, type: a.type })));
  }

  function states() {
    const K = extra.operation.arms, U = oz && oz.long_term && oz.long_term.summary.arms;
    const arm = ['A', 'B', 'C', 'D'];
    const sat = [
      ['Kurye/gün', (k) => CM.count(K[k].courier, 1)],
      ['Kendi bölgesinde durak', (k) => (U ? CM.percent(1 - U[k].unfamiliar_share) : '')],
      ['Başarısız teslim/gün', (k) => CM.count(K[k].fails_per_day)],
      ['… bilgiyle önlenebilir', (k) => CM.count(K[k].preventable_day)],
      ['Fazla mesai, saat/gün', (k) => CM.count(K[k].overtime_hour_day, 1)],
      ['Km/gün', (k) => CM.count(K[k].km_day)],
      ['Operasyon maliyeti, TL/gün', (k) => TL(K[k].total_tl_day)],
      ['Gönderi başı TL', (k) => CM.count(K[k].per_shipment_tl, 2)],
      ['Yıllık fark (bugüne göre)', (k) => (k === 'A' ? '—' : (K[k].total_tl_year - K.A.total_tl_year > 0 ? '+' : '−') + million(Math.abs(K[k].total_tl_year - K.A.total_tl_year)) + ' TL')],
    ];
    const head = arm.map((k) => `<th class="s"><i class="key frame" style="background:${CM.ARM[k]}"></i>${CM.escape(K[k].name)}</th>`).join('');
    CM.board(`<div class="chart"><div class="g-head"><div><div class="g-title">Aynı gönderiler, dört yapı · 60 iş günü ortalaması</div>
      <div class="g-alt">Uzun dönem senaryosu · km tasarrufu iddia etmiyoruz (simülasyon coğrafyasında oluşmuyor)</div></div></div>
      <table class="status"><thead><tr><th></th>${head}</tr></thead><tbody>${sat.map(([name, f]) => `<tr><td>${name}</td>${arm.map((k) => `<td class="s${k === 'D' ? ' accent' : ''}">${f(k)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`, 'full mid');
    CM.figure([]);
  }

  // Eski "Değer" sekmesinden: ölçek (1/10/100 bölge) ve model karşılaştırması
  function scale() {
    const O = extra.operation.scale || [], N = extra.scale || [];
    const net = new Map(N.map((r) => [r.branch, r]));
    const mk = extra.model_comparison || [], most = Math.max(...mk.map((m) => m.llm_tl_day)) || 1;
    CM.board(`<div class="two"><div class="chart"><div class="g-head"><div><div class="g-title">Ölçek: yıllık, TL</div>
      <div class="g-alt">Beykoz bölgesi değerinin doğrusal çarpımı (bölgeler arası fark modellenmedi) · kurye-gün maliyeti tahminidir</div></div></div>
      <table class="status"><thead><tr><th>Bölge</th><th class="s">Operasyon tasarrufu</th><th class="s">Ajansız geçişin ek maliyeti</th><th class="s">LLM maliyeti</th><th class="s">Hafıza + Brifing net (C'ye göre)</th></tr></thead>
      <tbody>${O.map((r) => { const n = net.get(r.branch) || {}; return `<tr><td>${r.branch}</td><td class="s accent">${million(r.savings_tl_year)}</td><td class="s">+${million(r.agentless_extra_cost_tl_year)}</td><td class="s">${n.llm_tl_year != null ? million(n.llm_tl_year) : ''}</td><td class="s">${n.net_tl_year_vs_C != null ? million(n.net_tl_year_vs_C) : ''}</td></tr>`; }).join('')}</tbody></table></div>
      <div class="chart"><div class="g-head"><div><div class="g-title">Tüm ajanlar tek modelle: LLM TL/gün</div>
      <div class="g-alt">Önbelleksiz · getiri: Hafıza + Brifing'in C'ye göre katkısı / LLM maliyeti</div></div></div>
      <table class="kirilim">${mk.map((m) => `<tr><td>${CM.escape(m.name)}</td><td class="bar-fill"><i style="width:${(m.llm_tl_day / most) * 100}%"></i></td><td class="s b">${CM.count(m.llm_tl_day, m.llm_tl_day < 10 ? 1 : 0)}</td><td class="s">${CM.count(m.per_shipment_kurus, 2)} kuruş/gönderi</td><td class="s">getiri ${CM.count(m.return_multiple_vs_C, 1)}×</td></tr>`).join('')}</table></div></div>`, 'full mid');
    const b = O[0];
    CM.figure(b ? [{ v: million(b.savings_tl_year), boy: 'mid', l: 'TL/yıl · Beykoz bölgesi' }, { v: million((O[O.length - 1] || b).savings_tl_year), boy: 'mid', l: `TL/yıl · ${(O[O.length - 1] || b).branch} bölge` }] : [],
      'Gerçek büyüklüğü 4 haftalık tek şube A/B pilotu ölçer');
  }

  async function llm(scenario, n) {
    const L = extra.llm_scenarios;
    const card = (s) => `<div class="llm-card ${s.scenario === scenario ? 'selected' : ''}" data-s="${s.scenario}"><div class="lk-name">${CM.escape(s.name)}</div>
      <div class="lk-v">${CM.count(s.llm_tl_day, s.llm_tl_day < 100 ? 1 : 0)} <small>TL/gün</small></div>
      <div class="lk-row"><span>gönderi başı</span><b>${CM.count(s.per_shipment_kurus, 2)} kuruş</b></div>
      <div class="lk-row"><span>tasarrufa oranı</span><b>%${CM.count(s.savings_rate * 100, 1)}</b></div>
      <div class="lk-row"><span>yılda</span><b>${TL(s.llm_tl_year)} TL</b></div></div>`;
    if (scenario === 'optimize' && !opt) { try { opt = await CM.api('/api/economics?scenario=optimize'); } catch (e) { opt = null; } }
    if (n !== no) return;
    const kay = scenario === 'optimize' && opt ? opt : extra;
    const aj = Object.entries(kay.llm.agents).sort((a, b) => b[1].daily_tl - a[1].daily_tl);
    const most = Math.max(...aj.map(([, a]) => a.daily_tl)) || 1;
    const NAME = { propose_assignment: 'Atama önerisi', ask_assignment: 'Atama soruları', memory: 'Hafıza (not)', briefing: 'Brifing', orchestrator: 'Orkestratör', ask_orchestrator: 'Orkestratör soruları', harvest: 'Hasat', harvest_answer: 'Hasat cevapları' };
    CM.board(`<div class="llm">${L.map(card).join('')}
      <div class="chart llm-kirilim"><div class="g-head"><div><div class="g-title">Ajan başına, TL/gün · ${scenario === 'optimize' ? 'optimize' : 'temkinli'}</div>
      <div class="g-alt">Token: ${aj.some(([, a]) => a.source === 'measurement') ? 'canlı ölçüm + tahmin' : 'tahmin (canlı ölçümle güncellenir)'} · ${CM.escape(kay.assumptions.price_source || '')}</div></div></div>
      <table class="kirilim">${aj.map(([k, a]) => `<tr><td>${NAME[k] || k}</td><td class="s">${CM.count(a.call_day, 1)} çağrı</td><td class="bar-fill"><i style="width:${(a.daily_tl / most) * 100}%"></i></td><td class="s b">${CM.count(a.daily_tl, 1)}</td></tr>`).join('')}</table></div></div>`, 'full mid');
    CM.$('board').querySelectorAll('.llm-card').forEach((c) => (c.onclick = () => llm(c.dataset.s, no)));
    modelSelector(kay);
    CM.figure([]);
    CM.action(`<button class="${scenario === 'cautious' ? 'selected' : 'secondary'}" id="tem7">Temkinli</button><button class="${scenario === 'optimize' ? 'selected' : 'secondary'}" id="opt7">Optimize</button><span class="hint">Optimize: önbellek + işe göre model · kalite iddiası canlı değerlendirmeyle desteklenir</span>`);
    CM.$('tem7').onclick = () => llm('cautious', no);
    CM.$('opt7').onclick = () => llm('optimize', no);
  }

  // Ajan başına model + önbellek (API'nin desteklediği üç ajan: atama, hafıza, brifing); sonuç kırılım tablosunun altına
  function modelSelector(kay) {
    const offline = CM.apiStatus.offline, am = kay.assumptions.agent_model || {}, M = extra.models || [];
    const select = (k, name) => `<label>${name}<select data-k="${k}" ${offline ? 'disabled' : ''}>${M.map((m) => `<option value="${m.id}" ${am[k] === m.id ? 'selected' : ''}>${CM.escape(m.name)}</option>`).join('')}</select></label>`;
    const boxes = CM.$('board').querySelector('.llm-kirilim');
    const d = document.createElement('div');
    d.className = 'model-select';
    d.innerHTML = `${select('model_assignment', 'Atama')}${select('model_memory', 'Hafıza')}${select('model_briefing', 'Brifing')}
      <label class="box"><input type="checkbox" data-k="onbellek" ${kay.assumptions.cache ? 'checked' : ''} ${offline ? 'disabled' : ''}>önbellek</label>
      <span class="ms-result" id="ms7">${offline ? 'API yok: model seçimi canlı hesap ister' : 'Ajan başına model seçin'}</span>`;
    boxes.appendChild(d);
    const compute = async () => {
      const q = new URLSearchParams();
      d.querySelectorAll('select').forEach((s) => q.set(s.dataset.k, s.value));
      q.set('cache', d.querySelector('input').checked ? 'true' : 'false');
      try {
        const e = await CM.api('/api/economics?' + q.toString());
        CM.$('ms7').innerHTML = `Seçiminiz: <b>${CM.count(e.llm.daily_tl, e.llm.daily_tl < 100 ? 1 : 0)} TL/gün</b> · ${CM.count(e.llm.per_shipment_kurus, 2)} kuruş/gönderi · tasarrufun %${CM.count(e.headline.llm_share * 100, 2)}'i`;
      } catch (err) { CM.$('ms7').textContent = 'Hesaplanamadı: ' + (err.detail || err.message); }
    };
    d.querySelectorAll('select, input').forEach((x) => (x.onchange = compute));
  }

  function assumption(n) {
    const v = extra.assumptions;
    for (const s of SLIDER) if (setting[s.k] == null) setting[s.k] = v[s.k];
    const offline = CM.apiStatus.offline;
    CM.board(`<div class="vars"><div class="sliders"><div class="g-title">Parametreleri değiştirin</div><div class="g-alt">${offline ? 'API yok: kaydırıcılar canlı hesap ister' : 'Her değişiklik /api/ekonomi ile yeniden hesaplanır'}</div>
      ${SLIDER.map((s) => `<label class="kd"><span class="kd-name">${s.name} <b id="kd-${s.k}">${CM.count(setting[s.k], s.step < 1 ? 1 : 0)} ${s.unit}</b></span>
        <input type="range" min="${s.min}" max="${s.max}" step="${s.step}" value="${setting[s.k]}" data-k="${s.k}" ${offline ? 'disabled' : ''}></label>`).join('')}
      <button class="g-table" id="reset7" ${offline ? 'disabled' : ''}>Varsayılana dön</button></div><div id="g7" class="vars-g"></div></div>`, 'full');
    const draw = (e) => { waterfall(CM.$('g7'), e); headline(e); };
    draw(extra);
    const update = () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const q = new URLSearchParams(Object.entries(setting).map(([k, x]) => [k, String(x)])).toString();
        try { const e = await CM.api('/api/economics?' + q); if (n === no) draw(e); } catch (err) { /* sınır dışı: eski çizim kalır */ }
      }, 160);
    };
    CM.$('board').querySelectorAll('input[type=range]').forEach((r) => (r.oninput = () => {
      const s = SLIDER.find((x) => x.k === r.dataset.k);
      setting[s.k] = +r.value;
      CM.$('kd-' + s.k).textContent = `${CM.count(setting[s.k], s.step < 1 ? 1 : 0)} ${s.unit}`;
      update();
    }));
    CM.$('reset7').onclick = () => { setting = {}; assumption(no); };
  }

  const S7 = {
    no: 7, name: 'Değer', stepCount: 6,
    title: 'Değer: yüzde değil para · Beykoz bölgesi operasyon maliyeti',
    attribution: '<b>Uygulama verisi · 1 aylık geçmiş</b> · tahmini maliyet parametreleri (agents/economics.yaml)',
    async enter() {
      no++;
      CM.H.end({ center: [29.19, 41.14], zoom: 11.2, pitch: 30, bearing: -8 }, 1500);
      CM.curtain(true);
      [extra, oz] = await Promise.all([CM.al('/api/economics'), CM.al('/api/summary').catch(() => null)]);
      opt = null;
    },
    step(i) {
      const n = ++no;
      CM.curtain(true); CM.hideHint(); CM.action(''); CM.message([]); CM.board('');
      if (i === 0) {
        headline(extra);
        CM.message(['Ajansız geçiş maliyeti artırır;', 'ajanlarla <span class="green">düşer.</span>']);
      } else if (i === 1) {
        CM.board('<div id="g7"></div>', 'full top');
        waterfall(CM.$('g7'), extra);
        headline(extra);
      } else if (i === 2) states();
      else if (i === 3) scale();
      else if (i === 4) llm('cautious', n);
      else assumption(n);
    },
    leaving() { no++; CM.board(''); CM.figure([]); CM.action(''); CM.message([]); CM.curtain(false); CM.hideHint(); },
  };
  CM.scenes = CM.scenes || {};
  CM.scenes[7] = S7;
})(window.CM);
