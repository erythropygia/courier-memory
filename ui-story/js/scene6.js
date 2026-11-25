/* Sahne 6 · Öğrenme: (0) yeni kurye ilk haftası (Hedef 1, /api/ogrenme), (1) dört yapı gün gün + başarısızlık nedenleri,
   (2) varsayımı değiştirin: sağlamlık taraması (81 kombinasyon; D − A ve D − C), (3) kalibrasyon x/14, (4) hafızanın parça parça
   katkısı (ablasyon). (1) ve (3) eski tek sayfanın Simülasyon sekmesinden taşındı. Harita perdenin arkasında. */
(function (CM) {
  let og = null, oz = null, no = 0;
  const pp = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + CM.count(Math.abs(v), 2);

  function curve(n) {
    const S = og.series;
    const point = (q) => q.map((p) => ({ x: p.day, y: p.preventable_100, alt: p.alt, top: p.top }));
    const p = CM.board('<div id="g6"></div>', 'full');
    const senior = og.senior_mean && og.senior_mean.C;
    const { body } = CM.chartShell(p.querySelector('#g6'), {
      title: 'Yeni kurye ilk günlerinde: bilgiyle önlenebilir başarısız teslim / 100 durak',
      alt: `İşteki güne göre · ortalama ve %95 aralık (kurye × ${og.seeds.length} seed) · yeni kurye senaryosu`,
      legend: [{ name: 'Hafızalı (D)', color: CM.ARM.D }, { name: 'Hafızasız dünya (C)', color: CM.ARM.C }, { name: 'D rotası, o gün hafızasız', color: CM.GRAY }],
      table: {
        titles: ['İş günü', 'Hafızalı (D)', 'Hafızasız dünya (C)', 'D, hafızasız'],
        rows: S.D.map((d, i) => [d.day, CM.count(d.preventable_100, 2), S.C[i] ? CM.count(S.C[i].preventable_100, 2) : '', S.D_memoryless[i] ? CM.count(S.D_memoryless[i].preventable_100, 2) : '']),
      },
    });
    CM.lineChart(body, {
      series: [
        { name: 'D, hafızasız', label: 'o gün hafızasız', color: CM.GRAY, points: S.D_memoryless.map((q) => ({ x: q.day, y: q.preventable_100 })) },
        { name: 'Hafızasız dünya (C)', label: 'hafızasız (C)', color: CM.ARM.C, points: point(S.C) },
        { name: 'Hafızalı (D)', label: 'hafızalı (D)', color: CM.ARM.D, points: point(S.D) },
      ],
      x: { name: 'kuryenin şubedeki iş günü' }, y: { format: (v) => CM.count(v, 0) },
      lines: senior ? [{ y: senior, name: 'kıdemli düzeyi' }] : [],
      hintX: (x) => `${x}. iş günü`,
    });
    const f = og.first_week_paired_diff_C_minus_D.preventable_fails, u = og.mastery_day;
    CM.figure([{ v: CM.count(f[0], 1), l: 'önlenebilir başarısız daha az · ilk hafta' }, { v: `${u.C} → ${u.D}`, l: 'gün · kıdemli düzeyine' }],
      `Kurye başına ilk 5 iş günü, eşli fark C − D, %95 aralık ${CM.count(f[1], 1)}–${CM.count(f[2], 1)} · ${og.first_week_paired_diff_C_minus_D.n} kurye × seed · bu varsayımlar altında`);
  }

  // Eski "Simülasyon" sekmesinden: dört yapı gün gün (demo dönemi) ve başarısızlık nedenleri
  const REASON = { recipient_absent: 'Alıcı yok', address_not_found: 'Adres bulunamadı', closed: 'Kapalı', entry_failed: 'Giriş yapılamadı',
    recipient_unreachable: 'Alıcıya ulaşılamadı', wrong_deferral: 'Yanlış erteleme', other: 'Diğer' };
  const ARMS = ['A', 'B', 'C', 'D'];
  function dayByDay() {
    const D = oz.daily, arms = oz.summary.arms, preventable = new Set(oz.summary.preventable_reasons || []);
    CM.board('<div class="two"><div id="g6"></div><div id="g6b"></div></div>', 'full');
    const { body } = CM.chartShell(CM.$('g6'), {
      title: 'Dört yapı, aynı günler: ilk denemede teslim (%)',
      alt: `Demo dönemi ${D.A.length} iş günü · aynı gönderiler, aynı rastgele sayılar · kampanya ve izin dalgası günleri dahil`,
      legend: ARMS.map((k) => ({ name: k, color: CM.ARM[k] })),
      table: { titles: ['Gün', ...ARMS.map((k) => arms[k].label)], rows: D.A.map((r, i) => [r.day, ...ARMS.map((k) => CM.count(D[k][i].first_attempt_rate * 100, 2))]) },
    });
    CM.lineChart(body, {
      series: ARMS.map((k) => ({ name: arms[k].label, label: { A: 'A · bugün', B: 'B · ajansız', C: 'C · çekirdek', D: 'D · + hafıza' }[k], color: CM.ARM[k], points: D[k].map((r) => ({ x: r.day, y: r.first_attempt_rate * 100 })) })),
      x: { name: 'gün' }, y: { min: 90, max: 100, format: (v) => CM.count(v, Number.isInteger(v) ? 0 : 1) },
      hintX: (x) => `Gün ${x}`,
    });
    const reasons = Object.keys(arms.A.fail_by_reason).filter((n) => ARMS.some((k) => arms[k].fail_by_reason[n]));
    reasons.sort((a, b) => (preventable.has(b) - preventable.has(a)) || arms.B.fail_by_reason[b] - arms.B.fail_by_reason[a]);
    CM.$('g6b').innerHTML = `<div class="chart"><div class="g-head"><div><div class="g-title">Başarısızlık nedenleri</div>
      <div class="g-alt">${D.A.length} günde gönderi · <b>kalın</b>: bilgiyle önlenebilir</div></div></div>
      <table class="status reason"><thead><tr><th></th>${ARMS.map((k) => `<th class="s"><i class="key frame" style="background:${CM.ARM[k]}"></i>${k}</th>`).join('')}</tr></thead>
      <tbody>${reasons.map((n) => `<tr class="${preventable.has(n) ? 'preventable' : ''}"><td>${REASON[n] || n}</td>${ARMS.map((k) => `<td class="s${k === 'D' ? ' accent' : ''}">${CM.count(arms[k].fail_by_reason[n] || 0)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    const fa = (k) => CM.count(arms[k].first_attempt_rate * 100, 2);
    CM.figure([{ v: '%' + fa('D'), boy: 'mid', l: 'D · ilk denemede teslim' }, { v: '%' + fa('A'), boy: 'mid', l: 'A · bugün', cls: 'faded' }, { v: '%' + fa('B'), boy: 'mid', l: 'B · ajansız geçiş', cls: 'red' }],
      `Kalite bugünkü düzeyde kalır; ajansız geçişte bilgiyle önlenebilir nedenler (adres, giriş, alıcıya ulaşma) artar · C: çekirdek bölge, hafızasız · bu varsayımlar altında`);
  }

  function calibration() {
    const k = oz.calibration;
    if (!k) { CM.board(''); CM.figure([]); return; }
    const s = k.rows, uy = s.filter((r) => r.compatible).length;
    const fmt = (v) => (v < 0 ? '−' : '') + (Math.abs(v) >= 100 ? CM.count(Math.abs(v)) : Math.abs(v) >= 10 ? CM.count(Math.abs(v), 1) : CM.count(Math.abs(v), 3));
    CM.board(`<div class="chart"><div class="g-head"><div><div class="g-title">Kalibrasyon: uygulama verisi, saha verisinden türetilmiş toplu hedeflere uyumlu</div>
      <div class="g-alt">${CM.escape(k.source || '')} · hedef değerler şirket içi toplu özettir, gösterilmez (veri-kurallari.md)</div></div></div>
      <table class="status calib"><thead><tr><th>Ölçü</th><th class="s">Uygulama</th><th class="s">Uyum</th></tr></thead>
      <tbody>${s.map((r) => `<tr><td>${CM.escape(r.explanation || r.measure)}</td><td class="s">${r.value != null ? fmt(r.value) : ''}</td><td class="s">${r.compatible ? '✓ uyumlu' : '✗'}</td></tr>`).join('')}</tbody></table></div>`, 'full mid');
    CM.figure([{ v: `${uy}/${s.length}`, l: 'hedefe uyumlu' }],
      'Uygulama verisi saha verisinin toplu özelliklerine kalibre edilir · simülasyon mekanizmayı gösterir, büyüklüğü pilot ölçer');
  }

  function robustness() {
    const sw = oz.sweep, rows = sw.rows;
    const fa = (r, k) => r.arms[k].first_attempt_rate * 100;
    const da = rows.map((r) => fa(r, 'D') - fa(r, 'A')), dc = rows.map((r) => fa(r, 'D') - fa(r, 'C'));
    const p = CM.board('<div id="g6"></div>', 'full mid');
    const NAME = { 'outcome.eta_nav': 'yabancı sokakta bilgi eksikliği etkisi', 'quirks.prevalence_scale': 'püf noktası sıklığı', 'couriers.note_propensity_scale': 'not bırakma eğilimi', 'memory.parse_accuracy': 'Hafıza Ajanı doğruluğu' };
    const { body } = CM.chartShell(p.querySelector('#g6'), {
      title: 'Varsayımı değiştirin: ilk denemede teslim farkı (puan)',
      alt: `${rows.length} kombinasyon × ${sw.seeds} seed · değişen: ${sw.keys.map((k) => NAME[k] || k).join(', ')} · her nokta bir kombinasyon, çentik medyan`,
      table: { titles: ['Kombinasyon', 'D − A (puan)', 'D − C (puan)'], rows: rows.map((r, i) => [Object.values(r.params).join(' · '), pp(da[i]), pp(dc[i])]) },
    });
    CM.intervalChart(body, [
      { name: 'D − A: bugüne göre', alt: 'kalite bugünkü düzeyde', color: CM.ARM.A, values: da },
      { name: 'D − C: hafızanın katkısı', alt: 'her kombinasyonda pozitif', color: CM.ARM.D, values: dc },
    ], { format: (v) => pp(v) });
    const m = sw.headline, calib = oz.calibration;
    const fit = calib ? calib.rows.filter((s) => s.compatible).length + '/' + calib.rows.length : '';
    CM.figure([{ v: `%${CM.count(m.D_vs_C_pp.share_gt_0 * 100)}`, l: 'kombinasyonda D > C' }, { v: `−%${CM.count(-m.courier_day_D_vs_A_pct.max, 1)} … −%${CM.count(-m.courier_day_D_vs_A_pct.min, 1)}`, boy: 'mid', l: 'kurye-gün, bugüne göre' }],
      `D − A medyan ${pp(m.D_vs_A_pp.median)} puan; kombinasyonların %${CM.count(m.D_vs_A_pp.share_abs_le_0_15 * 100)}'i ±0,15 içinde · kalibrasyon ${fit} · simülasyon mekanizmayı gösterir, büyüklüğü pilot ölçer`);
  }

  function ablation() {
    const a = oz.ablation, v = a.variants;
    const ORDER = [['hint_only', 'Kapıda ipucu'], ['hint_harvest', 'İpucu + hasat'], ['hint_route', 'İpucu + hafızalı rota'], ['full', 'Tamamı: ipucu + hasat + rota + teslim zamanı']];
    const sat = ORDER.filter(([k]) => v[k]).map(([k, name]) => ({ name, o: v[k] }));
    const most = Math.max(...sat.map((s) => Math.abs(s.o.D_vs_C_preventable_pct.mean)));
    const html = `<div class="chart"><div class="g-head"><div><div class="g-title">Hafızanın katkısı parça parça (C'ye göre)</div>
      <div class="g-alt">${a.seeds} seed × ${a.scenarios.length} senaryo · ortalama [en düşük … en yüksek] · aynı dünya, yalnız hafızanın kullanımı değişir</div></div></div>
      <table class="abl"><thead><tr><th>Hafıza kullanımı</th><th>Önlenebilir başarısız</th><th></th><th class="s">Fazla mesai dk/gün</th><th class="s">Km/gün</th></tr></thead><tbody>
      ${sat.map(({ name, o }) => {
        const p = o.D_vs_C_preventable_pct, f = o.overtime_D_minus_C, k = o.km_D_minus_C;
        return `<tr><td>${name}</td><td class="s b">−%${CM.count(-p.mean, 1)} <span>[${CM.count(-p.max, 1)} … ${CM.count(-p.min, 1)}]</span></td>
          <td class="bar-fill"><i style="width:${(Math.abs(p.mean) / most) * 100}%"></i></td>
          <td class="s">${CM.marked(f.mean)} <span>[${CM.marked(f.min)} … ${CM.marked(f.max)}]</span></td><td class="s">${CM.marked(k.mean, 1)}</td></tr>`;
      }).join('')}</tbody></table></div>`;
    CM.board(html, 'full mid');
    const t = v.full;
    CM.figure([{ v: `−%${CM.count(-t.D_vs_C_preventable_pct.mean, 0)}`, l: 'önlenebilir başarısız' }, { v: CM.marked(t.overtime_D_minus_C.mean), l: 'dk/gün fazla mesai' }],
      `Önlenebilir başarısızdaki düşüş neredeyse tamamen kapıdaki ipucundan; rota ve teslim zamanı ilk denemeye değil fazla mesaiye katkı verir (${CM.marked(v.hint_only.overtime_D_minus_C.mean)} → ${CM.marked(t.overtime_D_minus_C.mean)} dk/gün), km biraz artar · her satır ayrı simülasyon · bu varsayımlar altında`);
  }

  const S6 = {
    no: 6, name: 'Öğrenme', stepCount: 5,
    title: 'Yeni kurye daha hızlı öğrenir · varsayımı değiştirin',
    attribution: '<b>Uygulama verisi · 1 aylık geçmiş</b> · saha verisinin toplu özelliklerine kalibre · bu varsayımlar altında',
    async enter() {
      no++;
      CM.H.end({ center: [29.19, 41.14], zoom: 11.2, pitch: 30, bearing: -8 }, 1500);
      CM.curtain(true);
      [og, oz] = await Promise.all([CM.al('/api/learning'), CM.al('/api/summary')]);
    },
    step(i) {
      no++;
      CM.curtain(true); CM.hideHint();
      if (i === 0) curve();
      else if (i === 1) dayByDay();
      else if (i === 2) robustness();
      else if (i === 3) calibration();
      else ablation();
    },
    leaving() { no++; CM.board(''); CM.figure([]); CM.curtain(false); CM.hideHint(); },
  };
  CM.scenes = CM.scenes || {};
  CM.scenes[6] = S6;
})(window.CM);
