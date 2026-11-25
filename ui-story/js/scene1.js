/* Sahne 1 · Sorun (gerçek veri): 18 sabit bölge → yeni yapının dinamik bölgeleri → bedel (yabancı sokak). */
(function (CM) {
  // bölge / küme paleti: bej zeminde ayrışan, doygunluğu dengeli kategorik renkler
  CM.PALET = ['#C8553D', '#2A7F62', '#E0A030', '#3A6EA5', '#9C4F7E', '#6E9A4A', '#D9783F', '#2D5F86', '#B08A2E', '#5D6FB0',
    '#3F8C8C', '#B23A3A', '#7E8F24', '#CF8F1D', '#1F7090', '#A35A33', '#6B5B95', '#3E8E41', '#C26E8A', '#4B6E3A',
    '#D0A15C', '#3C7DBF', '#8C3B2E', '#5F9EA0', '#A0703C', '#7A9C6A'];
  const EXTRA = ['#1A1714', '#5A524A', '#857B70', '#3A332D'];
  const GRAY = '#A59A8C';
  const RED = '#D2261C';

  let data = null, branch = null, stepNo = 0;
  
  function camera() {
    const b = [[29.064, 41.047], [29.332, 41.235]];
    if (!CM.H.gl) return null;
    const w = innerWidth, h = innerHeight;
    const c = CM.H.map.cameraForBounds(b, { padding: { left: w * 0.27, right: w * 0.02, top: h * 0.05, bottom: h * 0.12 }, bearing: -8 });
    return { center: c.center, zoom: c.zoom + 0.32, pitch: 40, bearing: -8 };
  }
  const NEAR = { center: [29.0975, 41.1365], zoom: 15.4, pitch: 62, bearing: -38 };

  // Slayt 5: zorunlu anlar → dört ajan + orkestratör → tek maliyet fonksiyonu (araç adları kodla aynı)
  function agents() {
    const AJ = [
      ['Atama', 'Çekirdek bölgeli plan: kurye kendi bölgesinde, sınır ve fazla iş esner; "ya şöyle olursa?" sorusunu araçla yanıtlar.', 'day_summary · solve_assignment · respond'],
      ['Hafıza', 'Kurye notunu adrese bağlar, türünü ve süresini çıkarır; kişisel veriyi ayıklar, bayat bilgiyi unutur.', 'near_addresses · address_memory · write_memory'],
      ['Hasat', 'Bilgiyi kişiden toplar: hafızası boş adres için kıdemliye hedefli soru; kayıtlardan kalıp ve teyit.', 'memory_gaps · recurring_failure · save_questions'],
      ['Brifing', 'Sabah brifingi; kapıya yaklaşınca tek cümle; "hâlâ geçerli mi?" geri bildirimini hafızaya döndürür.', 'route_risks · compute_route'],
    ];
    CM.board(`<div class="diagram">
      <div class="sm-moments"><span>İzin</span><span>Ayrılma</span><span>Yeni kurye</span><span>Komşu şubeden kurye</span><span>Kampanya</span><b>→ bilgi kişiden adrese taşınır</b></div>
      <div class="sm-orch"><div class="sm-name">Orkestratör</div><div class="sm-ne">Günü yönetir: hacim → kapasite açığı → kim gitsin → atama → teslim saati → rota → müdüre gerekçeli öneri. Karar modelde, hesap araçlarda; son onay insanda.</div>
        <div class="sm-tool">read_volume · capacity_gap · neighbor_candidates · core_assignment · delivery_time_analysis · time_alternatives · compute_route · present_proposal</div></div>
      <div class="sm-dort">${AJ.map(([name, ne, ar]) => `<div class="sm-aj"><div class="sm-name">${name}</div><div class="sm-ne">${ne}</div><div class="sm-tool">${ar}</div></div>`).join('')}</div>
      <div class="sm-cost"><div class="sm-f">beklenen_başarısızlık(kurye, küme) = Σ<sub>durak</sub> P(başarısız | blok zorluğu, kurye×blok uyumu, [tanıdık <b>veya</b> hafızada geçerli not])</div>
        <div class="sm-c">Hafıza, optimizasyona serbestlik kazandırır: notu olan durak, kurye bloğu tanımasa da güvenlidir.</div></div></div>`, 'full diagram-p');
  }

  const S1 = {
    no: 1, name: 'Sorun', stepCount: 8,
    title: 'Beykoz şubesi · gerçek teslimat verisi',
    attribution: '<b>Gerçek veri</b> · Beykoz şubesi teslimatları, 4–8 Mayıs 2026 · Harita: OpenFreeMap © OpenMapTiles © OpenStreetMap katkıcıları',

    async enter() {
      if (!data) data = await (await fetch('data/scene1.json')).json();
      CM.adjust({ s1in: 0, w1: 0, w2: 0, w3: 0 });
      CM.H.frame([29.064, 41.047, 29.332, 41.235]);
      const zr = (i) => CM.PALET[i % CM.PALET.length];
      const kr = (col) => (col < data.figure.zone ? zr(col) : EXTRA[(col - data.figure.zone) % EXTRA.length]);
      const zones = CM.gj(data.zones.map((z) => CM.multi(z.rings, { c: zr(z.i), d: z.d })));
      const dyn = CM.gj(data.dyn.map((z) => CM.multi(z.rings, { c: zr(z.i + 3), d: z.d })));
      const dyn5 = CM.gj(data.dyn5.map((z) => CM.multi(z.rings, { c: zr(z.i + 7), d: z.d })));
      const p4 = CM.gj(data.pts.map((p) => CM.point(p[0], p[1], { co: kr(p[3]), cn: p[4] >= 0 ? zr(p[4] + 3) : GRAY, d: p[5] })));
      const p5 = CM.gj(data.pts5.map((p) => CM.point(p[0], p[1], { c: zr(p[2] + 7), u: p[3], d: p[4] })));
      const rad = ['interpolate', ['linear'], ['zoom'], 10, 2, 11, 2.4, 13, 3.4, 16, 6];
      const H = CM.H;

      const g = CM.dg, NB = 10, NF = 8;
      const fill = (o) => ({ 'fill-color': ['get', 'c'], 'fill-opacity': 0.3 * o });
      const line = (o) => ({ 'line-color': ['get', 'c'], 'line-width': 1.6, 'line-opacity': 0.95 * o });
      const dot = (color, o, r = rad) => ({ 'circle-radius': r, 'circle-color': color, 'circle-opacity': o, 'circle-stroke-color': '#FBF8F2', 'circle-stroke-width': 0.8, 'circle-stroke-opacity': o });
      // sabit bölgeler: giriş (s1in), dinamik bölgeye dönüşümde çıkış (w1)
      const oZon = (S, mins) => g(S.s1in, mins) * (1 - g(S.w1, mins));
      const oDyn = (S, mins) => g(S.w1, mins) * (1 - g(S.w2, mins));
      H.add({ id: 's1-zon', type: 'fill', data: zones, box: NF, paint: (S, mins) => fill(oZon(S, mins)) });
      H.add({ id: 's1-zon-c', type: 'line', data: zones, box: NF, paint: (S, mins) => line(oZon(S, mins)) });
      H.add({ id: 's1-dyn', type: 'fill', data: dyn, box: NF, paint: (S, mins) => fill(oDyn(S, mins)) });
      H.add({ id: 's1-dyn-c', type: 'line', data: dyn, box: NF, paint: (S, mins) => line(oDyn(S, mins)) });
      H.add({ id: 's1-dyn5', type: 'fill', data: dyn5, box: NF, paint: (S, mins) => fill(g(S.w2, mins) * (1 - 0.75 * S.w3)) });
      H.add({ id: 's1-dyn5-c', type: 'line', data: dyn5, box: NF, paint: (S, mins) => line(g(S.w2, mins) * (1 - 0.6 * S.w3)) });
      // 4 Mayıs durakları: kurye rengi → küme rengi (w1), ertesi güne geçişte çıkış (w2)
      H.add({ id: 's1-p4o', type: 'circle', data: p4, box: NB, paint: (S, mins) => dot(['get', 'co'], g(S.s1in, mins) * (1 - g(S.w1, mins))) });
      H.add({ id: 's1-p4n', type: 'circle', data: p4, box: NB, paint: (S, mins) => dot(['get', 'cn'], g(S.w1, mins) * (1 - g(S.w2, mins))) });
      // 5 Mayıs durakları: giriş (w2); bedel (w3): yabancı → kırmızı, tanıdık → gri
      H.add({ id: 's1-p5', type: 'circle', data: p5, box: NB, paint: (S, mins) => dot(['get', 'c'], g(S.w2, mins) * (1 - g(S.w3, mins))) });
      H.add({ id: 's1-p5t', type: 'circle', data: p5, box: NB, filtre: ['==', ['get', 'u'], 0], paint: (S, mins) => dot(GRAY, g(S.w2, mins) * g(S.w3, mins)) });
      H.add({ id: 's1-p5y', type: 'circle', data: p5, box: NB, filtre: ['==', ['get', 'u'], 1],
        paint: (S, mins) => dot(RED, g(S.w2, mins) * g(S.w3, mins), ['interpolate', ['linear'], ['zoom'], 11, 2.6, 13, 3.8, 16, 6.5]) });
      branch = H.mark(CM.branchEl(), [data.depot[1], data.depot[0]], 'left');
    },

    // Adımlar: 0 açılış (slayt 1) · 1–5 sorun (gerçek veri) · 6 ilke: kaydırmıyoruz, sınırı esnetiyoruz (slayt 4) ·
    // 7 zorunlu anlar için hafıza: ajanlar + tek maliyet (slayt 5). 6–7 uygulama verisi (atıf değişir).
    step(i, previous) {
      const R = data.figure, H = CM.H;
      const next = previous == null || i > previous;
      const n = ++stepNo;
      const appData = i >= 6;
      CM.$('attribution').innerHTML = appData ? '<b>Uygulama verisi</b> · uzun dönem, 60 iş günü · bu varsayımlar altında' : S1.attribution;
      CM.$('scene-title').textContent = i === 0 ? 'Courier Memory' : i === 6 ? 'İlke: kuryeyi değil sınırı kaydırıyoruz' : i === 7 ? 'Zorunlu anlar için hafıza: dört ajan, bir orkestratör' : S1.title;
      document.getElementById('curtain').classList.toggle('open', i === 0 || i >= 5);
      CM.message(i === 0 ? ['“Sitenin girişi arka sokaktan.”', 'Bu bilgi bir kuryenin <span class="red">kafasında.</span>']
        : i === 5 ? ['Verimlilik geliyor,', 'ama kuryenin bilgisi <span class="red">kayboluyor.</span>']
        : i === 6 ? ['Kuryeyi kaydırmıyoruz,', 'sınırı <span class="blue">esnetiyoruz.</span>'] : []);
      CM.board('');
      if (i === 0) {
        CM.tween({ s1in: 0, w1: 0, w2: 0, w3: 0 }, next ? 0 : 900);
        if (previous == null) H.skip(NEAR); else H.end(NEAR, 2200);
        CM.figure([]);
      } else if (i === 1) {
        if (previous == null || previous === 0) {
          if (previous == null) H.skip(NEAR);
          setTimeout(() => n === stepNo && H.end(camera(), 5200), previous == null ? 500 : 100);
          setTimeout(() => n === stepNo && CM.tween({ s1in: 1 }, 2600, CM.easing.out), previous == null ? 2600 : 1800);
        } else CM.tween({ s1in: 1 }, 600);
        CM.tween({ w1: 0, w2: 0, w3: 0 }, next ? 0 : 1600);
        CM.figure([{ v: R.zone, l: 'sabit bölge' }, { v: R.courier_today, l: 'kurye' }],
          `${R.courier_today - R.courier_extra} bölge kuryesi + ${R.courier_extra} ek kurye · 4 Mayıs 2026 · her nokta bir teslim noktası, kendi kuryesinin renginde`);
      } else if (i === 2) {
        CM.tween({ s1in: 1, w2: 0, w3: 0 }, 400);
        CM.tween({ w1: 1 }, next ? 3400 : 1200, CM.easing.io);
        if (previous == null) H.skip(camera());
        const ag = Math.round((1 - R.vehicle_days_5[1] / R.vehicle_days_5[0]) * 100), path = Math.round((1 - R.road_km_5[1] / R.road_km_5[0]) * 100);
        CM.figure([{ v: R.courier_new, l: 'kurye' }, { v: '−%' + ag, l: 'araç-gün' }, { v: '−%' + path, l: 'yol' }],
          'Yeni yapı: bölgeler her sabah o günün gönderisine göre çizilir · araç-gün ve yol 4–8 Mayıs toplamı, iki tarafta aynı rota yöntemi');
      } else if (i === 3) {
        CM.tween({ s1in: 1, w1: 1, w3: 0 }, 400);
        CM.tween({ w2: 1 }, next ? 3000 : 1000, CM.easing.io);
        if (previous == null) H.skip(camera());
        CM.figure([{ v: 'Ertesi gün', boy: 'mid', l: 'bölgeler yeniden çizilir' }], '5 Mayıs 2026 · aynı sokak bugün başka kümede');
      } else if (i === 4) {
        CM.tween({ s1in: 1, w1: 1, w2: 1 }, 300);
        CM.tween({ w3: 1 }, next ? 2600 : 600, CM.easing.io);
        if (previous == null) H.skip(camera());
        CM.figure([{ v: CM.percent(R.unfamiliar_blind), l: 'durak yabancı sokakta', cls: 'red' }, { v: CM.percent(R.unfamiliar_current), l: 'bugün', cls: 'faded' }],
          `Kurye geçmişine bakılmadan atanırsa · 4–8 Mayıs ortalaması (haritadaki gün, 5 Mayıs: ${CM.percent(R.display_unfamiliar_share)}) · yabancı = kuryenin daha önce girmediği ~300 m blok`);
      } else if (i === 5) {
        CM.tween({ s1in: 1, w1: 1, w2: 1, w3: 1 }, 300);
        if (previous == null) H.skip(camera());
        CM.figure([]);
      } else if (i === 6) {
        CM.tween({ s1in: 1, w1: 1, w2: 1, w3: 0 }, 600);
        if (previous == null) H.skip(camera());
        CM.figure([]);
        CM.al('/api/summary').then((oz) => {
          if (n !== stepNo) return;
          const U = oz.long_term && oz.long_term.summary.arms;
          if (!U) return;
          const kb = (k) => CM.percent(1 - U[k].unfamiliar_share);
          CM.figure([{ v: kb('A'), l: 'bugün · sabit bölge', cls: 'faded' }, { v: kb('B'), l: 'yeni yapı, ajansız', cls: 'red' }, { v: kb('D'), l: 'yeni yapı + Courier Memory' }],
            'Kendi bölgesinde durak payı · çekirdek bölgeli dinamik plan: kurye kendi bölgesinde kalır, yalnız sınır ve fazla iş esner · kaydırma yalnız zorunlu anlarda: izin, ayrılma, yeni ve komşu şubeden kurye, kampanya');
        }).catch(() => {});
      } else if (i === 7) {
        CM.tween({ s1in: 1, w1: 1, w2: 1, w3: 0 }, 600);
        if (previous == null) H.skip(camera());
        CM.figure([]);
        agents();
      }
    },

    leaving() {
      stepNo++;
      document.getElementById('curtain').classList.remove('open');
      CM.board('');
      CM.message([]);
      CM.figure([]);
      if (branch) branch.remove();
      CM.H.clear();
    },
  };
  CM.scenes = CM.scenes || {};
  CM.scenes[1] = S1;
})(window.CM);
