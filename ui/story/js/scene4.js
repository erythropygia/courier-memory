/* Sahne 4 · Kapıda: komşu şubeden gelen Gökhan (O02), gün 32. Sabah brifingi (ses), rota oynatma: notlu kapıya
   gelince tek cümle + "hâlâ geçerli mi?", kurye notu (kişisel veri ayıklanır), aynı adrese günler sonra giden başka
   kuryenin brifinginde bu not, hafızasız ↔ hafızalı aynı rota. Telefon ekranı sağ panelde. */
(function (CM) {
  const DAY = 32, COURIER = 'O02';
  const NOTES = [
    { name: 'personal', text: 'site güvenliği kimlik istiyor, kayıt yaptırınca giriyorsunuz. yönetici Ahmet bey 0532 412 55 10', label: 'İsim ve telefon içeren not' },
    { name: 'noise', text: 'trafik berbattı bugün', label: 'Adresle ilgisiz not' },
    { name: 'park', text: 'sitenin önünde park yeri yok, aracı arka sokaktaki otoparka bırakıp yürüyün', label: 'Park yeri notu' },
    { name: 'access', text: 'asansör yok, 4. kata merdivenle çıkılıyor', label: 'Bina erişimi' },
  ];
  const STATUS = { saved: 'Kaydedildi', updated: 'Güncellendi', noise: 'Kaydedilmedi · adresle ilgisiz', uncertain: 'Adres belirsiz · kuryeye soru', rejected: 'Reddedildi' };
  let brief = null, route = null, demo = null, stops = [], door = new Map(), targetIdx = -1;
  let tool = null, marks = [], no = 0, next = null, gb = {};

  function camera(ll) {
    if (!CM.H.gl) return null;
    const lng = ll.map((q) => q[0]), lat = ll.map((q) => q[1]), w = innerWidth, h = innerHeight;
    const c = CM.H.map.cameraForBounds([[Math.min(...lng), Math.min(...lat)], [Math.max(...lng), Math.max(...lat)]],
      { padding: { left: w * 0.08, right: w * 0.36, top: h * 0.14, bottom: h * 0.3 }, bearing: -20 });
    return { center: c.center, zoom: Math.min(15.6, c.zoom + 0.1), pitch: 52, bearing: -20 };
  }
  const near = (ll) => ({ center: ll, zoom: 16.4, pitch: 60, bearing: -28 });

  // ------------------------------------------------------------ telefon
  function phone(top, body, alt) {
    CM.side(`<div class="phone"><div class="phone-top"><span>${top}</span></div><div class="phone-inner">${body}</div>${alt ? `<div class="phone-alt">${alt}</div>` : ''}</div><div class="phone-mod"><span class="mod" id="mod4"></span></div>`, 'open phone-panel');
    CM.writeMode(CM.$('mod4'));
  }
  function briefingScreen() {
    const y = stops.filter((d) => d.u).length, yn = stops.filter((d) => d.u && door.has(d.address)).length;
    phone(`${brief.courier_name} · ${CM.TYPE[brief.courier_type] || ''}`,
      `<div class="t-label">Sabah brifingi</div><div class="t-briefing">${CM.escape(brief.morning_briefing)}</div>`,
      '<button class="phone-button" id="listen4">▶ Dinle</button>');
    CM.$('listen4').onclick = () => CM.speech.say(brief.morning_briefing);
    return { y, yn };
  }
  function doorScreen(d, k) {
    const kay = (k.records || []).map((x) => `<span class="t-type">${CM.QUIRK[x.type] || x.type}</span>`).join('');
    const g = gb[d.address];
    phone(`${brief.courier_name} · ${d.order}. durak · ${CM.hhmm(d.eta)}`,
      `<div class="t-label">Kapıda</div><div class="t-sentence">${CM.escape(k.sentence)}</div><div class="t-types">${kay}</div>`,
      g ? `<div class="t-result good">${CM.escape(g)}</div>` :
        '<button class="phone-button good" id="gb-e">✓ Hâlâ geçerli</button><button class="phone-button" id="gb-h">✗ Değişmiş</button>');
    if (!g) {
      CM.$('gb-e').onclick = () => feedback(d, k, true);
      CM.$('gb-h').onclick = () => feedback(d, k, false);
    }
  }
  async function feedback(d, k, valid) {
    const ids = (k.records || []).map((x) => x.id).filter(Boolean);
    try {
      const r = await Promise.all(ids.map((record) => CM.api('/api/memory/feedback', { day: DAY, record, valid }, { name: record + (valid ? '' : '-x') })));
      const s = r[0] && r[0].record && r[0].record.sources;
      gb[d.address] = valid ? `Teyit edildi · kayıt ${ids.join(', ')}${s ? ` · ${s} kaynak` : ''}` : 'Hafızadan düşürüldü; bir daha söylenmeyecek';
    } catch (e) { gb[d.address] = 'Geri bildirim gönderilemedi: ' + (e.detail || e.message); }
    doorScreen(d, k);
  }

  // ------------------------------------------------------------ oynatma: başlangıçtan hedef durağa
  async function play(n) {
    const path = stops.slice(0, targetIdx + 1);
    if (!tool) tool = CM.H.mark(CM.toolEl(CM.PALET[brief.route.route % CM.PALET.length], brief.courier_name), path[0].ll, 'center');
    tool.dur = false; tool.position(path[0].ll); tool.transparent(1);
    CM.H.end({ ...near(path[0].ll), zoom: 15.4 }, 1600);
    await CM.wait(1200);
    for (let i = 1; i < path.length && n === no; i++) {
      const d = path[i];
      await CM.H.execute(tool, [path[i - 1].ll, d.ll], 520);
      if (n !== no) return;
      if (CM.H.gl) CM.H.map.easeTo({ center: d.ll, duration: 520 });
      CM.figureMoment([{ v: d.order, l: 'durak' }, { v: CM.hhmm(d.eta), l: 'planlanan varış' }], `${d.u ? 'Bölgeye yabancı durak' : 'Tanıdık durak'}${door.has(d.address) ? ' · hafızada not var' : ''}`);
      const k = door.get(d.address);
      if (k) {
        doorScreen(d, k);
        CM.H.end(near(d.ll), 700);
        await Promise.race([CM.speech.say(k.sentence), CM.wait(4200)]);
        await CM.wait(600);
      }
    }
  }

  // ------------------------------------------------------------ not
  // not çipleri + serbest not (yazı ya da bas-konuş: önce sunucu/Amazon Transcribe, yoksa tarayıcının ses tanıması; js/listen.js)
  function noteField() {
    const speech = window.CMListen && CMListen.available();
    return NOTES.map((q) => `<button class="phone-button chip-k" data-name="${q.name}">${q.label}</button>`).join('') +
      `<form class="phone-input" id="noteForm"><input id="note-text" autocomplete="off" placeholder="Kendi notunuz">${speech ? '<button type="button" class="phone-button" id="mik4">Bas-konuş</button>' : ''}<button class="phone-button good">Gönder</button></form>`;
  }
  function bindNoteField() {
    CM.$('side').querySelectorAll('.chip-k').forEach((b) => (b.onclick = () => sendNote(no, NOTES.find((q) => q.name === b.dataset.name))));
    CM.$('noteForm').onsubmit = (e) => { e.preventDefault(); const m = CM.$('note-text').value.trim(); if (m) sendNote(no, { name: 'serbest', text: m }); };
    const b = CM.$('mik4'), input = CM.$('note-text');
    if (!b || !window.CMListen) return;
    CMListen.pushToTalk({ button: b, input, base: CM.API, notify: (m) => { input.value = ''; input.placeholder = m; } });
  }

  async function sendNote(n, select) {
    const d = stops[targetIdx];
    phone(`${brief.courier_name} · ${d.order}. durak`, `<div class="t-label">Not bırak · 3 saniye</div><div class="t-note">“${CM.escape(select.text)}”</div><div class="t-wait">Hafıza Ajanı notu işliyor…</div>`);
    try {
      let r;
      try { r = await CM.api('/api/note', { day: DAY, courier: COURIER, text: select.text, lat: d.lat, lng: d.lng, minute: Math.round(d.eta) }, { name: select.name, ms: 60000 }); }
      catch (e) { if (e.noRecord) throw new Error('API yok: serbest not canlı Hafıza Ajanı ister; hazır notlardan birini seçin.'); throw e; }
      if (n !== no) return;
      const kv = r.personal_data_redacted;
      const good = r.status === 'saved' || r.status === 'updated';
      phone(`${brief.courier_name} · ${d.order}. durak`,
        `<div class="t-label">Not</div><div class="t-note">“${CM.escape(select.text)}”</div>
         <div class="badges"><span class="badge ${good ? 'good' : ''}">${good ? '✓' : '–'} ${STATUS[r.status] || r.status}</span>${kv ? '<span class="badge shield">Kişisel veri ayıklandı</span>' : ''}</div>
         ${r.hint ? `<div class="t-label">Hafızaya yazılan</div><div class="t-sentence small">${CM.escape(r.hint)}</div>` : ''}
         <div class="t-summary">${CM.escape(r.summary || '')}${r.address ? ` · ${CM.escape(r.address.label)}` : ''}${r.type ? ` · ${CM.QUIRK[r.type] || r.type}` : ''}</div>`,
        noteField());
      bindNoteField();
      CM.figure(good ? [{ v: CM.QUIRK[r.type] || r.type, boy: 'mid', l: 'adrese bağlandı' }, ...(kv ? [{ v: 'KVKK', boy: 'mid', l: 'kişisel veri kaydedilmedi' }] : [])] : [{ v: '—', boy: 'mid', l: 'hafızaya yazılmadı' }],
        'Hafıza kişiyi değil adresi anlatır: ad, telefon, yargı araç düzeyinde reddedilir');
    } catch (e) {
      phone(`${brief.courier_name} · ${d.order}. durak`, `<div class="t-label">Not</div><div class="t-result error">${CM.escape(e.detail || e.message)}</div>`, noteField());
      bindNoteField();
    }
  }

  async function nextCourier(n) {
    const d = stops[targetIdx], s = demo.next;
    if (!s) { CM.figure([{ v: '—', boy: 'mid', l: 'bu adrese sonraki günlerde teslimat yok' }]); return; }
    try {
      if (!next) next = await CM.api(`/api/briefing/${s.day}/${s.courier}`, null, { ms: 60000 });
      if (n !== no) return;
      const k = next.door_sentences.find((q) => q.address === d.address);
      phone(`Gün ${s.day} · ${next.courier_name} · ${CM.TYPE[next.courier_type] || ''}`,
        k ? `<div class="t-label">Kapıda · ${k.order}. durak</div><div class="t-sentence">${CM.escape(k.sentence)}</div><div class="t-summary">Kaynak: ${CM.escape(brief.courier_name)}'ın gün ${DAY} notu · kişi değil adres</div>`
          : `<div class="t-summary">Bu adres için kapı cümlesi yok (önce Not adımında notu bırakın).</div>`,
        k ? '<button class="phone-button" id="listen4B">▶ Dinle</button>' : '');
      if (k) { CM.$('listen4B').onclick = () => CM.speech.say(k.sentence); CM.speech.say(k.sentence); }
      CM.figure([{ v: `Gün ${s.day}`, boy: 'mid', l: 'aynı kapı' }, { v: next.courier_name, boy: 'mid', l: 'başka kurye' }],
        k ? 'Bilgi kişiden adrese taşındı: Gökhan şubesine döndü, not kapıda kaldı' : '');
    } catch (e) {
      CM.figure([{ v: '—', boy: 'mid', l: 'brifing alınamadı' }], CM.escape(e.detail || e.message));
    }
  }

  async function routeDiff(n) {
    const [meta, summary] = await Promise.all([CM.al('/api/meta'), CM.al('/api/summary').catch(() => null)]);
    if (n !== no) return;
    const hk = meta.critical && meta.critical.memory_gain;
    const type = summary && summary.summary && summary.summary.memory_routing && summary.summary.memory_routing.type;
    const od = type && type.borrowed, is_new = type && type.new;
    const k = route.comparison;
    CM.side('');
    if (hk) {
      CM.figure([{ v: CM.count(hk.memoryless_min), l: 'dk · aynı rota hafızasız', cls: 'faded' }, { v: CM.count(hk.memory_min), l: 'dk · hafızalı' }, { v: '−' + CM.count(hk.mins), l: 'dk daha kısa' }],
        `Aynı kurye, aynı duraklar, aynı gün, aynı rastgele sayılar (tek rota)` +
        (od ? ` · ödünç kuryelerde rota başına ortalama ${CM.count(od.min_gain_route_mean)} dk (p10–p90 ${CM.count(od.min_gain_route_p10)}–${CM.count(od.min_gain_route_p90)})` : '') +
        (is_new ? `, yeni kuryelerde ${CM.count(is_new.min_gain_route_mean)} dk` : '') +
        ` · planlanan süre ${CM.count(k.memoryless.planned_min)} → ${CM.count(k.memory.planned_min)} dk: bilinen püf noktası süresi plana girdi`);
    }
    CM.message(['Gökhan bu sokağı hiç görmedi,', 'ama sokak onu <span class="blue">tanıyor.</span>']);
    CM.curtain(true);
  }

  const S4 = {
    no: 4, name: 'Kapıda', stepCount: 5,
    title: 'Gün 32 · Gökhan, komşu şubeden · kapıda tek cümle',
    attribution: '<b>Uygulama verisi · 1 aylık geçmiş</b> · Harita: OpenFreeMap © OpenMapTiles © OpenStreetMap · konumlar Beykoz saha verisi, sonuçlar simülasyon',

    async enter() {
      no++;
      gb = {}; next = null;
      await CM.mapping();
      demo = await CM.demo();
      [brief, route] = await Promise.all([CM.api(`/api/briefing/${DAY}/${COURIER}`, null, { ms: 60000 }), CM.api(`/api/route/${DAY}/${COURIER}`, null, { ms: 60000 })]);
      const F = brief.stop_fields, ix = (a) => F.indexOf(a);
      door = new Map(brief.door_sentences.map((k) => [k.address, k]));
      const hz = route.comparison.memory, arrival = new Map((hz.order || []).map((a, i) => [a, (hz.expected_arrival || [])[i]]));
      const byA = new Map(brief.route.stops.map((s) => [s[ix('address')], s]));
      const order = hz.order && hz.order.length ? hz.order.filter((a) => byA.has(a)) : [...byA.keys()];
      stops = order.map((a, i) => { const s = byA.get(a); return { order: i + 1, address: a, lat: s[ix('lat')], lng: s[ix('lng')], eta: arrival.get(a) ?? s[ix('eta')], u: s[ix('unfamiliar')] === 1, ll: CM.position(a) }; })
        .filter((d) => d.ll);
      targetIdx = stops.findIndex((d) => d.address === demo.note_address);
      if (targetIdx < 0) targetIdx = Math.min(stops.length - 1, stops.findIndex((d, i) => i > 8 && d.u && !door.has(d.address)));
      { // 2D yedekte kamera yok: çerçeve rotaya oturur (MapLibre'de etkisiz)
        const lng = stops.map((d) => d.ll[0]), lat = stops.map((d) => d.ll[1]), p = 0.004;
        CM.H.frame([Math.min(...lng) - p, Math.min(...lat) - p, Math.max(...lng) + p, Math.max(...lat) + p]);
      }
      CM.adjust({ s4: 0, s4h: 0 });
      const path = { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: stops.map((d) => d.ll) } };
      CM.H.add({ id: 's-4-road', type: 'line', data: CM.gj([path]), layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: (S) => ({ 'line-color': '#1A1714', 'line-width': 2, 'line-opacity': 0.55 * S.s4 }) });
      const pt = CM.gj(stops.map((d) => CM.point(d.ll[1], d.ll[0], { c: door.has(d.address) ? CM.ARM.D : d.u ? '#D2261C' : '#8A8177', r: door.has(d.address) || d.u ? 6 : 4.5 })));
      CM.H.add({ id: 's-4-stop', type: 'circle', data: pt, paint: (S) => ({ 'circle-radius': ['get', 'r'], 'circle-color': ['get', 'c'], 'circle-opacity': S.s4, 'circle-stroke-color': '#FBF8F2', 'circle-stroke-width': 2, 'circle-stroke-opacity': S.s4 }) });
      const h = stops[targetIdx];
      CM.H.add({ id: 's-4-target', type: 'circle', data: CM.gj(h ? [CM.point(h.ll[1], h.ll[0], {})] : []), paint: (S) => ({ 'circle-radius': 16, 'circle-color': '#FBF8F2', 'circle-opacity': 0, 'circle-stroke-color': '#1A1714', 'circle-stroke-width': 3, 'circle-stroke-opacity': S.s4h }) });
      CM.closeTrace();
    },

    step(i, previous) {
      const n = ++no;
      CM.speech.cancel();
      CM.message([]); CM.curtain(false); CM.action(''); CM.cards('');
      CM.deleteMark(marks);
      if (tool) tool.dur = true;
      CM.tween({ s4: 1, s4h: i >= 2 && i <= 3 ? 1 : 0 }, 900);
      const h = stops[targetIdx];
      if (i === 0) {
        if (tool) tool.transparent(0);
        CM.H.end(camera(stops.map((d) => d.ll)), previous == null ? 2400 : 1200);
        const { y, yn } = briefingScreen();
        CM.figure([{ v: stops.length, l: 'durak' }, { v: brief.estimated_return, l: 'tahmini dönüş' }, { v: y, l: 'durak bölgeye yabancı', cls: 'red' }, { v: yn, l: 'tanesinde bugün kapıda ipucu' }],
          'Kırmızı: Gökhan bu bloğa hiç girmedi · mavi: adres hafızasında not var · dönüş saati kuryeye özgü tahmin');
        if (previous != null) CM.speech.say(brief.morning_briefing);
      } else if (i === 1) {
        briefingScreen();
        CM.figure([]);
        if (previous == null || previous > i) {           // geri gelindi: hedefte bekle
          if (tool) { tool.transparent(1); tool.position(h.ll); }
          CM.H.end(near(h.ll), 900);
        } else play(n);
      } else if (i === 2) {
        if (!tool) tool = CM.H.mark(CM.toolEl(CM.PALET[brief.route.route % CM.PALET.length], brief.courier_name), h.ll, 'center');
        tool.transparent(1); tool.position(h.ll);
        CM.H.end(near(h.ll), 1200);
        marks.push(CM.H.mark(CM.labelEl(`${h.order}. durak`, 'Gökhan yeni bir şey öğrendi'), h.ll, 'top'));
        phone(`${brief.courier_name} · ${h.order}. durak`, '<div class="t-label">Not bırak · 3 saniye</div><div class="t-summary">Sesli ya da yazılı; Hafıza Ajanı adrese bağlar, türünü çıkarır, kişisel veriyi ayıklar.</div>',
          noteField());
        bindNoteField();
        CM.figure([]);
        if (previous != null && previous < i) sendNote(n, NOTES[0]);
      } else if (i === 3) {
        if (tool) tool.transparent(0);
        CM.H.end({ ...near(h.ll), bearing: 20 }, 1400);
        marks.push(CM.H.mark(CM.labelEl(`Gün ${demo.next ? demo.next.day : ''}`, 'aynı adres, başka kurye'), h.ll, 'top'));
        nextCourier(n);
      } else if (i === 4) {
        if (tool) tool.transparent(0);
        CM.H.end(camera(stops.map((d) => d.ll)), 1400);
        routeDiff(n);
      }
    },

    leaving() {
      no++;
      CM.speech.cancel();
      if (tool) { tool.dur = true; tool.remove(); tool = null; }
      CM.deleteMark(marks);
      CM.message([]); CM.curtain(false);
      CM.cards(''); CM.figure([]); CM.action(''); CM.side('');
      CM.H.clear();
    },
  };
  CM.scenes = CM.scenes || {};
  CM.scenes[4] = S4;
})(window.CM);
