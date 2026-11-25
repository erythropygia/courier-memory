/* Sahne 5 · Hasat: kıdemlinin bildiğini sistematik toplamak ve kayıtlardan kalıp bulmak.
   (0) Hasat Ajanı günün sorularını çıkarır (hafıza boşluğu, tekrarlayan başarısızlık hipotezi, saat teyidi; iz);
   (1) Gökhan'ın rotasındaki boş adres için kıdemliye soru → simüle cevap → Hafıza Ajanı → rota değişir;
   (2) saat teyidi → teslim saati kaydırılır; (3) kayıtlardan "bu adreste şu saatte kimse yok" (notsuz) → rota.
   Simüle kıdemli açıkça etiketlidir (cevap simülasyonun gizli gerçeğinden). */
(function (CM) {
  const DAY = 32;
  const REASON = { gap: { name: 'hafıza boşluğu', c: '#2a78d6' }, hypothesis: { name: 'tekrarlayan başarısızlık', c: '#9C4F7E' }, time: { name: 'saat teyidi', c: '#1A1714' } };
  let harvest = null, demo = null, example = null, answer = {}, routeBefore = {}, routeAfter = {};
  let marks = [], no = 0;

  function camera() {
    if (!CM.H.gl) return null;
    const w = innerWidth, h = innerHeight;
    const c = CM.H.map.cameraForBounds([[29.064, 41.047], [29.332, 41.235]], { padding: { left: w * 0.06, right: w * 0.34, top: h * 0.08, bottom: h * 0.22 }, bearing: -8 });
    return { center: c.center, zoom: c.zoom + 0.25, pitch: 30, bearing: -8 };
  }
  const near = (ll) => ({ center: [ll[0] + 0.004, ll[1]], zoom: 15.6, pitch: 55, bearing: -18 });

  async function getHarvest() {
    if (!harvest) harvest = await CM.api('/api/harvest/plan', { day: DAY }, { ms: 120000 });
    return harvest;
  }
  function findQuestion(address, reason) {
    const q = harvest.questions;
    return q.find((x) => x.address === address) || q.find((x) => x.reason === reason) || q[0];
  }

  function questionPoints() {
    const f = harvest.questions.map((q) => { const ll = CM.position(q.address); return ll && CM.point(ll[1], ll[0], { c: REASON[q.reason] ? REASON[q.reason].c : '#1A1714' }); }).filter(Boolean);
    CM.H.data('s-5-question', CM.gj(f));
  }

  function questionCard(q, outgoing, c) {
    const nd = REASON[q.reason] || { name: q.reason };
    let result = '';
    if (c) {
      const h = c.memory, z = c.time;
      result = `<div class="y-title">Cevap <span class="simulate">simüle kıdemli</span></div><div class="answer">“${CM.escape(c.question.answer || '')}”</div>`;
      if (h) result += `<div class="badges"><span class="badge ${h.status === 'saved' || h.status === 'updated' ? 'good' : ''}">Hafıza Ajanı · ${CM.escape({ saved: 'kaydedildi', updated: 'güncellendi', noise: 'gürültü', uncertain: 'belirsiz', rejected: 'reddedildi' }[h.status] || h.status)}</span>${h.type ? `<span class="badge">${CM.QUIRK[h.type] || h.type}</span>` : ''}${h.personal_data_redacted ? '<span class="badge shield">Kişisel veri ayıklandı</span>' : ''}</div>` +
        (h.hint ? `<div class="t-summary">Hafızaya: “${CM.escape(h.hint)}”</div>` : '');
      if (z) result += `<div class="badges"><span class="badge ${z.status === 'confirmation' ? 'good' : ''}">Saat ${z.status === 'confirmation' ? 'teyit edildi' : z.status === 'ret' ? 'rejected' : 'uncertain'}</span>${z.hour_text ? `<span class="badge">${CM.escape(z.hour_text)}</span>` : ''}</div>` +
        `<div class="t-summary">${CM.escape(z.summary || '')} · teslim zamanı kaynağına yazıldı (hafızaya değil)</div>`;
    }
    CM.side(`<div class="side-head"><span>Hasat · ${nd.name}</span><span class="mod" id="mod5"></span></div>
      <div class="side-inner"><div class="y-title">${CM.escape(q.label)} · soru ${CM.escape(q.courier_name)}'a</div>
      <div class="question">${CM.escape(q.question)}</div>${outgoing ? `<div class="t-summary">Bugün bu adrese giden: ${CM.escape(outgoing)}</div>` : ''}${result}</div>`, 'open');
    CM.writeMode(CM.$('mod5'));
  }

  async function ask(n, type) {
    const d = type === 'time' ? demo.harvest_time || {} : demo.harvest_gap || {};
    await getHarvest();
    if (n !== no) return;
    const q = findQuestion(d.address, type);
    const ll = CM.position(q.address);
    if (ll) {
      CM.H.end(near(ll), 1600);
      CM.H.data('s-5-focus', CM.gj([CM.point(ll[1], ll[0], {})]));
      CM.tween({ s5Focus: 1, s5Question: 0.25 }, 700);
      marks.push(CM.H.mark(CM.labelEl(q.label, REASON[q.reason] ? REASON[q.reason].name : ''), ll, 'top'));
    }
    const courier = d.courier;
    questionCard(q, d.courier_name, answer[q.id]);
    if (answer[q.id]) { showRoute(n, q, courier); return; }
    CM.figure([]);
    CM.action(`<button id="answer5">Simüle kıdemli cevaplasın <span class="kbd">→</span></button><span class="hint">Demoda cevap simülasyonun gizli gerçeğinden gelir; sahada kurye 3 saniyelik sesli cevap verir</span>`, true);
    CM.$('answer5').onclick = () => reply(no, q, courier);
    S5.pending = () => reply(no, q, courier);
  }
  async function reply(n, q, courier) {
    S5.pending = null;
    CM.action('');
    try {
      if (courier && !routeBefore[courier]) routeBefore[courier] = await CM.api(`/api/route/${DAY}/${courier}`, null, { name: 'before', ms: 60000 }).catch(() => null);
      if (!answer[q.id]) {
        try { answer[q.id] = await CM.api('/api/harvest/simulate-answer', { question_id: q.id }, { name: q.id, ms: 60000 }); }
        catch (e) { if (e.status === 409) { answer[q.id] = { question: { ...q, answer: '(bu soru daha önce cevaplandı)' }, memory: null }; } else throw e; }
      }
      if (n !== no) return;
      questionCard(q, (q.reason === 'time' ? demo.harvest_time : demo.harvest_gap || {}).courier_name, answer[q.id]);
      showRoute(n, q, courier);
    } catch (e) {
      CM.action(`<span class="hint error">${CM.escape(e.detail || e.message)}</span>`);
    }
  }
  async function showRoute(n, q, courier) {
    if (!courier) return;
    try {
      if (!routeAfter[q.id]) routeAfter[q.id] = await CM.api(`/api/route/${DAY}/${courier}`, null, { name: 'after-' + q.id, ms: 60000 });
      if (n !== no) return;
      const o = routeBefore[courier], s = routeAfter[q.id];
      const is_new = s.changes.filter((x) => !o || !o.changes.some((y) => JSON.stringify(y) === JSON.stringify(x)));
      const related = is_new.find((x) => x.address === q.address) || is_new[0];
      const pd0 = o ? o.comparison.memory.planned_min : null, pd1 = s.comparison.memory.planned_min;
      const pl = { v: pd0 != null && pd0 !== pd1 ? `${CM.count(pd0)} → ${CM.count(pd1)}` : CM.count(pd1), boy: 'mid', l: 'dk planlanan' };
      if (related && related.type === 'extra_service') {
        const es0 = o && o.changes.find((x) => x.type === 'extra_service');
        const diff = related.mins - (es0 ? es0.mins : 0);
        CM.figure([{ v: `+${CM.count(diff)} dk`, boy: 'mid', l: 'bu adresin servis süresi plana girdi' }, pl],
          `${CM.escape(s.name)} rotası · bilinen püf noktalı durak ${es0 ? es0.stop : 0} → ${related.stop} · planlanan süre gerçeğe yaklaşır, sürpriz azalır`);
      } else if (related) {
        CM.figure([{ v: related.type === 'time' ? `${related.old_order} → ${related.new_order}` : '✓', boy: 'mid', l: related.type === 'time' ? 'durak sırası · teslim saati kaydı' : 'rota değişti' }, pl],
          `${CM.escape(s.name)} rotası · ${CM.escape(related.text || '')}`);
      } else if ((s.time_unshiftable || []).some((x) => x.address === q.address)) {
        const b = s.time_unshiftable.find((x) => x.address === q.address);
        const NE = { route_duration: 'rotayı uzatırdı', km: 'yolu uzatırdı', band: 'vardiya bandını aşardı', after_shift: 'durağı vardiya bitişinden sonraya iterdi', window: 'bilinen bir pencereyi bozardı' };
        CM.figure([{ v: b.min_extra_min != null ? `+${CM.count(b.min_extra_min)} dk` : '—', boy: 'mid', l: 'aynı rotada kaydırmanın bedeli' }, pl],
          `${CM.escape(s.name)} rotası · ${CM.escape(b.label)}: en iyi saat ${CM.escape(b.good_slot)}, ama aynı rotada kaydırmak ${NE[b.reason] || 'kuralı bozardı'} (kural: rota uzamaz, fazla mesai yok) → müdüre alternatif: başka kurye ya da ertesi gün + alıcıya SMS`);
      } else {
        CM.figure([{ v: '—', boy: 'mid', l: 'rota değişmedi' }], `${CM.escape(s.name)} rotası · hafızaya yazıldı, bugünkü sırayı değiştirmedi`);
      }
    } catch (e) { CM.figure([]); }
  }

  async function records(n) {
    if (!example) example = await CM.api('/api/time/example');
    if (n !== no) return;
    const o = example.example, r = o.route || {};
    const ll = CM.position(o.address);
    if (ll) {
      CM.H.end({ ...near(ll), zoom: 15, center: [ll[0] + 0.014, ll[1] - 0.002] }, 1600);
      CM.H.data('s-5-focus', CM.gj([CM.point(ll[1], ll[0], {})]));
      CM.tween({ s5Focus: 1, s5Question: 0 }, 700);
      marks.push(CM.H.mark(CM.labelEl(o.label, `${{ house: 'ev', apartment: 'apartman', site: 'site', workplace: 'iş yeri', collection_point: 'toplu' }[o.address_type] || o.address_type} · ${o.courier_name}`), ll, 'top'));
    }
    CM.side('');
    const p = CM.board('<div id="g5"></div>', 'right');
    const { body } = CM.chartShell(p.querySelector('#g5'), {
      title: 'Teslim kayıtlarından, notsuz: bu adreste öğlen kimse yok',
      alt: `${CM.escape(o.finding.text)} · güven ${{ low: 'düşük', mid: 'orta', high: 'yüksek' }[o.finding.level] || o.finding.level}`,
      legend: [{ name: 'teslim', color: '#1A1714', type: 'point' }, { name: 'alıcı yok', color: '#D2261C', type: 'ring' }],
      table: { titles: ['Gün', 'Saat', 'Dilim', 'Sonuç'], rows: o.history.map((g) => [`${g.day} · ${g.weekday}`, g.hour, g.slot, g.result === 'delivery' ? 'delivery' : 'alıcı yok']) },
    });
    CM.timeChart(body, { history: o.history, bad: o.finding.bad_name, good: o.finding.good_name, day: o.day, legacy: o.result.no_time.arrival, is_new: o.result.memory.arrival });
    const pd = r.planned_min || {};
    CM.figure([{ v: o.result.memory.arrival, l: 'yeni varış · teslim' }, { v: pd.memory != null ? CM.marked(pd.memory - pd.no_time, 1) : '0', l: 'dk planlanan rota süresi farkı' }],
      `Ajan kalıbı kayıtlardan kendi buldu, rotayı uzatmadan kaydırdı (kural: rota uzamaz, fazla mesai yok) · seçilmiş örnek; mekanizmayı gösterir, büyüklüğü pilot ölçer`);
  }

  const S5 = {
    no: 5, name: 'Hasat', stepCount: 4, pending: null,
    title: 'Gün 32 · bilgi kişide kalmasın: kıdemliye sor, kayıtlardan öğren',
    attribution: '<b>Uygulama verisi · 1 aylık geçmiş</b> · cevaplar simüle kıdemliden · Harita: OpenFreeMap © OpenMapTiles © OpenStreetMap · konumlar Beykoz saha verisi',

    async enter() {
      no++;
      answer = {}; routeBefore = {}; routeAfter = {}; harvest = null; example = null;
      await CM.mapping();
      demo = await CM.demo();
      CM.adjust({ s5Question: 0, s5Focus: 0 });
      CM.H.frame([29.064, 41.047, 29.332, 41.235]);
      CM.H.add({ id: 's-5-question', type: 'circle', data: CM.gj([]), paint: (S) => ({ 'circle-radius': 7, 'circle-color': '#FBF8F2', 'circle-opacity': 0.9 * S.s5Question, 'circle-stroke-color': ['get', 'c'], 'circle-stroke-width': 3, 'circle-stroke-opacity': S.s5Question }) });
      CM.H.add({ id: 's-5-focus', type: 'circle', data: CM.gj([]), paint: (S) => ({ 'circle-radius': 15, 'circle-color': '#FBF8F2', 'circle-opacity': 0, 'circle-stroke-color': '#1A1714', 'circle-stroke-width': 3.5, 'circle-stroke-opacity': S.s5Focus }) });
      CM.$('trace-list').innerHTML = '';
    },

    step(i, previous) {
      const n = ++no;
      S5.pending = null;
      CM.action(''); CM.cards(''); CM.board(''); CM.hideHint();
      CM.deleteMark(marks);
      CM.tween({ s5Focus: 0 }, 400);
      if (i === 0) {
        CM.side('');
        CM.H.end(camera(), previous == null ? 1800 : 1000);
        CM.tween({ s5Question: harvest ? 1 : 0 }, 600);
        CM.openTrace('Hasat Ajanı izi');
        if (harvest && previous != null) { questionPoints(); summary(); return; }
        CM.figure([]);
        CM.action('<button id="harvest5">Bugünün soruları <span class="kbd">→</span></button><span class="hint">Planda yabancı kuryenin gideceği, hafızası boş adresler · tekrarlayan başarısızlık</span>');
        const start = async () => {
          CM.action('');
          CM.waitTrace(true);
          try { await getHarvest(); } catch (e) { CM.waitTrace(false); CM.action(`<span class="hint error">${CM.escape(e.detail || e.message)}</span>`); return; }
          if (n !== no) return;
          CM.waitTrace(false);
          CM.writeMode();
          questionPoints();
          CM.tween({ s5Question: 1 }, 1200);
          await CM.writeTrace(harvest.trace || [], { duration: 170 });
          if (n === no) summary();
        };
        CM.$('harvest5').onclick = start;
        S5.pending = start;
      } else if (i === 1) {
        CM.closeTrace();
        ask(n, 'gap');
      } else if (i === 2) {
        CM.closeTrace();
        ask(n, 'time');
      } else if (i === 3) {
        CM.closeTrace();
        records(n);
      }
    },
    leaving() {
      no++;
      S5.pending = null;
      CM.deleteMark(marks);
      CM.cards(''); CM.figure([]); CM.action(''); CM.side(''); CM.board(''); CM.hideHint();
      CM.closeTrace();
      CM.H.clear();
    },
  };
  function summary() {
    const say = (nd) => harvest.questions.filter((q) => q.reason === nd).length;
    CM.figure([{ v: say('gap'), l: 'boşluk sorusu' }, { v: say('hypothesis'), l: 'hipotez teyidi' }, { v: say('time'), l: 'saat teyidi' }],
      'Kurye başına günde ≤ 3, şubede ≤ 30 soru · hipotez teyitsiz hafızaya yazılmaz · halka rengi: mavi boşluk, mor hipotez, siyah saat');
  }
  CM.scenes = CM.scenes || {};
  CM.scenes[5] = S5;
})(window.CM);
