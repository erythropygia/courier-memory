/* Sahne 8 · Kapanış: (0) nasıl yaptık: AWS + Kiro (slayt 11), (1) sorumlu yapay zekâ (slayt 12), (2) pilot (slayt 12),
   (3) tek cümle. Modeller ve mod canlı /api/durum'dan; manşet /api/ekonomi'den. Sayılar (spec, görev, test) elle sayıldı:
   değişirse burada ve docs/sunum.md'de güncelleyin. */
(function (CM) {
  let status = null, extra = null, no = 0;
  const NAME = { 'anthropic.claude-opus-5-5': 'Claude Opus 5.5', 'anthropic.claude-sonnet-5-5': 'Claude Sonnet 5.5', 'anthropic.claude-haiku-5-5': 'Claude Haiku 5.5' };
  const AGENT = { orchestrator: 'Orkestratör', assignment: 'Atama', memory: 'Hafıza', harvest: 'Hasat', briefing: 'Brifing' };
  const MOD = { mock: 'mock · kurallı yedek', live: 'canlı · Bedrock', record: 'canlı · kayıt', replay: 'kayıttan oynatma' };

  function how() {
    const m = (status && status.models) || {};
    const models = Object.keys(AGENT).map((k) => `<tr><td>${AGENT[k]}</td><td>${CM.escape(NAME[m[k]] || m[k] || '—')}</td></tr>`).join('');
    CM.board(`<div class="two equal">
      <div class="chart card-text"><div class="g-title">Amazon Bedrock'ta Claude</div>
        <ul class="items">
          <li><b>Beş ajan, araç kullanarak</b> karar verir; hesap deterministik araçlarda, iz her adımı gösterir.</li>
          <li><b>Dört mod, aynı iz:</b> canlı (Bedrock) · kayıt · kayıttan oynatma · kurallı yedek. İnternet ya da kota giderse demo durmaz.</li>
          <li><b>İşe göre model ve önbellek:</b> LLM maliyeti tasarrufun %1,4'ünden %0,1'ine iner (Sahne 7).</li>
          <li><b>Amazon Polly:</b> kapıda tek cümle sesli (<code>/api/speech</code>).</li>
          <li><b>Sırada:</b> DynamoDB'de hafıza, Bedrock AgentCore Runtime, Transcribe ile sesli not.</li>
        </ul>
        <table class="models"><thead><tr><th>Ajan</th><th>Model · ${CM.escape(MOD[status && status.mode] || (status && status.mode) || 'API yok')}</th></tr></thead><tbody>${models}</tbody></table></div>
      <div class="chart card-text"><div class="g-title">Kiro ile: önce spec, sonra kod</div>
        <ul class="items">
          <li><b>Steering (5):</b> ürün, yapı, teknoloji, sunum dili, veri ve KVKK kuralları; her ajan ve her ekran bunlara uyar.</li>
          <li><b>Altı spec:</b> dünya ve simülatör · ajanlar · orkestratör · ekonomi · API ve arayüz · sabah akışı; her biri gereksinim → tasarım → görev (83 görev).</li>
          <li><b>Kabul testleri:</b> 104 test (99 hızlı + 5 yavaş); simülatör ile ajanın aynı rotayı çıkardığı 408/408 birebir.</li>
          <li><b>Yeniden kurulum kiti:</b> ürün kodu olmadan spec + testler; Kiro sıfırdan kurar (tek kişi ya da üç kişi paralel).</li>
          <li><b>Faz notları:</b> her fazın kararı, rakamı ve devri yazılı; "bu rakam nereden?" sorusunun cevabı tek komut.</li>
        </ul></div></div>`, 'full mid');
    CM.figure([{ v: 5, l: 'ajan' }, { v: 6, l: 'spec' }, { v: 104, l: 'kabul testi' }], 'Spec\'leri ve steering dosyalarını <code>.kiro/</code> klasöründen açıp gösterin');
  }

  function responsible() {
    const K = [
      ['Kişi değil adres', 'Hafıza binayı ve kapıyı anlatır. Ad, telefon, sağlık, yaş ve davranış yargısı araç düzeyinde reddedilir; ses metne çevrilince silinir (Sahne 4).'],
      ['Performans puanı yok', 'Kurye–bölge uyumu yalnız atama girdisidir: kurye sıralaması, disiplin ya da prim yok. Kimse kalıcı olarak "kötü rotaya" kilitlenmez.'],
      ['Temassız zincir, acil durumda insan', 'Normal günde plan müdüre gitmeden kesinleşir. Müdür yalnız acil durumda yetkili: kapasite açığı kapanmıyor, ciddi fazla mesai, ajan planı çıkaramadı. Eşikler deterministik kodda; her karar izde okunur (Sahne 3).'],
      ['Dürüst rakam', 'Her ekranda "Uygulama verisi · 1 aylık geçmiş"; maliyetler tahmini parametredir; simülasyon mekanizmayı gösterir, büyüklüğü pilot ölçer. Seçilmiş örnekler etiketli.'],
    ];
    CM.board(`<div class="quad">${K.map(([a, b]) => `<div class="chart card-text"><div class="g-title">${a}</div><p>${b}</p></div>`).join('')}</div>`, 'full mid');
    CM.figure([]);
  }

  function pilot() {
    CM.board(`<div class="two equal">
      <div class="chart card-text"><div class="g-title">Pilot: 4 hafta, tek şube, A/B</div>
        <ul class="items">
          <li>Aynı şube, aynı günler: dinamik rotaların yarısı <b>hafızalı</b>, yarısı <b>hafızasız</b>.</li>
          <li>Çekirdek bölgeli plan her iki yarıda da aynı; fark yalnız hafıza, hasat ve brifing.</li>
          <li>Haftalık müdür ve kurye geri bildirimi; "hâlâ geçerli mi?" oranı hafızanın tazeliğini ölçer.</li>
          <li><b>İlk iş:</b> başarısız teslimde saat ve neden alanı doldurulur (teslim zamanı analizi bunu ister; bugünkü kayıtta boş).</li>
        </ul></div>
      <div class="chart card-text"><div class="g-title">Ölçülecekler</div>
        <ul class="items">
          <li>İlk denemede teslim ve bilgiyle önlenebilir başarısız / 100 durak</li>
          <li>Fazla mesai dk/gün ve vardiya bandında kurye payı</li>
          <li>Yeni ve komşu şubeden gelen kuryenin ilk haftası</li>
          <li>LLM maliyeti (canlı token ölçümü) ↔ operasyon kazancı</li>
          <li>Simülasyonun öngördüğü aralıkla karşılaştırma: tutarsa ölçek, tutmazsa parametre düzeltilir</li>
        </ul></div></div>`, 'full mid');
    CM.figure([{ v: '4 hafta', boy: 'mid', l: 'süre' }, { v: '1 şube', boy: 'mid', l: 'kapsam' }, { v: 'A/B', boy: 'mid', l: 'yarı hafızalı' }], 'Büyüklüğü simülasyon değil pilot söyler');
  }

  function last() {
    // QR: geçmiş demo koşusunda her ajanın aldığı, düşündüğü ve verdiği (ui/demo/, build.py --url ile üretilir)
    CM.board(`<div class="demo-qr"><img src="data/demo-qr.svg" alt="Demo izi QR kodu" onerror="this.closest('#board').innerHTML=''">
      <p><b>Telefonunuzla okutun</b>Ajanlar ne aldı, ne düşündü, ne verdi: geçmiş demo koşusu adım adım</p></div>`, 'qr');
    CM.message(['Kuryeyi kaydırmıyoruz,', 'sınırı esnetiyoruz.', 'Bilgi kişiden <span class="blue">adrese</span> taşınır.']);
    const m = extra && extra.headline;
    CM.figure(m ? [{ v: CM.count(m.savings_tl_year / 1e6, 1) + ' mn', boy: 'mid', l: 'TL/yıl · şube başına' }, { v: `${m.quality.fails_per_day_current} → ${m.quality.fails_per_day_memory}`, boy: 'mid', l: 'başarısız teslim/gün' }] : [],
      'Dinamik planlamaya ajansız geçmek maliyeti artırır; Courier Memory ile aynı geçiş kaliteyi korur');
  }

  const S8 = {
    no: 8, name: 'Kapanış', stepCount: 4,
    title: 'Nasıl yaptık · sorumlu yapay zekâ · pilot',
    attribution: '<b>Uygulama verisi · 1 aylık geçmiş</b> · tahmini parametrelerle',
    async enter() {
      no++;
      CM.curtain(true);
      CM.H.end({ center: [29.19, 41.14], zoom: 11.2, pitch: 30, bearing: -8 }, 1500);
      [status, extra] = await Promise.all([CM.al('/api/status').catch(() => null), CM.al('/api/economics').catch(() => null)]);
    },
    step(i) {
      no++;
      CM.curtain(true); CM.message([]);
      CM.$('scene-title').textContent = ['Nasıl yaptık: AWS + Kiro', 'Sorumlu yapay zekâ', 'Pilot', 'Courier Memory'][i] || S8.title;
      if (i === 0) how();
      else if (i === 1) responsible();
      else if (i === 2) pilot();
      else last();
    },
    leaving() { no++; CM.board(''); CM.figure([]); CM.message([]); CM.curtain(false); },
  };
  CM.scenes = CM.scenes || {};
  CM.scenes[8] = S8;
})(window.CM);
