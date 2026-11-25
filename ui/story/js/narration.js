/* Anlatım satırı: her adımda alt çubuğun üstünde "Ne oluyor · Ekranda · Veri". Ekrandaki rakamlar veriden gelir; buradaki
   metinler rakam içermez (veri değişince eskimesin), neyin nasıl gösterildiğini anlatır. A tuşu açar/kapatır.
   Sahne 2–3'ün tek adımı var: canlı akış ajanın izini kendi ekranında gösterir (ui/flow/). */
(function (CM) {
  const A = (ne, screen, data) => ({ ne, screen, data });
  const SIM = 'Uygulama verisi';

  CM.NARRATION = {
    1: [
      A('Açılış. Kurye işini kafasındaki bilgiyle yapar: hangi sitenin girişi arka sokakta, kim öğlen evde yok. Bu bilgi hiçbir sistemde kayıtlı değil.',
        'Şubenin bölgesi sokak düzeyinde; büyük yazı sunumun tek cümlesi.', 'Harita gerçek (OpenStreetMap).'),
      A('Bugün şube sabit bölgelerle çalışıyor: her kuryenin yıllardır aynı bölgesi var, sokakları ezbere bilir.',
        'Her nokta bir teslim noktası, kendi kuryesinin renginde; rakamlar bölge ve kurye sayısı.', 'Gerçek teslimat verisi, tek gün (bu sahnenin haritası tek gerçek veri istisnasıdır).'),
      A('Yeni yapı: bölgeler her sabah o günün gönderisine göre yeniden çizilir. Aynı iş daha az kurye ve daha az yolla yapılır.',
        'Renkli alanlar o günün dinamik bölgeleri; rakamlar kurye, araç-gün ve yol farkı.', 'Gerçek veri, beş günlük toplam; iki tarafta aynı rota yöntemi.'),
      A('Ertesi gün bölgeler yine değişir: aynı sokak bugün başka bir kümeye, başka bir kuryeye düşer.',
        'Bölge sınırlarının bir günden ötekine kayması.', 'Gerçek veri, ertesi gün.'),
      A('Bedeli: kuryeler geçmişine bakılmadan atanırsa durakların çoğu kuryenin hiç girmediği sokaklarda kalır; kafadaki bilgi boşa gider.',
        'Kırmızı rakam: yabancı sokaktaki durak payı; soluk rakam: bugünkü pay.', 'Gerçek veri; yabancı = kuryenin daha önce girmediği ~300 m blok.'),
      A('Sorunun özeti: verimlilik geliyor, ama kuryenin bilgisi kayboluyor.', 'Ara başlık.', '—'),
      A('İlke: kuryeyi kaydırmıyoruz, sınırı esnetiyoruz. Kurye kendi çekirdek bölgesinde kalır; yalnız sınırdaki ve fazla iş esner.',
        'Üç rakam: kendi bölgesindeki durak payı · bugün · ajansız yeni yapı · Courier Memory.', `${SIM} buradan başlar (60 iş günü); saha verisinin toplu özelliklerine kalibre edildi.`),
      A('Zorunlu anlar (izin, ayrılma, yeni ya da komşu şubeden kurye, kampanya) için dört ajan ve onları yöneten bir orkestratör.',
        'Şema: ajanlar, araçları ve hepsinin kullandığı tek maliyet.', 'Mimari; araç adları koddakiyle aynı.'),
    ],
    2: [
      A('Gün 32, Çarşamba, kampanya günü, saat 09:00. Gönderiler ve kadro belli; komşu şubeden ödünç gelen kurye bölgeyi bilmiyor. "Günü planla" ajan zincirini canlı başlatır.',
        'Gri noktalar olağan bir Çarşamba\'nın teslim noktaları; sağ altta canlı akışın QR kodu (izleyiciler telefonda izler).', `${SIM}; konumlar saha verisinden.`),
    ],
    3: [
      A('Zincir canlı: Orkestratör günü planlar, acil durum yoksa plan müdüre gitmeden kesinleşir; Brifing kuryeye anlatır, Hafıza Ajanı kapıdaki notu adrese yazar, durak kartı sonraki kuryeye söyler, Hasat, Değerlendirme ve Bölge ajanları ertesi günü hazırlar.',
        'Akış ekranı: üstte mimari şerit (o adımda veri hangi parçalardan geçiyor), solda sekiz adım, ortada ajanın izi (karar, araç çağrısı, sonuç), sağda adımın çıktısı, şube hafızası ve ajan akışı. Sağ alttaki QR aynı akışı telefonda açar; telefon yalnız izler.',
        `${SIM}; ajanlar sunucuda canlı çalışır, her koşu hafızayı baştan alır.`),
    ],
    4: [
      A('Gökhan komşu şubeden geldi, bu bölgeyi bilmiyor. Telefonuna sabah brifingi geliyor: kaç durak, ne zaman döner, nerede dikkat etmeli.',
        'Haritada rotası: kırmızı = hiç girmediği blok, mavi = adresin hafızasında not var; sağda telefon ekranı (sesli okunur).', `${SIM}; Brifing Ajanı.`),
      A('Rota oynuyor. Notlu bir kapıya yaklaşınca telefon tek cümle söylüyor; kurye "hâlâ geçerli" diye teyit ediyor.',
        'Araç durak durak ilerler; rakam: durak sırası ve planlanan varış.', `${SIM}; hafıza kayıtları.`),
      A('Gökhan bir kapıda yeni bir şey öğreniyor ve 3 saniyelik not bırakıyor. Hafıza Ajanı notu adrese bağlıyor, kişisel bilgiyi ayıklıyor: kişi değil adres.',
        'Telefonda not ve ajanın çıkardığı tek cümlelik ipucu; "kişisel veri ayıklandı" etiketi.', 'Canlı API; hazır notlar var, kendi notunuzu da yazabilirsiniz.'),
      A('Günler sonra aynı adrese başka bir kurye gidiyor; Gökhan\'ın bıraktığı cümle onun brifinginde. Bilgi kişiden adrese taşındı.',
        'Aynı adres, başka gün ve kurye; telefonda yeni kuryenin brifingi.', `${SIM}; canlı hafıza.`),
      A('Hafızanın rotaya etkisi: aynı kurye, aynı duraklar, aynı gün; bir kez hafızasız, bir kez hafızalı yürütülüyor.',
        'Rakamlar: hafızasız ↔ hafızalı dakika; altta ödünç ve yeni kuryelerde ortalama.', `${SIM}; karşı-olgu, aynı rastgele sayılar.`),
    ],
    5: [
      A('Kıdemlinin bildiği kaybolmasın: Hasat Ajanı günün sorularını çıkarıyor (hafızada boş adres, tekrarlayan başarısızlık, saat teyidi); kurye başına en fazla 3 soru.',
        'Haritada soru noktaları, renkleri soru türü; sağda ajanın izi.', `${SIM}; Hasat Ajanı.`),
      A('Gökhan\'ın rotasındaki boş bir adres için o sokağı bilen kıdemliye soru gidiyor; cevap hafızaya yazılıyor ve rota hesabı değişiyor.',
        'Sağda soru ve cevap; rakam: bu adresin servis süresi ve rotanın planlanan süresi.', 'Cevap simüle kıdemliden (simülasyonun gizli gerçeği); sahada 3 saniyelik sesli cevap.'),
      A('Saat teyidi: kayıtlarda görülen "bu saatte kimse yok" kalıbı kuryeye soruluyor. Teyit gelse de aynı rotada kaydırmak rotayı uzatacaksa kaydırılmaz; müdüre alternatif gider.',
        'Sağda soru ve teyit; rakam: yeni sıra ya da aynı rotada kaydırmanın bedeli.', `${SIM}; kural: rota uzamaz, fazla mesai yok.`),
      A('Not olmadan da öğreniliyor: bir iş yerinde öğlen teslim olmuyor, öğleden sonra oluyor. Ajan kalıbı kayıtlardan kendisi buluyor ve rotayı uzatmadan kaydırıyor.',
        'Grafik: geçmiş denemeler saat saat (dolu = teslim, halka = alıcı yok); rakam: yeni varış ve rota süresi farkı.', `${SIM} kayıtları; seçilmiş örnek, mekanizmayı gösterir, büyüklüğü pilot ölçer.`),
    ],
    6: [
      A('Yeni gelen kurye ilk günlerinde ne kadar zorlanıyor? Hafızalı ve hafızasız yeni kurye gün gün karşılaştırılıyor.',
        'Bilgiyle önlenebilir başarısız teslim / 100 durak · mavi: hafızalı · turuncu: hafızasız dünya · gri: aynı rota o gün hafızasız · yatay çizgi: kıdemli düzeyi · rakam: ilk hafta farkı.', `${SIM}; 12 tekrar × 4 yeni kurye.`),
      A('Dört yapı aynı günlerde: bugün (sabit bölge), ajansız yeni yapı, çekirdek bölgeli plan, plan + hafıza.',
        'Çizgiler: ilk denemede teslim yüzdesi gün gün; altta başarısızlık nedenleri.', `${SIM}; aynı gönderiler, dört kol.`),
      A('Parametreler değişince sonuç değişiyor mu? 81 parametre kombinasyonunda aynı karşılaştırma.',
        'Dağılım: kombinasyon başına fark (puan): Courier Memory − bugün ve hafızanın katkısı.', `${SIM} taraması; 81 kombinasyon × 2 tekrar.`),
      A('Uygulama verisi sahaya ne kadar benziyor? Saha verisinin toplu ölçüleriyle karşılaştırma.',
        'Tablo: hedef ↔ uygulama verisi, uyum işareti.', 'Hedefler gerçek verinin yuvarlanmış toplu özetleri; ham veri kullanılmaz.'),
      A('Hafızanın hangi parçası ne katıyor? Parçalar tek tek kapatılarak ölçülüyor.',
        'Tablo: varyant başına önlenebilir başarısız, fazla mesai, km.', `${SIM} ablasyonu; 3 tekrar × 4 senaryo.`),
    ],
    7: [
      A('Bütün bunlar para olarak ne ediyor? Şube başına operasyon maliyeti, bugüne göre.',
        'Rakamlar: günlük ve yıllık tasarruf, başarısız teslim/gün.', `${SIM} + tahmini maliyet parametreleri.`),
      A('Maliyet adım adım: bugün → daha az kurye → ajansız bilgi kaybı → Atama Ajanı geri kazanır → hafıza ve brifing → sabah → sonuç.',
        'Şelale: her çubuk bir adımın günlük TL etkisi.', `${SIM} + tahmini parametreler; sabah kalemi aynı rotanın bugünkü sabahla karşı-olgusu.`),
      A('Dört durum yan yana: kurye, kendi bölgesindeki pay, başarısız teslim, fazla mesai, TL.', 'Tablo.', `${SIM}, uzun dönem.`),
      A('Ölçek: 1, 10, 100 şube; ve hangi modelle ne kadar yapay zekâ maliyeti.', 'Tablolar.', 'Tahmini; modellerin liste fiyatı.'),
      A('Yapay zekâ maliyeti: temkinli (her ajan büyük model) ↔ optimize (önbellek + işe göre model).',
        'İki kart; ajan başına model seçici.', 'Token tahmini ya da canlı ölçüm; liste fiyatı.'),
      A('Parametreyi siz değiştirin: kurye-gün ya da başarısız teslim maliyeti değişince sonuç yeniden hesaplanır.',
        'Kaydırıcılar; şelale ve manşet canlı güncellenir.', 'API, istek başına yeniden hesaplar; tahmini parametreler.'),
    ],
    8: [
      A('Nasıl yaptık: araç kullanan ajanlar, aynı izi üreten dört çalışma modu; spec\'ten koda.',
        'Ajan başına model ve mod (canlı); spec, görev, test sayıları.', 'API durum bilgisi; depo.'),
      A('Sorumlu yapay zekâ: kişi değil adres; kişisel veri araç düzeyinde reddedilir; performans puanı yok; zincir temassız, acil durumda insan devreye girer.', 'İlkeler.', '—'),
      A('Pilot: 4 hafta, tek şube, rotaların yarısı hafızalı; ilk ölçülecekler.', 'Pilot planı.', 'Buradaki rakamlar simülasyon; büyüklüğü pilot ölçer.'),
      A('Tek cümle.', 'Manşet: yıllık tasarruf ve başarısız teslim.', `${SIM} + tahmini parametreler.`),
    ],
  };

  const closed = () => document.body.classList.contains('narration-closed');
  function height() {
    const el = CM.$('narration');
    const h = !el || closed() || !el.innerHTML ? 0 : el.offsetHeight;
    document.documentElement.style.setProperty('--ah', h + 'px');
  }

  CM.drawNarration = function (no, key) {
    const el = CM.$('narration');
    if (!el) return;
    const t = CM.NARRATION[no];
    const a = t && (t[key] || (!Array.isArray(t) && t._));
    el.innerHTML = a ? `<div class="a-row"><b>Ne oluyor</b><span>${a.ne}</span></div>` +
      `<div class="a-row"><b>Ekranda</b><span>${a.screen}${a.data && a.data !== '—' ? ` <i>Veri: ${a.data}</i>` : ''}</span></div>` : '';
    height();
  };
  CM.toggleNarration = function () {
    document.body.classList.toggle('narration-closed');
    try { localStorage.setItem('cm-narration', closed() ? '0' : '1'); } catch (e) { /* yok */ }
    height();
  };
  try { if (localStorage.getItem('cm-narration') === '0') document.body.classList.add('narration-closed'); } catch (e) { /* yok */ }
  if (window.ResizeObserver) new ResizeObserver(height).observe(document.documentElement);
})(window.CM);
