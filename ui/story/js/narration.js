/* Anlatım satırı: her adımda alt çubuğun üstünde "Ne oluyor · Ekranda · Veri". Ekrandaki rakamlar veriden gelir; buradaki
   metinler rakam içermez (veri değişince eskimesin), neyin nasıl gösterildiğini anlatır. A tuşu açar/kapatır.
   Sahne 2 adım değil vuruş (orkestratör aracı) ile ilerler: anahtar vuruşun grubudur (scene2.js → CM.drawNarration(2, grup)). */
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
    2: {
      empty: A('Gün 32, Çarşamba, kampanya günü, saat 09:00. Gönderiler ve kadro belli; müdür "Günü planla" der, orkestratör ajan çalışmaya başlar.',
        'Gri noktalar olağan bir Çarşamba\'nın teslim noktaları.', `${SIM}; konumlar saha verisinden.`),
      read_volume: A('Orkestratör önce günün hacmine bakıyor: kampanya yüzünden gönderi olağanın üstünde.',
        'Sağda orkestratörün izi: her satır bir düşünce, araç çağrısı ya da sonucu. Haritada günün teslim noktaları; rakam: olağan güne göre fark.', `${SIM}; araç: read_volume.`),
      capacity_gap: A('Bu hacim için kaç kurye-gün gerektiği hesaplanıyor; şubenin kendi kadrosu yetmiyor.',
        'Kırmızı rakam eksik kurye; kareler müsait kuryeler ve açık.', `${SIM}; araç: capacity_gap.`),
      neighbor_candidates: A('Açığı kapatmak için komşu şubeden kim gelsin? Her aday için ayrı plan kurulur; alacağı bölgeyi tanıyan önde.',
        'Kartlar: aday ve alacağı kümede tanıdığı durak payı; çerçeveli olanlar önerildi.', `${SIM}; tanıdıklık = kuryenin ortak sınır sokaklarını kendi şubesinden dağıtma geçmişi.`),
      core_assignment: A('Kuryeler kümelere atanıyor: herkes mümkün olduğunca kendi bölgesinde kalır; komşu şubeden gelenler sınır kümelerini alır.',
        'Renkli alanlar kümeler, kuryesinin renginde; rakam: kurye sayısı ve kendi bölgesindeki durak payı.', `${SIM}; araç: core_assignment (Atama Ajanı).`),
      time: A('Geçmiş teslim kayıtlarında "bu adreste şu saatte kimse yok" kalıbı aranıyor. Bulunanlar rota uzamadan uygun saate kaydırılır; kaydırılamayan müdüre alternatif olur.',
        'Halkalar saati kaydırılan adresler; rakam: kaydırılan adres sayısı.', `${SIM} kayıtları, not gerekmez; araçlar: delivery_time_analysis → apply_time_constraint → time_alternatives.`),
      compute_route: A('Bölgeye yabancı kuryelerin rotaları hafızayla hesaplanıyor: bilinen kapalı kapı plandan çıkar, püf noktası süreye eklenir, yanlış saatteki durak kaydırılır.',
        'Odaktaki rota ve durak sırası; izde her rotanın durak, km, dönüş saati ve hafızanın yaptığı değişiklik.', `${SIM}; araç: compute_route (simülatörle aynı fonksiyon, 408/408 aynı rota).`),
      sorting_plan: A('Gönderiler ve atama araç gelmeden belli. Ayrıştırma indirme okutmasına gömülür: her rota bir raf, yükleme sırası rotanın tersi. Kurye ayrıştırma yapmaz, erken çıkar.',
        'Rakam: tahmini çıkış saati ve raf sayısı; izde bugünkü süreçle karşılaştırma.', 'Plandan çıkan tablo (LLM yok); sabah süreleri şube beyanı.'),
      _: A('Orkestratör bir araç çağırdı ve sonucunu okudu.', 'Sağda iz: düşünce, araç çağrısı ve sonucu.', SIM),
      proposal: A('Orkestratör planı gerekçesiyle müdüre sunuyor ve bekliyor. Karar müdürde.',
        'Rakam: kurye sayısı, komşu şubeden gelenler, kendi bölgesindeki pay; buton müdür ekranına geçer.', `${SIM}; araç: present_proposal.`),
    },
    3: [
      A('Müdür ekranı: önerinin ne olduğu ve neden. Komşu şubeden gelen kuryelerin bölgeleri haritada.',
        'Koyu kümeler ödünç kuryelerin bölgeleri; sağda gerekçe; rakamın altında beklenen başarısız teslim ↔ geçmişe bakmadan atama.', `${SIM}; orkestratörün önerisi.`),
      A('Riskler: bazı kuryelerin beklenen süresi vardiya bandını aşıyor; bazı teslim saatleri kural (rota uzamaz) yüzünden kaydırılamadı.',
        'İşaretli üç küme en uzun rotalar; kırmızı etiketli adres kaydırılamayan teslim; sağda müdüre alternatif ve alıcıya gidecek SMS.', `${SIM}; beklenen süre kuryeye özgü tahmin.`),
      A('Müdür "Onur gelmezse ne olur?" diye soruyor; ajan iki yolu araçlarıyla yeniden hesaplıyor: yerine başkası gelir ya da kimse gelmez.',
        'Sağda ajanın izi; kartlarda iki yolun bant üstü süre ve başarısız teslim farkı. Kendi sorunuzu da yazabilirsiniz.', `${SIM}; Atama Ajanı aynı araçları kullanır.`),
      A('Öneri değişmedi; müdür onaylamak üzere.', 'ONAYLA butonu; onaydan sonra brifing ve rotalar onaylı planı okur.', 'Karar insanda.'),
      A('İnsan onayı: plan kesinleşti.', 'İzde İNSAN satırı ve kapanış olayları.', 'API onay kaydı.'),
      A('08:30, araç geldi. İndirme okutmasında her gönderi doğrudan kuryesinin rafına gider; kurye kendi gönderisini ayıklamakla uğraşmaz, rafını zimmetleyip yükler ve çıkar.',
        'Solda raflar (raf = rota; kurye ve gönderi sayısı); sağda okutulan gönderiler ve ekranın söylediği raf; kırmızı satır planda olmayan gönderi (müdüre düşer); altta ortalama çıkış ↔ bugünkü süreç.',
        `${SIM}; gönderi kimlikleri uygulamanın ürettiği; sabah süreleri şube beyanı.`),
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
      A('Sorumlu yapay zekâ: kişi değil adres; kişisel veri araç düzeyinde reddedilir; performans puanı yok; son karar insanda.', 'İlkeler.', '—'),
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
